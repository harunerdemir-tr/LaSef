
import os
from typing import Any, Dict, List
from infrastructure.gemini_client import gemini_service
from agents.worker_agent import saf_kodu_ayikla
from tools.blender_bridge_client import blender_bridge, find_blender_executable


class BlenderAutonomousRunner:
    """Üretilen Blender bpy betiklerini canlı köprü veya headless Blender CLI ile doğrular ve onarır."""

    def __init__(self, target_folder: str):
        self.target_folder = target_folder

    def run_full_pipeline(self, user_request: str, generated_files: Dict[str, Any]) -> Dict[str, Any]:
        summary_lines: List[str] = []
        bpy_files = [
            f for f, code in generated_files.items()
            if f.lower().endswith(".py") and isinstance(code, str) and "import bpy" in code
        ]
        if not bpy_files:
            return {"blender_tested": False, "summary": "Blender bpy betiği bulunamadı."}

        live_ok = blender_bridge.is_alive()
        exe = find_blender_executable()
        if not live_ok and not exe:
            return {
                "blender_tested": False,
                "summary": "Ne canlı Blender MCP köprüsü (9876) ne de Blender CLI kurulumu bulunamadı.",
            }

        print("\n🎨 [BLENDER MCP & DOĞRULAMA BAŞLIYOR]...")
        all_ok = True
        object_total = 0
        render_path_out = ""

        for rel_name in bpy_files:
            disk_path = os.path.join(self.target_folder, os.path.basename(rel_name))
            if not os.path.exists(disk_path):
                for root, _dirs, files in os.walk(self.target_folder):
                    if os.path.basename(rel_name) in files:
                        disk_path = os.path.join(root, os.path.basename(rel_name))
                        break
            if not os.path.exists(disk_path):
                continue

            if live_ok:
                print(f"   ├─ 🔌 Canlı Blender Köprüsü (127.0.0.1:9876) üzerinden '{rel_name}' yürütülüyor...")
                with open(disk_path, "r", encoding="utf-8", errors="replace") as f:
                    res = blender_bridge.execute_python(f.read())
                if not res.get("success"):
                    err_txt = res.get("traceback") or res.get("error") or "Bilinmeyen bpy hatası"
                    print(f"   │  ❌ Canlı Blender Hatası: {err_txt[:160]}")
                    if self._repair_script(disk_path, rel_name, user_request, err_txt):
                        with open(disk_path, "r", encoding="utf-8", errors="replace") as f:
                            res = blender_bridge.execute_python(f.read())
                if res.get("success"):
                    scene_info = res.get("scene") or {}
                    cnt = int(scene_info.get("object_count", 0))
                    object_total = max(object_total, cnt)
                    summary_lines.append(f"✅ Canlı Blender çalıştırması başarılı ({rel_name} | {cnt} nesne).")
                    prev_png = os.path.join(self.target_folder, f"{os.path.splitext(os.path.basename(rel_name))[0]}_preview.png")
                    r_res = blender_bridge.render_preview(prev_png)
                    if r_res.get("success") and os.path.exists(prev_png):
                        render_path_out = prev_png
                else:
                    all_ok = False
                    summary_lines.append(f"❌ Canlı Blender hatası ({rel_name}): {res.get('error', '')[:180]}")
            else:
                ver = blender_bridge.get_blender_version() or "Blender CLI"
                print(f"   ├─ 🧊 Headless Blender ({ver}) ile '{rel_name}' doğrulanıyor...")
                base_stem = os.path.splitext(os.path.basename(rel_name))[0]
                blend_out = os.path.join(self.target_folder, f"{base_stem}.blend")
                png_out = os.path.join(self.target_folder, f"{base_stem}_preview.png")
                res = blender_bridge.run_script_headless(disk_path, save_blend_path=blend_out, render_preview_path=png_out, timeout=75.0)
                if not res.get("success"):
                    err_txt = res.get("traceback") or res.get("error") or res.get("stderr_tail") or "Blender çıkış kodu != 0"
                    print(f"   │  ⚠️ Headless Hata tespit edildi, Şef Onarım Ajanı devreye giriyor...")
                    if self._repair_script(disk_path, rel_name, user_request, err_txt):
                        res = blender_bridge.run_script_headless(disk_path, save_blend_path=blend_out, render_preview_path=png_out, timeout=75.0)
                if res.get("success"):
                    cnt = int(res.get("object_count", 0))
                    object_total = max(object_total, cnt)
                    summary_lines.append(
                        f"✅ {res.get('blender_version', 'Blender')} headless doğrulaması geçti ({rel_name} | "
                        f"{cnt} nesne, {res.get('meshes', 0)} mesh, {res.get('lights', 0)} ışık, {res.get('cameras', 0)} kamera)."
                    )
                    if res.get("blend_path"):
                        summary_lines.append(f"📦 Sahne kaydedildi: {res['blend_path']}")
                    if res.get("render_path") and os.path.exists(res["render_path"]):
                        render_path_out = res["render_path"]
                else:
                    all_ok = False
                    summary_lines.append(f"❌ Headless Blender hatası ({rel_name}): {(res.get('error') or res.get('stderr_tail', ''))[:220]}")

        if render_path_out and os.path.exists(render_path_out):
            try:
                vis_note = gemini_service.analyze_image(
                    render_path_out,
                    custom_prompt="Bu Blender 3D önizleme renderını incele: nesneler doğru yerleşmiş mi, ışık ve kamera kadrajı düzgün mü? Kısa teknik değerlendirme yaz."
                )
                summary_lines.append(f"👁️ Blender Önizleme Görsel Analizi:\n{vis_note[:500]}")
            except Exception:
                pass

        return {
            "blender_tested": True,
            "live_bridge": live_ok,
            "is_fully_successful": all_ok,
            "object_count": object_total,
            "render_path": render_path_out,
            "summary": "\n".join(summary_lines),
        }

    def _repair_script(self, disk_path: str, rel_name: str, user_request: str, err_txt: str) -> bool:
        try:
            with open(disk_path, "r", encoding="utf-8", errors="replace") as f:
                broken_code = f.read()
            prompt = (
                f"Sen Blender 4.x/5.x bpy Python onarım uzmanısın.\n"
                f"KULLANICI İSTEĞİ: {user_request}\n"
                f"DOSYA: {rel_name}\n"
                f"BLENDER ÇALIŞMA HATASI:\n{err_txt[:1500]}\n\n"
                f"HATALI KOD:\n```python\n{broken_code[:8000]}\n```\n\n"
                f"Blender 5 uyumlu Principled BSDF soket adlarıyla ('Specular IOR Level', 'Coat Weight'), context-safe bpy API'si kullanarak bu betiği tamamen çalışır hale getir ve tek ```python``` bloğunda döndür."
            )
            repaired_raw = gemini_service.generate_with_retry(
                prompt=prompt,
                system_instruction="Sadece Blender 5 uyumlu temiz, hatasız Python bpy kodunu döndür.",
                temperature=0.1,
                allow_nim_fallback=False,
            )
            fixed_code = saf_kodu_ayikla(repaired_raw, rel_name)
            if fixed_code and "import bpy" in fixed_code:
                with open(disk_path, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                print(f"   │  🛠️ '{rel_name}' Blender hatasına göre onarıldı.")
                return True
        except Exception as exc:
            print(f"   │  ⚠️ Blender onarım hatası: {exc}")
        return False
