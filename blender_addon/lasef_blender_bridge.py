
bl_info = {
    "name": "LaSef Blender MCP Bridge",
    "author": "LaSef AI Orchestrator",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > LaSef MCP",
    "description": "LaSef yapay zeka şef ve alt ajanlarının canlı Blender sahnesini okuması, Python/bpy çalıştırması ve render alması için TCP JSON köprüsü.",
    "category": "Development",
}

import io
import json
import queue
import socket
import threading
import traceback
from contextlib import redirect_stdout, redirect_stderr

try:
    import bpy  # type: ignore
except ImportError:
    bpy = None

HOST = "127.0.0.1"
PORT = 9876

_server_socket = None
_server_thread = None
_server_running = False
_cmd_queue: "queue.Queue[tuple]" = queue.Queue()


def _collect_scene_info() -> dict:
    scene = bpy.context.scene
    objs = []
    for obj in scene.objects:
        mats = [ms.material.name for ms in obj.material_slots if ms.material] if hasattr(obj, "material_slots") else []
        objs.append({
            "name": obj.name,
            "type": obj.type,
            "location": [round(float(v), 3) for v in obj.location],
            "scale": [round(float(v), 3) for v in obj.scale],
            "materials": mats,
        })
    return {
        "blender_version": bpy.app.version_string,
        "scene_name": scene.name,
        "object_count": len(objs),
        "active_camera": scene.camera.name if scene.camera else None,
        "render_engine": scene.render.engine,
        "objects": objs[:200],
    }


def _handle_command_on_main_thread(payload: dict) -> dict:
    cmd = payload.get("command", "")
    params = payload.get("params") or {}

    if cmd == "ping":
        return {
            "success": True,
            "message": "LaSef Blender MCP Bridge Aktif",
            "blender_version": bpy.app.version_string,
            "scene_name": bpy.context.scene.name,
            "object_count": len(bpy.context.scene.objects),
        }

    if cmd == "get_scene_info":
        return {"success": True, **_collect_scene_info()}

    if cmd == "execute_python":
        code = params.get("code", "")
        if not code.strip():
            return {"success": False, "error": "Calistirilacak Python kodu bos."}
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        ns = {"__name__": "__main__", "bpy": bpy}
        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(compile(code, "<lasef_live_bpy>", "exec"), ns)
            return {
                "success": True,
                "stdout": stdout_buf.getvalue()[-4000:],
                "stderr": stderr_buf.getvalue()[-2000:],
                "scene": _collect_scene_info(),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc()[-4000:],
                "stdout": stdout_buf.getvalue()[-2000:],
            }

    if cmd == "render_preview":
        out_path = params.get("output_path", "")
        if not out_path:
            import tempfile, os
            out_path = os.path.join(tempfile.gettempdir(), "lasef_blender_live_preview.png")
        scene = bpy.context.scene
        if not scene.camera:
            cams = [o for o in scene.objects if o.type == "CAMERA"]
            if cams:
                scene.camera = cams[0]
        if not scene.camera:
            return {"success": False, "error": "Sahnede render alinacak Camera nesnesi yok."}

        prev_path = scene.render.filepath
        prev_fmt = scene.render.image_settings.file_format
        prev_rx = scene.render.resolution_x
        prev_ry = scene.render.resolution_y
        try:
            scene.render.filepath = out_path
            scene.render.image_settings.file_format = "PNG"
            scene.render.resolution_x = int(params.get("width", 800))
            scene.render.resolution_y = int(params.get("height", 450))
            bpy.ops.render.render(write_still=True)
            return {"success": True, "image_path": out_path}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        finally:
            scene.render.filepath = prev_path
            scene.render.image_settings.file_format = prev_fmt
            scene.render.resolution_x = prev_rx
            scene.render.resolution_y = prev_ry

    return {"success": False, "error": f"Bilinmeyen Blender komutu: {cmd}"}


def _pump_commands_timer():
    while not _cmd_queue.empty():
        try:
            payload, result_holder, done_event = _cmd_queue.get_nowait()
        except queue.Empty:
            break
        try:
            result_holder["data"] = _handle_command_on_main_thread(payload)
        except Exception as exc:
            result_holder["data"] = {"success": False, "error": str(exc)}
        finally:
            done_event.set()
    return 0.05 if _server_running else None


def _client_worker(conn: socket.socket):
    try:
        conn.settimeout(30.0)
        chunks = []
        while True:
            data = conn.recv(65536)
            if not data:
                break
            chunks.append(data)
            if b"\n" in data:
                break
        raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not raw:
            return
        payload = json.loads(raw)
        holder: dict = {}
        ev = threading.Event()
        _cmd_queue.put((payload, holder, ev))
        if ev.wait(timeout=30.0):
            resp = holder.get("data", {"success": False, "error": "Bos yanit"})
        else:
            resp = {"success": False, "error": "Blender ana thread zaman asimi"}
        conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception as exc:
        try:
            conn.sendall((json.dumps({"success": False, "error": str(exc)}) + "\n").encode("utf-8"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _server_accept_loop():
    global _server_running
    while _server_running and _server_socket:
        try:
            conn, _addr = _server_socket.accept()
            t = threading.Thread(target=_client_worker, args=(conn,), daemon=True)
            t.start()
        except OSError:
            break
        except Exception:
            continue


def start_bridge_server():
    global _server_socket, _server_thread, _server_running
    if _server_running or bpy is None:
        return
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(8)
        _server_socket = srv
        _server_running = True
        bpy.app.timers.register(_pump_commands_timer, persistent=True)
        _server_thread = threading.Thread(target=_server_accept_loop, daemon=True)
        _server_thread.start()
        print(f"🎨 [LaSef Blender MCP Bridge] {HOST}:{PORT} dinlemede.")
    except Exception as exc:
        print(f"⚠️ [LaSef Blender MCP Bridge] Başlatılamadı: {exc}")
        stop_bridge_server()


def stop_bridge_server():
    global _server_socket, _server_running
    _server_running = False
    if _server_socket:
        try:
            _server_socket.close()
        except Exception:
            pass
        _server_socket = None


if bpy is not None:
    class LASEF_OT_StartBridge(bpy.types.Operator):
        bl_idname = "lasef.start_bridge"
        bl_label = "LaSef Köprüsünü Başlat"

        def execute(self, context):
            start_bridge_server()
            return {"FINISHED"}

    class LASEF_OT_StopBridge(bpy.types.Operator):
        bl_idname = "lasef.stop_bridge"
        bl_label = "Köprüyü Durdur"

        def execute(self, context):
            stop_bridge_server()
            return {"FINISHED"}

    class LASEF_PT_BridgePanel(bpy.types.Panel):
        bl_label = "LaSef MCP Köprüsü"
        bl_idname = "LASEF_PT_bridge_panel"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "LaSef MCP"

        def draw(self, context):
            layout = self.layout
            status = f"Aktif ({HOST}:{PORT})" if _server_running else "Kapalı"
            layout.label(text=f"Durum: {status}")
            if not _server_running:
                layout.operator("lasef.start_bridge", icon="PLAY")
            else:
                layout.operator("lasef.stop_bridge", icon="PAUSE")

    _CLASSES = (LASEF_OT_StartBridge, LASEF_OT_StopBridge, LASEF_PT_BridgePanel)

    def register():
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
        start_bridge_server()

    def unregister():
        stop_bridge_server()
        for cls in reversed(_CLASSES):
            bpy.utils.unregister_class(cls)
