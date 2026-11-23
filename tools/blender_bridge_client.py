
import glob
import json
import os
import shutil
import socket
import subprocess
import tempfile
from typing import Any, Dict, List, Optional


def find_blender_executable() -> Optional[str]:
    """Sistemdeki Blender çalıştırılabilir dosyasını (env, PATH veya kurulum dizini) bulur."""
    env_path = os.getenv("BLENDER_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path

    which_path = shutil.which("blender")
    if which_path:
        return which_path

    candidates: List[str] = []
    if os.name == "nt":
        for root in [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        ]:
            candidates.extend(glob.glob(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe")))
    elif os.uname().sysname == "Darwin":
        candidates.append("/Applications/Blender.app/Contents/MacOS/Blender")
    else:
        candidates.extend(["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"])

    existing = [p for p in candidates if os.path.exists(p)]
    if existing:
        existing.sort(reverse=True)
        return existing[0]
    return None


class BlenderBridgeClient:
    """Canlı Blender TCP/JSON köprüsü ve Headless CLI çalıştırıcısı."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9876, timeout: float = 15.0):
        self.host = host
        self.port = int(os.getenv("LASEF_BLENDER_PORT", port))
        self.timeout = timeout

    def _send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"command": command, "params": params or {}}
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            chunks: List[bytes] = []
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
                if b"\n" in data:
                    break
            raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
            if not raw:
                return {"success": False, "error": "Blender köprüsünden boş yanıt döndü."}
            return json.loads(raw)
        except Exception as exc:
            return {"success": False, "error": f"Blender bağlantı hatası ({self.host}:{self.port}): {exc}"}
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def is_alive(self) -> bool:
        try:
            res = self._send_command("ping")
            return bool(res.get("success"))
        except Exception:
            return False

    def ping(self) -> Dict[str, Any]:
        return self._send_command("ping")

    def get_scene_info(self) -> Dict[str, Any]:
        return self._send_command("get_scene_info")

    def execute_python(self, code: str) -> Dict[str, Any]:
        return self._send_command("execute_python", {"code": code})

    def render_preview(self, output_path: Optional[str] = None, width: int = 800, height: int = 450) -> Dict[str, Any]:
        return self._send_command("render_preview", {
            "output_path": output_path or "",
            "width": width,
            "height": height,
        })

    def get_blender_version(self) -> Optional[str]:
        exe = find_blender_executable()
        if not exe:
            return None
        try:
            res = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
            out = (res.stdout or res.stderr or "").strip().splitlines()
            return out[0] if out else exe
        except Exception:
            return exe

    def run_script_headless(
        self,
        script_path: str,
        save_blend_path: Optional[str] = None,
        render_preview_path: Optional[str] = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """Üretilen bpy betiğini sistemdeki Blender --background --python ile gerçekten çalıştırır."""
        exe = find_blender_executable()
        if not exe:
            return {
                "success": False,
                "blender_found": False,
                "error": "Sistemde Blender kurulumu bulunamadı (BLENDER_PATH ayarlanabilir)."
            }
        if not os.path.exists(script_path):
            return {"success": False, "blender_found": True, "error": f"Betik bulunamadı: {script_path}"}

        harness_code = r"""
import json, os, runpy, sys, traceback
try:
    import bpy
except Exception as e:
    print("LASEF_BLENDER_JSON:" + json.dumps({"success": False, "error": f"bpy import failed: {e}"}))
    sys.exit(2)

target_script = sys.argv[sys.argv.index("--") + 1]
save_blend = sys.argv[sys.argv.index("--") + 2]
render_png = sys.argv[sys.argv.index("--") + 3]

result = {"success": False, "script": target_script}
try:
    # Varsayilan baslangic kupunu temizlemeden once sahneyi hazir tut veya betigin yonetmesine izin ver
    runpy.run_path(target_script, run_name="__main__")
    scene = bpy.context.scene
    objs = [{"name": o.name, "type": o.type} for o in scene.objects]
    result["success"] = True
    result["blender_version"] = bpy.app.version_string
    result["object_count"] = len(objs)
    result["objects"] = objs[:150]
    result["meshes"] = sum(1 for o in scene.objects if o.type == "MESH")
    result["lights"] = sum(1 for o in scene.objects if o.type == "LIGHT")
    result["cameras"] = sum(1 for o in scene.objects if o.type == "CAMERA")

    if save_blend:
        os.makedirs(os.path.dirname(os.path.abspath(save_blend)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save_blend))
        result["blend_path"] = os.path.abspath(save_blend)

    if render_png and scene.camera:
        os.makedirs(os.path.dirname(os.path.abspath(render_png)), exist_ok=True)
        scene.render.filepath = os.path.abspath(render_png)
        scene.render.image_settings.file_format = "PNG"
        scene.render.resolution_x = 640
        scene.render.resolution_y = 360
        try:
            if hasattr(scene, "cycles") and scene.render.engine == "CYCLES":
                scene.cycles.samples = min(int(getattr(scene.cycles, "samples", 16)), 16)
            elif hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
                scene.eevee.taa_render_samples = min(int(scene.eevee.taa_render_samples), 16)
        except Exception:
            pass
        bpy.ops.render.render(write_still=True)
        if os.path.exists(render_png):
            result["render_path"] = os.path.abspath(render_png)
except Exception as exc:
    result["success"] = False
    result["error"] = str(exc)
    result["traceback"] = traceback.format_exc()[-4000:]

print("LASEF_BLENDER_JSON:" + json.dumps(result, ensure_ascii=False))
if not result.get("success"):
    sys.exit(1)
"""
        tmp_harness = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix="_lasef_harness.py", delete=False, encoding="utf-8") as tf:
                tf.write(harness_code)
                tmp_harness = tf.name

            cmd = [
                exe,
                "--background",
                "--factory-startup",
                "--python", tmp_harness,
                "--",
                os.path.abspath(script_path),
                os.path.abspath(save_blend_path) if save_blend_path else "",
                os.path.abspath(render_preview_path) if render_preview_path else "",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            parsed: Dict[str, Any] = {}
            for line in stdout.splitlines():
                if line.startswith("LASEF_BLENDER_JSON:"):
                    try:
                        parsed = json.loads(line.split("LASEF_BLENDER_JSON:", 1)[1].strip())
                    except Exception:
                        pass
            if parsed:
                parsed["blender_found"] = True
                parsed["blender_exe"] = exe
                parsed["stdout_tail"] = stdout[-2000:]
                parsed["stderr_tail"] = stderr[-1500:]
                return parsed

            return {
                "success": proc.returncode == 0,
                "blender_found": True,
                "blender_exe": exe,
                "returncode": proc.returncode,
                "stdout_tail": stdout[-2000:],
                "stderr_tail": stderr[-1500:],
                "error": stderr.strip()[-1000:] if proc.returncode != 0 else "",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "blender_found": True, "blender_exe": exe, "error": f"Blender headless zaman aşımı ({timeout:.0f}s)"}
        except Exception as exc:
            return {"success": False, "blender_found": True, "blender_exe": exe, "error": str(exc)}
        finally:
            if tmp_harness and os.path.exists(tmp_harness):
                try:
                    os.remove(tmp_harness)
                except Exception:
                    pass


blender_bridge = BlenderBridgeClient()
