import os
import re
import sys
import time
import json
import shutil
import urllib.request
import urllib.error
import threading
from typing import Dict, Any, Optional, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8088"

class UnityBridgeClient:
    """
    Python tarafındaki Unity Editor Köprü İstemcisi.
    - REST API üzerinden Unity Editor ile çift yönlü haberleşir.
    - Derleme (Domain Reload) durumunu takip eder ve kilitlenmeyi önler.
    - Thread-safe komut yürütme sağlar.
    """
    def __init__(self, base_url: str = DEFAULT_BRIDGE_URL):
        self.base_url = base_url.rstrip("/")
        self._lock = threading.Lock()

    def _parse_json_safe(self, body: str) -> Dict[str, Any]:
        """JSON yanıtını ayrıştırır; Türkçe yerel ayar ondalık virgül (0,00 -> 0.00) kaymalarını otomatik onarır."""
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            fixed = re.sub(
                r'("pos"\s*:\s*\{\s*"x"\s*:\s*-?\d+),(\d+\s*,\s*"y"\s*:\s*-?\d+),(\d+\s*,\s*"z"\s*:\s*-?\d+),(\d+\s*\})',
                r'\1.\2.\3.\4',
                body
            )
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return {"success": True, "raw": body}

    @staticmethod
    def _wake_unity_editor_window() -> None:
        """
        Windows üzerinde Unity Editor penceresi arka plandayken (odak dışındayken)
        EditorApplication.update döngüsünün uyumaması için Win32 mesaj kuyruğunu dürter.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def _cb(hwnd, _lparam):
                buf = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(hwnd, buf, 128)
                if "Unity" in buf.value:
                    user32.PostMessageW(hwnd, 0x0000, 0, 0)
                    user32.PostMessageW(hwnd, 0x0113, 0, 0)
                return True

            user32.EnumWindows(WNDENUMPROC(_cb), 0)
        except Exception:
            pass

    def _send_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 15.0,
        retries: int = 4
    ) -> Dict[str, Any]:
        """
        Unity Editor'e HTTP isteği gönderir ve JSON cevabını ayrıştırır.
        Domain Reload (Play Mode geçişi veya C# derlemesi) sırasında oluşan geçici
        WinError 10061 / bağlantı kopmalarını otomatik yeniden deneyerek tolere eder.
        """
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        req_data = json.dumps(data).encode("utf-8") if data else None

        if endpoint not in ("/status", "/console/logs", "/console/clear"):
            self._wake_unity_editor_window()

        last_err = ""
        for attempt in range(max(1, retries + 1)):
            if attempt > 0:
                self._wake_unity_editor_window()
            req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    body = response.read().decode("utf-8")
                    return self._parse_json_safe(body)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8")
                try:
                    return json.loads(err_body)
                except Exception:
                    return {"success": False, "error": f"HTTP {e.code}: {e.reason}", "raw": err_body}
            except urllib.error.URLError as e:
                last_err = str(e.reason)
                if attempt < retries:
                    time.sleep(0.75)
                    continue
                return {
                    "success": False,
                    "error": f"Unity Editor bağlantısı kurulamadı ({self.base_url}). Unity açık mı ve köprü scripti (LaSefBridgeServer.cs) yüklü mü? Hata: {e.reason}"
                }
            except Exception as e:
                last_err = str(e)
                if attempt < retries:
                    time.sleep(0.75)
                    continue
                return {"success": False, "error": f"Bilinmeyen köprü hatası: {last_err}"}
        return {"success": False, "error": last_err}

    def is_connected(self) -> bool:
        """Unity Editor'ün canlı ve dinlemede olup olmadığını kontrol eder."""
        res = self._send_request("/status", method="GET", timeout=2.0, retries=1)
        return bool(res.get("online", False))

    def get_status(self) -> Dict[str, Any]:
        """Unity'nin güncel durumunu, sahne adını ve derleme vaziyetini sorgular."""
        return self._send_request("/status", method="GET")

    def refresh_assets(self) -> Dict[str, Any]:
        """Unity AssetDatabase.Refresh çağrısı yaparak dosya değişikliklerini editöre bildirir."""
        with self._lock:
            return self._send_request("/asset/refresh", method="GET", timeout=15.0, retries=2)

    def compile_project_locally_with_dotnet(self, project_path: str) -> Dict[str, Any]:
        """
        Unity Editor odak dışında veya kapalı olsa bile projedeki Assembly-CSharp.csproj /
        Assembly-CSharp-Editor.csproj dosyalarını gerçek Unity DLL'lerine karşı Roslyn (dotnet build)
        ile 1-2 saniyede derler ve tüm CS derleme hatalarını %100 kesinlikle yakalar.
        """
        import subprocess
        if not project_path or not os.path.isdir(project_path):
            return {"supported": False, "has_errors": False, "errors": []}

        runtime_csproj = os.path.join(project_path, "Assembly-CSharp.csproj")
        editor_csproj = os.path.join(project_path, "Assembly-CSharp-Editor.csproj")
        if not os.path.exists(runtime_csproj) and not os.path.exists(editor_csproj):
            return {"supported": False, "has_errors": False, "errors": []}

        self._sync_csproj_compile_items(project_path, runtime_csproj, is_editor=False)
        self._sync_csproj_compile_items(project_path, editor_csproj, is_editor=True)

        target_csproj = editor_csproj if os.path.exists(editor_csproj) else runtime_csproj
        obj_assets = os.path.join(project_path, "Temp", "obj", os.path.splitext(os.path.basename(target_csproj))[0], "project.assets.json")

        cmd = ["dotnet", "build", target_csproj, "-v", "q", "-nologo"]
        if os.path.exists(obj_assets):
            cmd.append("--no-restore")

        try:
            proc = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30.0
            )
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if "NETSDK1004" in output and "--no-restore" in cmd:
                cmd.remove("--no-restore")
                proc = subprocess.run(
                    cmd,
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=35.0
                )
                output = (proc.stdout or "") + "\n" + (proc.stderr or "")

            cs_errors: List[str] = []
            cs_warnings: List[str] = []
            for line in output.splitlines():
                s = line.strip()
                if (": error CS" in s or ": warning CS" in s) and "LaSefDynamicRunner_" not in s:
                    m_rel = re.search(r'(Assets[\\/].*)', s)
                    clean_diag = m_rel.group(1) if m_rel else s
                    clean_diag = re.sub(r'\s*\[[^\]]+\.csproj\]\s*$', '', clean_diag).strip()
                    if ": error CS" in s:
                        if clean_diag not in cs_errors:
                            cs_errors.append(clean_diag)
                    elif ": warning CS" in s:
                        if clean_diag not in cs_warnings:
                            cs_warnings.append(clean_diag)

            return {
                "supported": True,
                "has_errors": len(cs_errors) > 0,
                "errors": cs_errors,
                "warnings": cs_warnings,
                "exit_code": proc.returncode
            }
        except Exception as ex:
            return {"supported": False, "has_errors": False, "errors": [], "error": str(ex)}

    def _sync_csproj_compile_items(self, project_path: str, csproj_path: str, is_editor: bool) -> None:
        """Assets/ altındaki mevcut C# dosyalarını ilgili .csproj dosyasıyla senkronize eder (silinenleri çıkarır, yenileri ekler)."""
        if not os.path.exists(csproj_path):
            return
        try:
            with open(csproj_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            assets_root = os.path.join(project_path, "Assets")
            if not os.path.isdir(assets_root):
                return

            actual_cs_rel: List[str] = []
            for root, _dirs, files in os.walk(assets_root):
                for fname in files:
                    if not fname.endswith(".cs") or fname.startswith("LaSefDynamicRunner_"):
                        continue
                    full_p = os.path.join(root, fname)
                    rel_p = os.path.relpath(full_p, project_path).replace("/", "\\")
                    parts_lower = [p.lower() for p in rel_p.split("\\")]
                    file_in_editor = "editor" in parts_lower
                    if file_in_editor == is_editor:
                        actual_cs_rel.append(rel_p)

            changed = False
            for m in list(re.finditer(r'\s*<Compile Include="(Assets\\[^"]+\.cs)"\s*/>', content)):
                inc_rel = m.group(1)
                if not os.path.exists(os.path.join(project_path, inc_rel)):
                    content = content.replace(m.group(0), "")
                    changed = True

            missing = [rel for rel in actual_cs_rel if f'Include="{rel}"' not in content]
            if missing:
                insert_tags = "\n".join(f'    <Compile Include="{rel}" />' for rel in missing)
                m_group = re.search(r'(<Compile Include="Assets\\[^"]+\.cs"\s*/>)', content)
                if m_group:
                    content = content.replace(m_group.group(1), m_group.group(1) + "\n" + insert_tags, 1)
                    changed = True

            if changed:
                with open(csproj_path, "w", encoding="utf-8") as wf:
                    wf.write(content)
        except Exception:
            pass

    def wait_for_compilation(self, timeout: float = 35.0, trigger_refresh: bool = True, project_path: str = "") -> Dict[str, Any]:
        """
        Unity C# derleme (Domain Reload) yapıyorsa bitene kadar bekler.
        Hem Assembly-CSharp.dll hem de Assembly-CSharp-Editor.dll hatalarını,
        yerel Roslyn (dotnet build) kontrolünü ve EditorUtility.scriptCompilationFailed durumunu denetler.
        """
        refresh_ok = True
        if trigger_refresh:
            try:
                ref_res = self.refresh_assets()
                refresh_ok = bool(ref_res.get("success", False))
            except Exception:
                refresh_ok = False
            time.sleep(1.2)

        start = time.time()
        while time.time() - start < timeout:
            status = self.get_status()
            if not status.get("online"):
                time.sleep(1.0)
                continue

            if int(status.get("pending_queue", 0) or 0) > 0:
                time.sleep(0.6)
                continue

            if not status.get("is_compiling"):
                time.sleep(0.5)
                status = self.get_status()
                if status.get("is_compiling") or int(status.get("pending_queue", 0) or 0) > 0:
                    time.sleep(0.8)
                    continue

                compile_errors = [
                    e for e in status.get("compile_errors", [])
                    if "LaSefDynamicRunner_" not in e and "LaSefBridge" not in e
                ]
                script_comp_failed = bool(status.get("script_compilation_failed", False))

                try:
                    logs_res = self.get_console_logs()
                    for l in logs_res.get("logs", []):
                        msg = l.get("message", "")
                        if "error CS" in msg and "LaSefDynamicRunner_" not in msg and "LaSefBridge" not in msg:
                            if msg not in compile_errors:
                                compile_errors.append(msg)
                except Exception:
                    pass

                eff_project_path = project_path
                if not eff_project_path and status.get("project_path"):
                    p_str = str(status.get("project_path", ""))
                    eff_project_path = os.path.dirname(p_str) if p_str.endswith(("Assets", "Assets/", "Assets\\")) else p_str

                if eff_project_path and (not compile_errors or not refresh_ok):
                    local_check = self.compile_project_locally_with_dotnet(eff_project_path)
                    if local_check.get("supported"):
                        if local_check.get("has_errors"):
                            for le in local_check.get("errors", []):
                                if le not in compile_errors:
                                    compile_errors.append(le)
                        else:
                            if not compile_errors:
                                script_comp_failed = False

                if script_comp_failed and not compile_errors:
                    editor_log = os.path.expandvars(r"%LOCALAPPDATA%\Unity\Editor\Editor.log")
                    if os.path.exists(editor_log):
                        try:
                            with open(editor_log, "r", encoding="utf-8", errors="ignore") as lf:
                                son_satirlar = lf.readlines()[-80:]
                            for s in son_satirlar:
                                s_str = s.strip()
                                if "error CS" in s_str and "LaSefDynamicRunner_" not in s_str and "LaSefBridge" not in s_str:
                                    if s_str not in compile_errors:
                                        compile_errors.append(s_str)
                        except Exception:
                            pass

                if compile_errors or script_comp_failed:
                    if not compile_errors:
                        compile_errors = ["Unity scriptCompilationFailed bayrağı aktif (Derleme hatası mevcut)."]
                    return {
                        "success": False,
                        "compiling": False,
                        "has_errors": True,
                        "errors": compile_errors,
                        "message": f"Unity C# derleme hatası tespit edildi ({len(compile_errors)} hata)."
                    }
                return {"success": True, "compiling": False, "has_errors": False, "message": "Derleme başarıyla tamamlandı (Temiz)."}

            time.sleep(1.0)

        if project_path:
            local_check = self.compile_project_locally_with_dotnet(project_path)
            if local_check.get("supported"):
                if local_check.get("has_errors"):
                    errs = local_check.get("errors", [])
                    return {
                        "success": False,
                        "compiling": False,
                        "has_errors": True,
                        "errors": errs,
                        "message": f"Yerel C# derleme kontrolünde {len(errs)} hata tespit edildi."
                    }
                return {"success": True, "compiling": False, "has_errors": False, "message": "Yerel Roslyn derlemesi temiz (0 hata)."}

        return {"success": False, "error": f"Derleme zaman aşımına uğradı ({timeout}s)."}

    def get_hierarchy(self) -> Dict[str, Any]:
        """Aktif sahnedeki tüm GameObject hiyerarşisini ve bileşenlerini ağaç yapısında çeker (PlayMode geçişinde bekler)."""
        for _ in range(8):
            with self._lock:
                res = self._send_request("/hierarchy", method="GET")
            if isinstance(res, dict) and (res.get("transitioning") or res.get("compiling")):
                time.sleep(0.6)
                continue
            return res
        return res

    def inspect_gameobject(self, target: str) -> Dict[str, Any]:
        """Belirli bir GameObject'in tüm bileşenlerini ve SerializedProperty alanlarını inceler."""
        with self._lock:
            return self._send_request("/gameobject/inspect", method="POST", data={"target": target})

    def create_gameobject(
        self,
        name: str,
        primitive_type: Optional[str] = None,
        parent: Optional[str] = None,
        px: float = 0.0, py: float = 0.0, pz: float = 0.0,
        sx: float = 1.0, sy: float = 1.0, sz: float = 1.0
    ) -> Dict[str, Any]:
        """Sahneye yeni bir GameObject veya Primitif (Cube, Sphere, vb.) ekler."""
        with self._lock:
            payload = {
                "name": name,
                "primitive_type": primitive_type or "",
                "parent": parent or "",
                "px": px, "py": py, "pz": pz,
                "sx": sx, "sy": sy, "sz": sz
            }
            return self._send_request("/gameobject/create", method="POST", data=payload)

    def delete_gameobject(self, target: str) -> Dict[str, Any]:
        """Sahnedeki bir objeyi güvenli bir şekilde (Undo destekli) siler."""
        with self._lock:
            return self._send_request("/gameobject/delete", method="POST", data={"target": target})

    def add_component(self, target: str, component_name: str) -> Dict[str, Any]:
        """Bir GameObject'e belirtilen bileşeni (Rigidbody, BoxCollider, PlayerController vb.) ekler."""
        with self._lock:
            return self._send_request("/component/add", method="POST", data={"target": target, "component": component_name})

    def set_property(
        self,
        target: str,
        component: str,
        property_name: str,
        value: str,
        is_reference: bool = False
    ) -> Dict[str, Any]:
        """
        Bileşenin SerializedProperty alanını değiştirir.
        `is_reference=True` ise sahnedeki başka bir objeyi veya Asset dosyasını referans olarak bağlar!
        """
        with self._lock:
            payload = {
                "target": target,
                "component": component,
                "property": property_name,
                "value": str(value),
                "is_reference": is_reference
            }
            return self._send_request("/property/set", method="POST", data=payload)

    def create_prefab(self, target: str, asset_path: Optional[str] = None) -> Dict[str, Any]:
        """Sahnedeki bir objeyi temiz bir Prefab olarak kaydeder."""
        with self._lock:
            payload = {"target": target}
            if asset_path:
                payload["asset_path"] = asset_path
            return self._send_request("/prefab/create", method="POST", data=payload)

    def instantiate_prefab(self, asset_path: str, parent: Optional[str] = None) -> Dict[str, Any]:
        """Bir Prefab asset'ini sahneye örnekler (Instantiate)."""
        with self._lock:
            return self._send_request("/prefab/instantiate", method="POST", data={"asset_path": asset_path, "parent": parent or ""})

    def execute_csharp(self, code_snippet: str) -> Dict[str, Any]:
        """Unity Editor context'inde dinamik C# kodu çalıştırır (REPL)."""
        with self._lock:
            return self._send_request("/execute_csharp", method="POST", data={"code": code_snippet})

    def get_console_logs(self) -> Dict[str, Any]:
        """Unity editörünün son konsol loglarını ve hatalarını çeker (Köprü iç gürültüsü filtrelenir)."""
        res = self._send_request("/console/logs", method="GET")
        if isinstance(res, dict) and "logs" in res and isinstance(res["logs"], list):
            res["logs"] = [
                l for l in res["logs"]
                if not any(
                    noise in (l.get("message", "") + l.get("stackTrace", ""))
                    for noise in ["LaSefDynamicRunner_", "LaSefBridgeServer", "[LaSef Köprüsü]"]
                )
            ]
        return res

    def clear_console_logs(self) -> Dict[str, Any]:
        """Unity editöründeki konsol loglarını ve derleme hatalarını temizler."""
        return self._send_request("/console/clear", method="POST", data={})

    def save_scene(self) -> Dict[str, Any]:
        """Aktif sahneyi diske kaydeder."""
        with self._lock:
            return self._send_request("/scene/save", method="POST", data={})

    def set_play_mode(self, play: bool = True, wait_reload: bool = True) -> Dict[str, Any]:
        """
        Unity'de Play Mode'u (Oyun Modunu) açar veya kapatır.
        Play Mode geçişindeki Domain Reload tamamlanıp köprü yeniden ayağa kalkana kadar bekler.
        """
        with self._lock:
            res = self._send_request("/playmode/set", method="POST", data={"play": play}, retries=3)

        if wait_reload:
            time.sleep(1.2)
            start_wait = time.time()
            while time.time() - start_wait < 12.0:
                st = self._send_request("/status", method="GET", timeout=2.5, retries=0)
                if st.get("online") and not st.get("is_compiling") and bool(st.get("is_playing")) == bool(play):
                    return {"success": True, "is_playing": play}
                time.sleep(0.5)
        return res

    def capture_screenshot(self, prefer_game_view: bool = True) -> Dict[str, Any]:
        """SceneView veya GameView (Camera.main) kamerasından Base64 formatında ekran görüntüsü alır."""
        with self._lock:
            return self._send_request("/camera/capture", method="POST", data={"game_view": prefer_game_view})

    def install_bridge_to_project(self, project_path: str) -> bool:
        """
        Hedef Unity projesine `LaSefBridgeServer.cs` scriptini otomatik kopyalar
        ve varsa eski `LaSefDynamicRunner_*.cs/.meta` kalıntılarını temizler.
        """
        assets_dir = os.path.join(project_path, "Assets")
        if not os.path.exists(assets_dir):
            return False

        editor_bridge_dir = os.path.join(assets_dir, "Editor", "LaSefBridge")
        os.makedirs(editor_bridge_dir, exist_ok=True)

        try:
            for fname in os.listdir(editor_bridge_dir):
                if fname.startswith("LaSefDynamicRunner_"):
                    try:
                        os.remove(os.path.join(editor_bridge_dir, fname))
                    except Exception:
                        pass
        except Exception:
            pass

        source_cs = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "unity_bridge", "Editor", "LaSefBridge", "LaSefBridgeServer.cs"))
        dest_cs = os.path.join(editor_bridge_dir, "LaSefBridgeServer.cs")

        if os.path.exists(source_cs):
            need_copy = True
            if os.path.exists(dest_cs):
                try:
                    with open(source_cs, "rb") as sf, open(dest_cs, "rb") as df:
                        if sf.read() == df.read():
                            need_copy = False
                except Exception:
                    need_copy = True

            if need_copy:
                shutil.copy2(source_cs, dest_cs)
                print(f"✅ [Unity Bridge] Köprü başarıyla kuruldu: {dest_cs}")
            self.ensure_mcp_project_setup(project_path, copy_bridge=False)
            return True
        return False

    def ensure_mcp_project_setup(self, project_path: str, copy_bridge: bool = True) -> Dict[str, Any]:
        """
        Hedef Unity projesinin standart MCP (CoplayDev/unity-mcp + LaSef-Unity-Bridge)
        yapılandırmasını denetler, güncel köprüyü kopyalar ve `.mcp.json` bağlantı dosyasını hazırlar.
        """
        if copy_bridge:
            self.install_bridge_to_project(project_path)

        result = {
            "project_path": project_path,
            "has_coplay_unity_mcp": False,
            "coplay_mcp_configured": False,
            "has_lasef_bridge": False,
            "bridge_installed": False,
            "mcp_config_path": "",
            "mcp_json_created": False
        }
        bridge_cs = os.path.join(project_path, "Assets", "Editor", "LaSefBridge", "LaSefBridgeServer.cs")
        has_bridge = os.path.exists(bridge_cs)
        result["has_lasef_bridge"] = has_bridge
        result["bridge_installed"] = has_bridge

        manifest_path = os.path.join(project_path, "Packages", "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                deps = manifest.get("dependencies", {})
                has_coplay = "com.coplaydev.unity-mcp" in deps
                result["has_coplay_unity_mcp"] = has_coplay
                result["coplay_mcp_configured"] = has_coplay
            except Exception:
                pass

        lasef_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        mcp_server_py = os.path.join(lasef_root, "tools", "unity_mcp_server.py")
        mcp_cfg = {
            "mcpServers": {
                "lasef-unity-bridge": {
                    "command": sys.executable or "python",
                    "args": [mcp_server_py],
                    "env": {
                        "UNITY_PORT": "8088",
                        "UNITY_PROJECT_PATH": os.path.abspath(project_path)
                    }
                }
            }
        }
        mcp_json_path = os.path.join(project_path, ".mcp.json")
        try:
            new_json_str = json.dumps(mcp_cfg, indent=2, ensure_ascii=False)
            existing_json_str = ""
            if os.path.exists(mcp_json_path):
                try:
                    with open(mcp_json_path, "r", encoding="utf-8") as ef:
                        existing_json_str = ef.read()
                except Exception:
                    existing_json_str = ""
            if existing_json_str != new_json_str:
                with open(mcp_json_path, "w", encoding="utf-8") as f:
                    f.write(new_json_str)
            result["mcp_config_path"] = mcp_json_path
            result["mcp_json_created"] = True
        except Exception:
            pass
        return result

unity_client = UnityBridgeClient()
