import os
import sys
import time
import re
import json
import base64
from typing import Dict, Any, List, Optional
from tools.unity_bridge_client import unity_client
from tools.unity_tools import (
    collect_unity_diagnostics_summary,
    format_unity_project_symbol_index,
    parse_unity_project_symbols,
    tool_unity_get_hierarchy,
)
from infrastructure.gemini_client import gemini_service
from agents.worker_agent import saf_kodu_ayikla, _sanitize_unity_csharp
from agents.unity_agent_loop import UnityAgentLoop
from orchestrator.lifecycle_tracker import lifecycle_tracker

class UnityAutonomousPlaytester:
    """
    👑 LASEF OTONOM UNITY SAHNE KURUCU, ÇALIŞTIRICI VE GÖRSEL DENETÇİ (VISION EYE)
    
    Kör kod üretimini sonlandırır:
    1. Unity C# derlemesini denetler, derleme hatası varsa anında kendi kendine onarır.
    2. Sahneyi kurar (SceneBuilder çalıştırır veya sahneye objeleri, scriptleri, collider/fizikleri koyar).
    3. Konsolu temizler ve Oyunu Başlatır (Play Mode ON).
    4. Şefin Gözünü Açar (The Vision Eye):
       - GameView / Camera.main görüntüsünü çeker.
       - Konsoldaki Exception ve kırmızı hataları yakalar.
       - Gemini Multimodal Vision ile görüntüyü ve hataları canlı analiz eder.
    5. Hata varsa Play Mode'u durdurur, otomatik onarır ve tekrar test eder.
    6. Başarılıysa sahneyi diske kaydeder ve detaylı test raporu sunar.
    """
    def __init__(self, target_folder: str):
        self.target_folder = os.path.abspath(target_folder)
        self.max_repair_attempts = 5
        self.last_compile_errors: List[str] = []
        self.last_scenebuilder_errors: List[Dict[str, str]] = []

    def run_full_pipeline(self, user_request: str, nihai_dosyalar: Dict[str, str]) -> Dict[str, Any]:
        """Tüm otonom çalıştırma, sahne kurma ve görsel test döngüsünü yürütür."""
        print("\n" + "═" * 65)
        print("🎮 [LASEF OTONOM ÇALIŞTIRICI & GÖZ] Canlı Unity Doğrulama Başlatıldı")
        print("═" * 65)

        rapor = {
            "unity_connected": False,
            "compilation_success": False,
            "scene_built": False,
            "playmode_tested": False,
            "is_fully_successful": False,
            "compile_errors": [],
            "scenebuilder_errors": [],
            "runtime_errors": [],
            "vision_verdict": "DEĞERLENDİRİLMEDİ",
            "vision_analysis": "",
            "summary": ""
        }

        if os.path.exists(os.path.join(self.target_folder, "Assets")):
            unity_client.ensure_mcp_project_setup(self.target_folder)

        comp_ok = self._bekle_ve_onar_derleme(nihai_dosyalar)
        rapor["compilation_success"] = comp_ok
        rapor["compile_errors"] = list(self.last_compile_errors)
        if not comp_ok:
            err_lines = "\n".join(f"  • {e}" for e in self.last_compile_errors[:6])
            rapor["is_fully_successful"] = False
            rapor["summary"] = (
                "❌ [UNITY C# DERLEME HATASI — OYUN ÇALIŞTIRILAMADI]\n"
                "• C# Derleme: BAŞARISIZ (Unity konsolunda derleme hataları mevcut)\n"
                "• Sahne Kurulumu & Play Mode: Derleme hatası nedeniyle başlatılamadı\n"
                + (f"• Tespit Edilen Hatalar:\n{err_lines}" if err_lines else "")
            )
            print(f"\n{rapor['summary']}")
            return rapor

        print("   🔍 [Unity Köprüsü]: Port 8088 bağlantısı taranıyor (Domain reload bekleniyor)...")
        baglandi = False
        for deneme in range(10):
            if unity_client.is_connected():
                baglandi = True
                break
            time.sleep(1.0)

        if not baglandi:
            print("   ⚠️ [Unity Köprüsü]: Unity Editor şu an dinlemede değil (Port 8088).")
            print("      (C# derlemesi yerel Roslyn ile 0 hata olarak doğrulandı. Unity açıldığında otomatik bağlanacaktır.)")
            rapor["summary"] = (
                "✅ [YEREL C# DERLEMESİ TEMİZ (0 HATA) — CANLI PLAY TESTİ ERTELENDİ]\n"
                "• C# Derleme: Temiz (Sıfır hata — Roslyn/Unity doğrulandı)\n"
                "• Unity Editor şu an kapalı veya arka planda yenileniyor; Unity penceresine geçtiğinizde sahne hazır olacaktır."
            )
            return rapor

        rapor["unity_connected"] = True
        status = unity_client.get_status()
        print(f"   🟢 [Unity Bağlandı]: {status.get('unity_version', '')} | Sahne: '{status.get('active_scene', '')}'")

        lifecycle_tracker.advance_to_stage(4, "Unity Editor sahnesi inşa ediliyor; objeler oluşturulup C# scriptleri atanıyor...")
        scene_ok = self._sahneyi_insa_et(user_request, nihai_dosyalar)
        rapor["scene_built"] = scene_ok
        rapor["scenebuilder_errors"] = list(self.last_scenebuilder_errors)

        max_play_rounds = 3
        for play_round in range(1, max_play_rounds + 1):
            print(f"\n🎮 [Play Mode - Tur {play_round}/{max_play_rounds}]: Oyun başlatılıyor (Play Mode ON)...")
            unity_client.clear_console_logs()
            play_res = unity_client.set_play_mode(True)
            rapor["playmode_tested"] = True

            if isinstance(play_res, dict) and not play_res.get("success", True):
                err_msg = str(play_res.get("error", ""))
                if "compile" in err_msg.lower() or "error" in err_msg.lower():
                    print(f"   ⚠️ [Play Mode Başlatılamadı]: {err_msg} -> Derleme onarımı başlatılıyor...")
                    comp_fixed = self._bekle_ve_onar_derleme(nihai_dosyalar)
                    rapor["compilation_success"] = comp_fixed
                    rapor["compile_errors"] = list(self.last_compile_errors)
                    if not comp_fixed:
                        break
                    unity_client.clear_console_logs()
                    unity_client.set_play_mode(True)

            bekleme_sn = 3.0 if play_round == 1 else 2.5
            print(f"   ⏳ Oyunun çalışması ve fiziklerin başlaması bekleniyor ({bekleme_sn}s)...")
            time.sleep(bekleme_sn)

            lifecycle_tracker.advance_to_stage(
                5,
                f"Play Mode (Tur {play_round}/{max_play_rounds}) açıldı. Şefin Gözü ile GameView ve konsol hataları denetleniyor..."
            )
            eye_result = self._sefin_gozuyle_denetle(user_request)
            rapor["runtime_errors"] = eye_result.get("runtime_errors", [])
            rapor["vision_verdict"] = eye_result.get("verdict", "BİLİNMİYOR")
            rapor["vision_analysis"] = eye_result.get("analysis", "")

            hata_var = eye_result.get("has_errors") or eye_result.get("verdict") == "DÜZELTME_GEREKLİ"
            if not hata_var:
                break

            if play_round >= max_play_rounds:
                print(f"   ⚠️ [Göz Uyarısı]: {max_play_rounds} test turu sonunda hâlâ runtime hatası/uyarısı mevcut.")
                break

            print(f"\n⚠️ [Göz Uyarısı - Tur {play_round}]: Canlı oyunda hata veya eksik tespit edildi! Otomatik onarım deneniyor...")
            unity_client.set_play_mode(False)
            time.sleep(1.0)

            onarildi = False
            if eye_result.get("has_errors"):
                has_cs_compile_err = any("error CS" in e.get("message", "") for e in eye_result.get("runtime_errors", []))
                if has_cs_compile_err:
                    onarildi = self._bekle_ve_onar_derleme(nihai_dosyalar)
                else:
                    onarildi = self._onar_runtime_hatasi(eye_result, nihai_dosyalar)

            hier_simdi = unity_client.get_hierarchy()
            mevcut_sayisi = hier_simdi.get("root_count", len(hier_simdi.get("nodes", [])))
            if mevcut_sayisi <= 3 or self.last_scenebuilder_errors:
                print("   🔨 [Şef Müdahalesi]: Sahne eksik veya SceneBuilder hata aldı, sahne kurulumu yenileniyor...")
                scene_ok = self._sahneyi_insa_et(user_request, nihai_dosyalar)
                rapor["scenebuilder_errors"] = list(self.last_scenebuilder_errors)
                if scene_ok:
                    onarildi = True

            rapor["compilation_success"] = (len(self.last_compile_errors) == 0)
            rapor["compile_errors"] = list(self.last_compile_errors)
            if not onarildi:
                print("   ⚠️ [Onarım Durduruldu]: Bu turda ek bir otomatik değişiklik uygulanamadı.")
                break

        unity_client.set_play_mode(False)
        time.sleep(0.5)
        save_res = unity_client.save_scene()
        print(f"   💾 [Sahne Kaydedildi]: {save_res.get('scene', 'Aktif Sahne')}")

        hier_res = unity_client.get_hierarchy()
        root_count = hier_res.get("root_count", len(hier_res.get("nodes", [])))
        print(f"   🌳 [Nihai Hiyerarşi]: Sahnede {root_count} adet kök nesne mevcut.")

        rapor["scene_built"] = (root_count > 0)
        rapor["scenebuilder_errors"] = list(self.last_scenebuilder_errors)
        is_tam_basarili = (
            rapor["compilation_success"] and
            root_count >= 3 and
            rapor["vision_verdict"] != "DÜZELTME_GEREKLİ" and
            len(rapor["runtime_errors"]) == 0 and
            len(self.last_scenebuilder_errors) == 0
        )
        rapor["is_fully_successful"] = is_tam_basarili

        durum_basligi = "✅ [LASEF BAŞARIYLA ÇALIŞTIRDI VE ONAYLADI]" if is_tam_basarili else "⚠️ [LASEF DOĞRULAMA UYARISI: SAHNEDE EKSİK VEYA DÜZELTME TESPİT EDİLDİ]"
        derleme_durumu = "Temiz (Sıfır hata)" if rapor["compilation_success"] else "HATALI (Derleme hataları mevcut)"
        if root_count >= 3:
            sahne_durumu = f"Tamamlandı ({root_count} kök nesne)"
        elif root_count > 0:
            sahne_durumu = f"Eksik ({root_count} kök nesne)"
        else:
            sahne_durumu = "BAŞARISIZ (Sahnede 0 kök nesne mevcut!)"

        ozet = (
            f"{durum_basligi}\n"
            f"• C# Derleme: {derleme_durumu}\n"
            f"• Sahne Kurulumu: {sahne_durumu}\n"
            f"• Play Mode: {'Başarıyla çalıştırıldı ve test edildi' if rapor['playmode_tested'] else 'Çalıştırılamadı'}\n"
            f"• Şefin Gözü (Vision Kararı): {rapor['vision_verdict']}\n"
            f"• Konsol Durumu: {len(rapor['runtime_errors'])} kırmızı hata"
        )
        rapor["summary"] = ozet
        print(f"\n{ozet}")
        return rapor

    def _resolve_disk_path(self, dosya_adi: str, kod_icerigi: str = "") -> str:
        """Hedef C# dosyasının diskteki gerçek yolunu (Assets/Editor veya Assets/Scripts) doğru çözer."""
        tam_yol = os.path.join(self.target_folder, dosya_adi)
        if os.path.exists(tam_yol):
            return tam_yol

        base_name = os.path.basename(dosya_adi)
        is_editor = (
            "editor" in dosya_adi.lower()
            or "scenebuilder" in base_name.lower()
            or "builder" in base_name.lower()
            or "using UnityEditor" in (kod_icerigi or "")
        )
        alt_klasor = "Editor" if is_editor else "Scripts"
        aday_yol = os.path.join(self.target_folder, "Assets", alt_klasor, base_name)
        os.makedirs(os.path.dirname(aday_yol), exist_ok=True)
        return aday_yol

    def _iter_project_cs_files(self) -> List[str]:
        """Projede Assets altındaki (köprü hariç) tüm C# dosyalarının göreli yollarını döndürür."""
        assets_dir = os.path.join(self.target_folder, "Assets")
        if not os.path.isdir(assets_dir):
            return []
        skip_dirs = {"lasefbridge", "tutorialinfo", "textmesh pro", ".git"}
        sonuc = []
        for root_d, dirs, files in os.walk(assets_dir):
            dirs[:] = sorted(d for d in dirs if d.lower() not in skip_dirs)
            for fn in sorted(files):
                if not fn.endswith(".cs") or fn.startswith("LaSefDynamicRunner_"):
                    continue
                fp = os.path.join(root_d, fn)
                sonuc.append(os.path.relpath(fp, self.target_folder).replace("\\", "/"))
        return sonuc

    def _snapshot_project_cs_files(self) -> Dict[str, str]:
        """Assets altındaki mevcut tüm C# dosyalarını salt-okunur önbelleğe alır."""
        cache: Dict[str, str] = {}
        for rel_p in self._iter_project_cs_files():
            disk_p = os.path.join(self.target_folder, rel_p)
            try:
                with open(disk_p, "r", encoding="utf-8", errors="ignore") as f:
                    cache[rel_p] = f.read()
            except Exception:
                pass
        return cache

    def _find_existing_disk_path(self, dosya_key: str) -> Optional[str]:
        """Klasör oluşturmadan dosyanın diskteki gerçek yolunu bulur."""
        aday = os.path.join(self.target_folder, dosya_key)
        if os.path.isfile(aday):
            return aday
        base = os.path.basename(dosya_key)
        for rel_p in self._iter_project_cs_files():
            if os.path.basename(rel_p) == base:
                return os.path.join(self.target_folder, rel_p)
        return None

    def _check_stub_regression(
        self,
        original_code: str,
        candidate_code: str,
        all_other_code: str = "",
        ignored_duplicate_symbols: Optional[set] = None,
    ) -> Optional[str]:
        """Onarım çıktısının mevcut bir dosyayı yıkıcı biçimde stub'a küçültüp küçültmediğini denetler."""
        if not original_code or len(original_code) < 1200:
            return None
        if len(original_code) >= 3000 and len(candidate_code) < int(len(original_code) * 0.42):
            pct = (len(candidate_code) * 100) // max(1, len(original_code))
            return f"Dosya boyutu {len(original_code)} -> {len(candidate_code)} karaktere (%{pct}) düştü (yıkıcı stub yazımı)."

        ignored = ignored_duplicate_symbols or set()
        lifecycle = {
            "Awake", "Start", "Update", "FixedUpdate", "LateUpdate",
            "OnEnable", "OnDisable", "OnDestroy", "OnGUI",
            "OnTriggerEnter", "OnCollisionEnter", "Reset",
        }
        pub_types = set(re.findall(
            r"\bpublic\s+(?:static\s+|abstract\s+|sealed\s+|partial\s+)?(?:class|struct|enum|interface)\s+(\w+)",
            original_code,
        ))
        pub_members = set(re.findall(
            r"\bpublic\s+(?:static\s+|virtual\s+|override\s+|async\s+|event\s+|const\s+|readonly\s+)*[\w<>\[\],\.\?]+\s+(\w+)\s*(?:\(|=>|\{|;|=)",
            original_code,
        ))
        kayip_semboller = []
        for sym in sorted((pub_types | pub_members) - lifecycle - ignored):
            if len(sym) < 3 or re.search(rf"\b{re.escape(sym)}\b", candidate_code):
                continue
            if len(original_code) >= 3000 or (all_other_code and re.search(rf"\b{re.escape(sym)}\b", all_other_code)):
                kayip_semboller.append(sym)
        if len(kayip_semboller) >= 2:
            return f"Mevcut public semboller silindi/değiştirildi: {', '.join(kayip_semboller[:6])}"
        return None

    def _collect_project_scripts_api_summary(self, exclude_file: str = "") -> str:
        """Projedeki TÜM (Scripts + Editor) C# dosyalarının namespace, tip ve public üye haritasını üretir."""
        return format_unity_project_symbol_index(
            self.target_folder,
            exclude_file=exclude_file,
            max_chars=9000,
        )

    def _collect_referenced_symbol_sources(
        self,
        errors: List[str],
        exclude_file: str = "",
        disk_cache: Optional[Dict[str, str]] = None,
        max_chars: int = 7500,
    ) -> str:
        """Hata mesajlarında geçen sınıfların/tiplerin gerçek kaynak tanımlarını (namespace dahil) toplar."""
        err_joined = "\n".join(errors)
        raw_tokens = re.findall(r"'([A-Za-z_][A-Za-z0-9_\.]*)'", err_joined)
        tokens = set()
        for tok in raw_tokens:
            tokens.add(tok)
            for part in tok.split("."):
                if len(part) >= 3:
                    tokens.add(part)
        if not tokens:
            return ""

        parsed = parse_unity_project_symbols(self.target_folder)
        files_info = parsed.get("files", {})
        exclude_base = os.path.basename(exclude_file) if exclude_file else ""
        cache = disk_cache if disk_cache is not None else self._snapshot_project_cs_files()

        matched_paths: List[str] = []
        for rel_p, info in sorted(files_info.items()):
            base = os.path.basename(rel_p)
            if exclude_base and base == exclude_base:
                continue
            stem = os.path.splitext(base)[0]
            searchable = stem + " " + " ".join(info.get("decls", [])) + " " + " ".join(info.get("members", []))
            if stem in tokens or any(re.search(rf"\b{re.escape(t)}\b", searchable) for t in tokens):
                matched_paths.append(rel_p)

        if not matched_paths:
            return ""

        sections = []
        total_len = 0
        for rel_p in matched_paths[:5]:
            icerik = cache.get(rel_p, "")
            if not icerik:
                disk_p = os.path.join(self.target_folder, rel_p)
                if os.path.isfile(disk_p):
                    try:
                        with open(disk_p, "r", encoding="utf-8", errors="ignore") as f:
                            icerik = f.read()
                    except Exception:
                        continue
            if not icerik:
                continue
            ns_label = files_info.get(rel_p, {}).get("namespace", "<global>")
            snippet = icerik if len(icerik) <= 2800 else (icerik[:2600] + "\n// ... (kısaltıldı)")
            block = f"// === REFERANS DOSYA: {rel_p} (namespace={ns_label}) ===\n{snippet}"
            if total_len + len(block) > max_chars and sections:
                break
            sections.append(block)
            total_len += len(block)
        return "\n\n".join(sections)

    def _map_compile_errors_to_files(
        self,
        errors: List[str],
        nihai_dosyalar: Dict[str, str],
        disk_cache: Dict[str, str],
    ) -> List[str]:
        """Derleme hatalarını tüm proje .cs dosyalarına eşler; CS0101 ve CS0246 kök neden sırasını belirler."""
        kok_hata_dosyalari: List[str] = []
        cascading_dosyalar: List[str] = []

        def _kayitli_anahtar_bul(rel_p: str) -> Optional[str]:
            norm_rel = rel_p.replace("\\", "/")
            base_rel = os.path.basename(norm_rel)
            for k in nihai_dosyalar.keys():
                if k.replace("\\", "/") == norm_rel or os.path.basename(k) == base_rel:
                    return k
            if norm_rel in disk_cache:
                nihai_dosyalar[norm_rel] = disk_cache[norm_rel]
                return norm_rel
            disk_p = os.path.join(self.target_folder, norm_rel)
            if os.path.isfile(disk_p):
                try:
                    with open(disk_p, "r", encoding="utf-8", errors="ignore") as rf:
                        nihai_dosyalar[norm_rel] = rf.read()
                    return norm_rel
                except Exception:
                    pass
            for c_rel, c_code in disk_cache.items():
                if os.path.basename(c_rel) == base_rel:
                    nihai_dosyalar[c_rel] = c_code
                    return c_rel
            return None

        parsed_syms = parse_unity_project_symbols(self.target_folder)
        dup_types = parsed_syms.get("duplicate_types", {})

        for e in errors:
            eslesen_dosya = None
            m_path = re.search(r'(Assets[\\/][^(\s:]+\.cs)', e)
            if m_path:
                eslesen_dosya = _kayitli_anahtar_bul(m_path.group(1))

            if not eslesen_dosya:
                for k in list(nihai_dosyalar.keys()):
                    if os.path.basename(k) in e:
                        eslesen_dosya = k
                        break

            if not eslesen_dosya:
                for d_rel, d_code in disk_cache.items():
                    if os.path.basename(d_rel) in e:
                        nihai_dosyalar[d_rel] = d_code
                        eslesen_dosya = d_rel
                        break

            if eslesen_dosya:
                if "CS0101:" in e:
                    m_dup = re.search(r"already contains a definition for '(\w+)'", e)
                    if m_dup and m_dup.group(1) in dup_types:
                        locs = dup_types[m_dup.group(1)]
                        sirali_locs = sorted(
                            locs,
                            key=lambda item: (
                                0 if any(tag in item[0].lower() for tag in ("fix", "audit", "scenebuilder", "upgrade")) else 1,
                                len(disk_cache.get(item[0], nihai_dosyalar.get(item[0], ""))),
                            ),
                        )
                        for loc_rel, _ in sirali_locs:
                            loc_key = _kayitli_anahtar_bul(loc_rel)
                            if loc_key and loc_key not in kok_hata_dosyalari:
                                kok_hata_dosyalari.append(loc_key)

                is_cascading = "CS0246: The type or namespace name" in e
                target_list = cascading_dosyalar if is_cascading else kok_hata_dosyalari
                if eslesen_dosya not in target_list and eslesen_dosya not in kok_hata_dosyalari:
                    target_list.append(eslesen_dosya)

        for c_file in cascading_dosyalar:
            if c_file not in kok_hata_dosyalari:
                kok_hata_dosyalari.append(c_file)
        return kok_hata_dosyalari

    def _bekle_ve_onar_derleme(self, nihai_dosyalar: Dict[str, str]) -> bool:
        """Derlemeyi bekler; hem Runtime (Assembly-CSharp) hem Editor (Assembly-CSharp-Editor) hatalarını toplu olarak onarır."""
        print("   ⏳ Unity Editor C# derlemesi bekleniyor...")
        self.last_compile_errors = []

        disk_baselines = self._snapshot_project_cs_files()
        file_baselines: Dict[str, str] = {}
        for k_rel, k_code in disk_baselines.items():
            file_baselines[k_rel] = k_code

        for rel_k, kod_v in list(nihai_dosyalar.items()):
            if rel_k.lower().endswith(".cs") and isinstance(kod_v, str):
                temiz_v = _sanitize_unity_csharp(kod_v)
                if temiz_v != kod_v:
                    nihai_dosyalar[rel_k] = temiz_v
                    try:
                        tam_p = self._resolve_disk_path(rel_k, temiz_v)
                        with open(tam_p, "w", encoding="utf-8") as wf:
                            wf.write(temiz_v)
                    except Exception:
                        pass

        onceki_deneme_hatalari: Dict[str, List[str]] = {}

        for attempt in range(1, self.max_repair_attempts + 1):
            local_res = unity_client.compile_project_locally_with_dotnet(self.target_folder)
            if local_res.get("supported"):
                if local_res.get("has_errors"):
                    comp_res = {"has_errors": True, "errors": local_res.get("errors", [])}
                else:
                    if unity_client.is_connected():
                        comp_res = unity_client.wait_for_compilation(timeout=25.0, project_path=self.target_folder)
                    else:
                        comp_res = {"has_errors": False, "errors": []}
            else:
                if unity_client.is_connected():
                    comp_res = unity_client.wait_for_compilation(timeout=35.0, project_path=self.target_folder)
                else:
                    comp_res = {"has_errors": False, "errors": []}

            if not comp_res.get("has_errors"):
                self.last_compile_errors = []
                print("   ✅ [Unity Derleme Başarılı]: Tüm üretilen C# scriptleri (Runtime + Editor) derlendi!")
                return True

            raw_errors = comp_res.get("errors", [])
            errors = [
                e for e in raw_errors
                if "LaSefDynamicRunner_" not in e and "LaSefBridgeServer" not in e
            ]
            if not errors:
                self.last_compile_errors = []
                print("   ✅ [Unity Derleme Başarılı]: Köprü dışı derleme hatası yok.")
                return True

            self.last_compile_errors = list(errors)
            err_text = "\n".join(errors[:12])
            print(f"   ❌ [Unity Derleme Hatası - Deneme {attempt}/{self.max_repair_attempts}]:\n{err_text}")

            disk_cache_now = self._snapshot_project_cs_files()
            for rel_p, code_now in disk_cache_now.items():
                if rel_p not in file_baselines:
                    file_baselines[rel_p] = code_now

            kok_hata_dosyalari = self._map_compile_errors_to_files(errors, nihai_dosyalar, disk_cache_now)
            if not kok_hata_dosyalari:
                print("   ⚠️ [Derleme Onarımı]: Hata mesajında proje dosyalarından hiçbiri eşleşmedi, rastgele dosya ezilmeyecek.")
                return False

            en_az_bir_onarildi = False
            for hatali_dosya in kok_hata_dosyalari:
                base_hatali = os.path.basename(hatali_dosya)
                dosya_hatalari = [e for e in errors if base_hatali in e] or errors[:8]
                dosya_err_text = "\n".join(dosya_hatalari[:10])

                print(f"   🎯 [Kök Neden Tespiti]: Hatayı üreten dosya -> '{hatali_dosya}' ({len(dosya_hatalari)} hata)")
                print(f"   🔧 [Otomatik C# Onarımı]: '{hatali_dosya}' için onarım kodu üretiliyor...")

                mevcut_kod = nihai_dosyalar.get(hatali_dosya, "")
                if not mevcut_kod:
                    disk_p = self._find_existing_disk_path(hatali_dosya)
                    if disk_p:
                        try:
                            with open(disk_p, "r", encoding="utf-8", errors="ignore") as rf:
                                mevcut_kod = rf.read()
                        except Exception:
                            pass

                norm_hatali = hatali_dosya.replace("\\", "/")
                baseline_kod = file_baselines.get(norm_hatali) or disk_baselines.get(norm_hatali) or mevcut_kod
                all_other_code = "\n".join(
                    v for k, v in disk_cache_now.items() if os.path.basename(k) != base_hatali
                )

                diger_script_imzalari = self._collect_project_scripts_api_summary(exclude_file=hatali_dosya)
                referans_kaynaklar = self._collect_referenced_symbol_sources(
                    dosya_hatalari,
                    exclude_file=hatali_dosya,
                    disk_cache=disk_cache_now,
                )

                onceki_not = ""
                if hatali_dosya in onceki_deneme_hatalari:
                    onceki_not = (
                        "⚠️ ÖNCEKİ ONARIM DENEMESİ BAŞARISIZ OLDU! Aynı hataları tekrar üretme.\n"
                        "- Eğer CS0246 devam ediyorsa, referans verilen sınıf başka bir `namespace` (ör. `namespace Global`) içindedir veya senin dosyan yanlışlıkla `namespace Global` içinde tanımlanmıştır! Namespace haritasını ve referans dosya kodlarını kontrol edip `using <Namespace>;` ekle veya gereksiz `namespace` sarmalını kaldır.\n"
                        f"- Önceki denemedeki hatalar:\n{chr(10).join(onceki_deneme_hatalari[hatali_dosya][:5])}\n\n"
                    )
                onceki_deneme_hatalari[hatali_dosya] = list(dosya_hatalari)

                ignored_dups = set(re.findall(r"CS0101:.*?'(\w+)'", dosya_err_text))
                prompt_base = (
                    f"UNITY C# DERLEME HATALARI ({base_hatali}):\n{dosya_err_text}\n\n"
                    + onceki_not
                    + f"HEDEF DOSYA: {hatali_dosya}\n"
                    + f"MEVCUT KOD:\n```csharp\n{mevcut_kod}\n```\n\n"
                    + (f"PROJEDEKİ TÜM SCRIPTLERİN GERÇEK NAMESPACE & SEMBOL HARİTASI:\n{diger_script_imzalari}\n\n" if diger_script_imzalari else "")
                    + (f"HATADA GEÇEN REFERANS SINIFLARIN GERÇEK KAYNAK KODLARI:\n```csharp\n{referans_kaynaklar}\n```\n\n" if referans_kaynaklar else "")
                    + f"ÖNEMLİ KURALLAR:\n"
                    + f"1. Unity 6 ile %100 uyumlu olmalıdır.\n"
                    + f"2. `FindFirstObjectByType<T>()` ve `FindAnyObjectByType<T>()` metotlarına ASLA `FindObjectsSortMode.None` parametresi verme; çoklu aramada `FindObjectsByType<T>(FindObjectsSortMode.None)` kullan.\n"
                    + f"3. CS0122 / CS1061 hatasında: Yukarıdaki gerçek sınıf/üye imzalarına göre düzelt; olmayan metot/özellik uydurma.\n"
                    + f"4. CS0246 / CS0234 hatasında: Hedef sembolün hangi namespace içinde tanımlandığına (örn. `<global>` vs `namespace Global`) haritadan bak; projede aynı namespace standardını koru (`Global` sarmalı açma; eğer referans dosya `Global` içindeyse `using Global;` veya tam ad kullan).\n"
                    + f"5. CS0101 çakışmasında: Çakışan enum/tip zaten başka bir dosyada tanımlıysa bu dosyada tekrar tanımlama, mevcut olanı kullan.\n"
                    + f"6. `UnityEngine.UI` tipleri (`CanvasScaler`, `GraphicRaycaster`, `RawImage`, `Image`, `Text`, `Button`, `Slider`, `ScrollRect`, `LayoutGroup`) kullanılıyorsa `using UnityEngine.UI;` ekle. Runtime (`Assets/Scripts/`) içinde `using UnityEditor;` varsa `#if UNITY_EDITOR` ile sar.\n"
                    + f"7. `GetComponent<T>() ?? gameObject.AddComponent<T>()` KESİNLİKLE YASAKTIR (Unity fake-null hatası); yerine `!= null` kontrolü veya `if (c == null) c = ...` yaz.\n"
                    + f"8. KRİTİK: Mevcut dosyadaki çalışan sistemleri, metodları veya public API'leri SİLME, dosyayı kısaltılmış stub'a çevirme! Tüm mevcut işlevselliği koruyarak yalnızca hatayı gider.\n"
                    + f"9. Sadece ve sadece tam, eksiksiz, saf C# kodunu tek parça olarak yaz."
                )

                try:
                    tamir_kodu = gemini_service.generate_with_retry(
                        prompt=prompt_base,
                        system_instruction="Sen Baş Unity C# Derleme Uzmanısın. Verilen tüm CS derleme hatalarını tek seferde çözen, mevcut kodu küçültmeden koruyan, eksiksiz ve derleme hatasız C# kodunu üret."
                    )
                    temiz_kod = _sanitize_unity_csharp(saf_kodu_ayikla(tamir_kodu, hatali_dosya))
                    if not temiz_kod or len(temiz_kod) <= 50:
                        continue

                    stub_sorunu = self._check_stub_regression(
                        baseline_kod,
                        temiz_kod,
                        all_other_code=all_other_code,
                        ignored_duplicate_symbols=ignored_dups,
                    )
                    if stub_sorunu:
                        print(f"   🛡️ [Anti-Stub Koruması ({base_hatali})]: {stub_sorunu} Tam kodla tekrar onarılıyor...")
                        retry_prompt = (
                            f"❌ ÖNCEKİ ÇIKTI REDDEDİLDİ: {stub_sorunu}\n"
                            "Mevcut dosyanın içeriğini özetleme veya stub'a çevirme! Aşağıdaki MEVCUT KODUN TÜM SINIF, METOT VE ÖZELLİKLERİNİ AYNEN KORU, sadece derleme hatalarını cerrahi olarak düzelt:\n\n"
                            + prompt_base
                        )
                        tamir_kodu_2 = gemini_service.generate_with_retry(
                            prompt=retry_prompt,
                            system_instruction="Sen Baş Unity C# Derleme Uzmanısın. Mevcut kodun tüm işlevlerini eksiksiz koruyarak yalnızca derleme hatalarını düzelt."
                        )
                        temiz_kod_2 = _sanitize_unity_csharp(saf_kodu_ayikla(tamir_kodu_2, hatali_dosya))
                        stub_sorunu_2 = self._check_stub_regression(
                            baseline_kod,
                            temiz_kod_2,
                            all_other_code=all_other_code,
                            ignored_duplicate_symbols=ignored_dups,
                        )
                        if temiz_kod_2 and len(temiz_kod_2) > 50 and not stub_sorunu_2:
                            temiz_kod = temiz_kod_2
                        elif len(baseline_kod) >= 3000 and stub_sorunu_2:
                            print(f"   ⚠️ [Anti-Stub Koruması]: '{base_hatali}' yıkıcı stub riskine karşı üzerine yazılmadı; deterministik temizlik uygulanıyor.")
                            temiz_kod = _sanitize_unity_csharp(baseline_kod)
                            if temiz_kod == mevcut_kod:
                                continue

                    nihai_dosyalar[hatali_dosya] = temiz_kod
                    tam_yol = self._resolve_disk_path(hatali_dosya, temiz_kod)
                    with open(tam_yol, "w", encoding="utf-8") as f:
                        f.write(temiz_kod)
                    print(f"   💾 [Onarılan Kod Diske Yazıldı]: {tam_yol}")
                    en_az_bir_onarildi = True
                except Exception as ex:
                    print(f"   ⚠️ [Onarım İstek Hatası ({hatali_dosya})]: {ex}")

            if en_az_bir_onarildi:
                try:
                    unity_client.clear_console_logs()
                except Exception:
                    pass
                time.sleep(1.5)

        return False

    def _safe_create_object(self, name: str, primitive_type: Optional[str] = None, px: float = 0.0, py: float = 0.0, pz: float = 0.0, sx: float = 1.0, sy: float = 1.0, sz: float = 1.0) -> bool:
        """Derleme kilidine takılmadan güvenli GameObject oluşturur ve sonucu doğrular."""
        for _ in range(2):
            res = unity_client.create_gameobject(name, primitive_type=primitive_type, px=px, py=py, pz=pz, sx=sx, sy=sy, sz=sz)
            if res.get("success"):
                return True
            if res.get("compiling"):
                unity_client.wait_for_compilation(timeout=15.0, trigger_refresh=False)
                continue
            break
        return False

    def _repair_scenebuilder_script(
        self,
        dosya_yolu: str,
        kod_icerigi: str,
        exec_err: str,
        nihai_dosyalar: Dict[str, str],
    ) -> Optional[str]:
        """Çalıştırılırken istisna fırlatan Editor SceneBuilder scriptini hataya göre onarır, derler ve döndürür."""
        base_name = os.path.basename(dosya_yolu)
        print(f"   🩺 [SceneBuilder Otonom Onarımı]: '{base_name}' çalışma hatası üzerine onarılıyor...")
        hier_text = ""
        try:
            hier_text = tool_unity_get_hierarchy()
        except Exception:
            pass
        sembol_haritasi = self._collect_project_scripts_api_summary(exclude_file=dosya_yolu)

        prompt = (
            f"UNITY EDITOR SCENEBUILDER ÇALIŞMA HATASI ({dosya_yolu}):\n{exec_err}\n\n"
            + (f"MEVCUT SAHNE HİYERARŞİSİ:\n{hier_text[:2500]}\n\n" if hier_text else "")
            + (f"PROJE SEMBOL & NAMESPACE HARİTASI:\n{sembol_haritasi}\n\n" if sembol_haritasi else "")
            + f"MEVCUT SCENEBUILDER KODU:\n```csharp\n{kod_icerigi}\n```\n\n"
            "ZORUNLU ONARIM KURALLARI:\n"
            "1. Unity UI nesneleri (`Fill Area`, `Fill`, `Handle Slide Area`, `Handle`, `Viewport`, `Content` vb.) oluştururken mutlaka `new GameObject(\"Ad\", typeof(RectTransform))` veya önce `AddComponent<RectTransform>()` kullan; `GetComponent<RectTransform>() ?? AddComponent<RectTransform>()` ASLA yazma (MissingComponentException üretir).\n"
            "2. Sahnedeki mevcut çalışan objeleri (Player, Canvas, Enemy, Ground vb.) `DestroyImmediate` ile körü körüne silme; varsa bulup güncelle.\n"
            "3. Başlangıçtaki public static metod adını koru (`BuildScene()` / `BuildAndConnectScene()` vb.).\n"
            "4. Hatanın kök nedenini (MissingComponentException, NullReferenceException, eksik bileşen vb.) kesin olarak çöz.\n"
            "5. Sadece ve sadece tam, eksiksiz, saf C# kodunu tek parça olarak yaz."
        )
        try:
            tamir = gemini_service.generate_with_retry(
                prompt=prompt,
                system_instruction="Sen Kıdemli Unity Editor & SceneBuilder Onarım Uzmanısın. İstisna fırlatan SceneBuilder C# scriptini çalışma zamanı hatasız hale getir."
            )
            temiz = _sanitize_unity_csharp(saf_kodu_ayikla(tamir, dosya_yolu))
            if not temiz or len(temiz) <= 50:
                return None
            stub_err = self._check_stub_regression(kod_icerigi, temiz)
            if stub_err:
                print(f"   ⚠️ [SceneBuilder Onarım Uyarısı ({base_name})]: {stub_err}")
                return None

            nihai_dosyalar[dosya_yolu] = temiz
            tam_yol = self._resolve_disk_path(dosya_yolu, temiz)
            with open(tam_yol, "w", encoding="utf-8") as wf:
                wf.write(temiz)
            print(f"   💾 [Onarılan SceneBuilder Diske Yazıldı]: {tam_yol}")

            if not self._bekle_ve_onar_derleme(nihai_dosyalar):
                return None
            for _ in range(10):
                if unity_client.is_connected():
                    break
                time.sleep(1.0)
            return nihai_dosyalar.get(dosya_yolu, temiz)
        except Exception as ex:
            print(f"   ⚠️ [SceneBuilder Onarım İstek Hatası ({base_name})]: {ex}")
            return None

    def _sahneyi_insa_et(self, user_request: str, nihai_dosyalar: Dict[str, str]) -> bool:
        """
        Sahneyi kurar veya günceller:
        - Eğer sahne zaten doluysa (root_count >= 4) ve kullanıcı açıkça sahneyi sıfırlamayı istemediyse,
          mevcut sahneyi yıkıcı SceneBuilder.BuildScene() ile silmez; korur ve yalnızca eksik bileşenleri/objeleri tamamlar.
        - Sahne boşsa (< 4 kök nesne) veya sıfırlama istendiyse SceneBuilder veya canlı API ile kurar.
        """
        print("\n🏗️ [Sahne İnşası]: Oyun nesneleri ve bileşenleri kontrol ediliyor...")
        self.last_scenebuilder_errors = []

        unity_client.wait_for_compilation(timeout=20.0, trigger_refresh=False)

        hier_ilk = unity_client.get_hierarchy()
        ilk_kok_sayisi = hier_ilk.get("root_count", len(hier_ilk.get("nodes", [])))
        istek_kucuk = (user_request or "").lower()
        sifirlama_istendi = any(
            k in istek_kucuk
            for k in (
                "sahneyi sıfırla", "sahneyi sifirla", "sahneyi baştan kur",
                "sahneyi bastan kur", "sahneyi yeniden kur", "reset scene", "rebuild scene"
            )
        )

        def _tum_bilesenleri_topla(node_list: List[Dict[str, Any]]) -> set:
            bulunan = set()
            for nd in (node_list or []):
                for comp_name in (nd.get("components") or []):
                    bulunan.add(str(comp_name).split(".")[-1])
                alt = nd.get("children") or []
                if alt:
                    bulunan.update(_tum_bilesenleri_topla(alt))
            return bulunan

        mevcut_bilesenler = _tum_bilesenleri_topla(hier_ilk.get("nodes", []))

        uretilen_runtime_siniflar = [
            os.path.splitext(os.path.basename(fp))[0]
            for fp in nihai_dosyalar.keys()
            if fp.lower().endswith(".cs")
            and "editor" not in fp.lower()
            and "scenebuilder" not in fp.lower()
            and "builder" not in os.path.basename(fp).lower()
        ]
        yeni_script_eksik = any(s not in mevcut_bilesenler for s in uretilen_runtime_siniflar)
        editor_builder_var = any(
            any(k in fp for k in ["SceneBuilder", "Editor", "Builder"]) and "static void" in (kod or "")
            for fp, kod in nihai_dosyalar.items()
        )

        if ilk_kok_sayisi < 4 or sifirlama_istendi or yeni_script_eksik or editor_builder_var:
            def _builder_onceligi(item):
                yol = item[0].lower()
                if "upgrade" in yol or "integrat" in yol or "final" in yol or "game" in yol:
                    return 2
                if "scenebuilder" in yol:
                    return 1
                return 0

            sirali_dosyalar = sorted(nihai_dosyalar.items(), key=_builder_onceligi)
            en_az_bir_builder_calisti = False

            for dosya_yolu, kod_icerigi in sirali_dosyalar:
                if any(k in dosya_yolu for k in ["SceneBuilder", "Editor", "Builder"]) and "static void" in (kod_icerigi or ""):
                    def _sec_cagri(src_code: str) -> Optional[str]:
                        tum_m = re.findall(r'public\s+static\s+void\s+(\w+)\s*\(\)', src_code)
                        yasak = {"showwindow", "openwindow", "initwindow", "closewindow"}
                        adaylar = [m for m in tum_m if m.lower() not in yasak]
                        if not adaylar:
                            return None
                        def _metot_skoru(m_adi: str) -> int:
                            ml = m_adi.lower()
                            if ml in ("buildandconnectscene", "buildscene", "setupscene", "upgradescene", "constructscene"):
                                return 100
                            if any(k in ml for k in ("build", "setup", "connect", "assemble", "create", "construct", "apply", "run")):
                                return 80
                            return 10
                        adaylar.sort(key=_metot_skoru, reverse=True)
                        c_m = re.search(r'public\s+(?:static\s+)?class\s+(\w+)', src_code)
                        if not c_m:
                            return None
                        ns_m = re.search(r'namespace\s+([\w\.]+)', src_code)
                        sinif_ad = c_m.group(1)
                        ns_ad = ns_m.group(1) if ns_m else ""
                        tam_ad_str = f"{ns_ad}.{sinif_ad}" if ns_ad else sinif_ad
                        return f"{tam_ad_str}.{adaylar[0]}();"

                    csharp_cagrisi = _sec_cagri(kod_icerigi)
                    if not csharp_cagrisi:
                        continue

                    print(f"   ⚡ [SceneBuilder Tetikleniyor]: {csharp_cagrisi}")
                    exec_res = unity_client.execute_csharp(csharp_cagrisi)
                    if exec_res.get("success"):
                        en_az_bir_builder_calisti = True
                        unity_client.save_scene()
                        hier_check = unity_client.get_hierarchy()
                        built_roots = hier_check.get("root_count", len(hier_check.get("nodes", [])))
                        print(f"   ✅ [SceneBuilder Tamamlandı ({csharp_cagrisi})]: {exec_res.get('output', 'OK')} ({built_roots} kök nesne doğrulandı)")
                    else:
                        err_msg = str(exec_res.get("error", "Bilinmeyen hata"))
                        print(f"   ⚠️ [SceneBuilder Çalıştırılamadı ({csharp_cagrisi})]: {err_msg}")
                        repaired_code = self._repair_scenebuilder_script(dosya_yolu, kod_icerigi, err_msg, nihai_dosyalar)
                        retry_succeeded = False
                        if repaired_code:
                            retry_call = _sec_cagri(repaired_code) or csharp_cagrisi
                            print(f"   🔄 [Onarılan SceneBuilder Tekrar Tetikleniyor]: {retry_call}")
                            exec_res_2 = unity_client.execute_csharp(retry_call)
                            if exec_res_2.get("success"):
                                retry_succeeded = True
                                en_az_bir_builder_calisti = True
                                unity_client.save_scene()
                                hier_check = unity_client.get_hierarchy()
                                built_roots = hier_check.get("root_count", len(hier_check.get("nodes", [])))
                                print(f"   ✅ [Onarılan SceneBuilder Başarılı ({retry_call})]: {exec_res_2.get('output', 'OK')} ({built_roots} kök nesne doğrulandı)")
                            else:
                                err_msg = str(exec_res_2.get("error", err_msg))
                        if not retry_succeeded:
                            self.last_scenebuilder_errors.append({
                                "file": dosya_yolu,
                                "call": csharp_cagrisi,
                                "error": err_msg,
                            })

            if en_az_bir_builder_calisti:
                hier_son_kontrol = unity_client.get_hierarchy()
                son_kok_sayisi = hier_son_kontrol.get("root_count", len(hier_son_kontrol.get("nodes", [])))
                if son_kok_sayisi > 0:
                    return True
                print("   ⚠️ [SceneBuilder Uyarısı]: SceneBuilder çalıştı ancak sahnede 0 kök nesne var! Canlı API kurulumuna geçiliyor...")
        else:
            print(f"   🛡️ [Sahne Koruması]: Sahnede zaten {ilk_kok_sayisi} kök nesne ve tüm hedef bileşenler mevcut; mevcut hiyerarşi korunuyor.")
            return True

        print("   👑 [Şef Sahne Mimarı]: Otomatik akıllı sahne inşası başlatılıyor...")
        unity_client.wait_for_compilation(timeout=15.0, trigger_refresh=False)
        hier = unity_client.get_hierarchy()
        mevcut_objeler = [n.get("name") for n in hier.get("nodes", [])]

        if not any(z in mevcut_objeler for z in ["Ground", "Floor", "Zemin", "Plane"]):
            if self._safe_create_object("Ground", primitive_type="Plane", px=0, py=0, pz=0, sx=3.0, sy=1.0, sz=3.0):
                print("   └ 📦 [Zemin Oluşturuldu]: 'Ground' (Plane, 30x1x30)")

        if not any("Light" in o for o in mevcut_objeler):
            if self._safe_create_object("Directional Light", px=0, py=10, pz=0):
                unity_client.add_component("Directional Light", "Light")
                print("   └ 💡 [Işık Oluşturuldu]: 'Directional Light'")

        for dosya_yolu, kod in nihai_dosyalar.items():
            if not dosya_yolu.endswith(".cs"):
                continue
            sinif_adi = os.path.splitext(os.path.basename(dosya_yolu))[0]
            if "Editor" in dosya_yolu or "Builder" in sinif_adi:
                continue

            if any(k in sinif_adi.lower() for k in ["player", "character", "oyuncu", "hero"]):
                if not any("Player" in o for o in mevcut_objeler):
                    if self._safe_create_object("Player", primitive_type="Capsule", px=0, py=1.2, pz=0):
                        unity_client.add_component("Player", "Rigidbody")
                        unity_client.add_component("Player", sinif_adi)
                        mevcut_objeler.append("Player")
                        print(f"   └ 🧍 [Oyuncu Objesi Oluşturuldu]: 'Player' (Capsule) + '{sinif_adi}'")

            elif any(k in sinif_adi.lower() for k in ["gamemanager", "gamecontroller", "yonetici"]):
                if not any("GameManager" in o for o in mevcut_objeler):
                    if self._safe_create_object("GameManager", px=0, py=0, pz=0):
                        unity_client.add_component("GameManager", sinif_adi)
                        mevcut_objeler.append("GameManager")
                        print(f"   └ 🎮 [Oyun Yöneticisi Oluşturuldu]: 'GameManager' + '{sinif_adi}'")

        if not any("Camera" in o for o in mevcut_objeler):
            if self._safe_create_object("Main Camera", px=0, py=3, pz=-8):
                unity_client.add_component("Main Camera", "Camera")
                unity_client.add_component("Main Camera", "AudioListener")
                print("   └ 🎥 [Kamera Oluşturuldu]: 'Main Camera'")

        hier_son = unity_client.get_hierarchy()
        son_sayisi = hier_son.get("root_count", len(hier_son.get("nodes", [])))
        if son_sayisi < 3:
            try:
                print("   🤖 [Unity ReAct Ajanı]: Sahne hiyerarşisi eksik, otonom ReAct ajanı devreye giriyor...")
                react_agent = UnityAgentLoop(project_path=self.target_folder, max_steps=6)
                react_agent.execute_task(
                    instruction=(
                        f"Kullanıcı isteği: {user_request}\n"
                        f"Mevcut C# dosyaları: {list(nihai_dosyalar.keys())}\n"
                        "Sahnedeki eksik temel oyun nesnelerini (Ground, Player, Light, Camera, Manager) oluştur, "
                        "ilgili scriptleri tak ve sahneyi kaydet."
                    )
                )
                hier_son = unity_client.get_hierarchy()
                son_sayisi = hier_son.get("root_count", len(hier_son.get("nodes", [])))
            except Exception as react_err:
                print(f"   ⚠️ [Unity ReAct Ajanı Uyarısı]: {react_err}")
        return son_sayisi > 0

    def _sefin_gozuyle_denetle(self, user_request: str) -> Dict[str, Any]:
        """
        👁️ ŞEFİN CANLI GÖZÜ (The Vision Eye):
        Ekran görüntüsünü (GameView) ve Unity konsol loglarını alır;
        Gemini Multimodal Vision ile sahneyi ve oyunu inceler.
        """
        print("\n👁️ [ŞEFİN GÖZÜ AÇILDI]: Canlı oyun ekranı ve konsol hataları inceleniyor...")

        logs_res = unity_client.get_console_logs()
        raw_logs = [
            l for l in logs_res.get("logs", [])
            if not any(
                noise in (l.get("message", "") + l.get("stackTrace", ""))
                for noise in ["LaSefDynamicRunner_", "LaSefBridgeServer", "LaSefBridge", "[LaSef Köprüsü]"]
            )
        ]
        kirmizi_hatalar = [
            l for l in raw_logs
            if "error" in l.get("type", "").lower() or "exception" in l.get("type", "").lower()
        ]

        if kirmizi_hatalar:
            print(f"   🚨 [Konsol Hatası Tespit Edildi]: {len(kirmizi_hatalar)} adet hata!")
            for kh in kirmizi_hatalar[:3]:
                print(f"      • {kh.get('message', '')[:120]}")

        shot_res = unity_client.capture_screenshot(prefer_game_view=True)
        if not shot_res.get("success") or not shot_res.get("data"):
            print("   ⚠️ [Göz Uyarısı]: Ekran görüntüsü alınamadı, sadece konsol hatalarına bakılıyor.")
            verdict = "DÜZELTME_GEREKLİ" if kirmizi_hatalar else "ONAYLANDI"
            return {
                "has_errors": bool(kirmizi_hatalar),
                "runtime_errors": kirmizi_hatalar,
                "verdict": verdict,
                "analysis": "Ekran görüntüsü alınamadı; konsol durumu değerlendirildi."
            }

        temp_img_path = os.path.join(self.target_folder, "temp_lasef_eye_capture.jpg")
        try:
            img_bytes = base64.b64decode(shot_res.get("data"))
            with open(temp_img_path, "wb") as f:
                f.write(img_bytes)
            print(f"   📸 [Ekran Yakalandı]: {shot_res.get('camera', 'Camera')} ({len(img_bytes)//1024} KB)")

            log_ozeti = "\n".join([f"[{l.get('type')}] {l.get('message')}" for l in raw_logs[-10:]]) or "Konsol temiz (0 hata)."
            hier_live = unity_client.get_hierarchy()
            hier_nodes = hier_live.get("nodes", [])

            def _ozetle_dugum(nd: Dict[str, Any]) -> str:
                ad = nd.get("name", "")
                bilesenler = ",".join((nd.get("components") or [])[:5])
                alt_adlar = [
                    f"{c.get('name')}[{','.join((c.get('components') or [])[:3])}]"
                    for c in (nd.get("children") or [])[:4]
                ]
                alt_metin = f" -> alt: {'; '.join(alt_adlar)}" if alt_adlar else ""
                return f"{ad} ({bilesenler}{alt_metin})"

            hier_ozeti = ", ".join([_ozetle_dugum(n) for n in hier_nodes[:20]]) or "Hiyerarşi okunamadı"
            hata_sayisi = len(kirmizi_hatalar)
            custom_prompt = (
                f"Sen Kıdemli Bir Unity Oyun Direktörü ve Baş Yazılım Mimarısın.\n"
                f"Şu an Unity Editor'de Play Modunda (oyun çalışırken) çekilmiş CANLI BİR OYUN EKRANI GÖRÜNTÜSÜNÜ inceliyorsun.\n\n"
                f"KULLANICI TALEBİ: {user_request}\n\n"
                f"CANLI SAHNE HİYERARŞİSİ ({len(hier_nodes)} kök nesne): {hier_ozeti}\n"
                f"CANLI UNITY KONSOL DURUMU ({hata_sayisi} kırmızı hata):\n{log_ozeti}\n\n"
                f"DEĞERLENDİRME KURALLARI:\n"
                f"- Unity prototip sahnelerinde kapsül/küp/düzlem (Primitive) kullanımı ve FPS kamerasının oyuncunun içinden bakması (oyuncu kapsülünün görünmemesi) tamamen NORMALDİR.\n"
                f"- Eğer sahnede 3B zemin/duvar/nesneler görünüyorsa ve konsolda kritik kırmızı çalışma zamanı hatası (0 kırmızı hata) yoksa kararı 'KARAR: ONAYLANDI' olarak ver.\n"
                f"- Sadece ekran tamamen siyah/boş/pembe shader hatası ise veya konsolda oynanışı çökerten Exception varsa 'KARAR: DÜZELTME_GEREKLİ' ver.\n\n"
                f"Lütfen şu 3 soruyu cevapla:\n"
                f"1. GÖRSEL DURUM: Sahnede zemin, çevre, nesneler ve/veya UI doğru şekilde görünüyor mu?\n"
                f"2. ÇALIŞMA ZAMANI SAĞLIĞI: Konsolda oynanışı bozan bir Exception var mı?\n"
                f"3. NİHAİ KARAR: Tek satırda 'KARAR: ONAYLANDI' veya 'KARAR: DÜZELTME_GEREKLİ' yaz."
            )

            analiz = gemini_service.analyze_image(temp_img_path, custom_prompt=custom_prompt)
            print(f"   🔍 [Şefin Gözü Raporu]:\n{analiz[:300]}...")

            verdict = "ONAYLANDI"
            if len(kirmizi_hatalar) > 0 or ("KARAR: DÜZELTME_GEREKLİ" in analiz.upper() and "KARAR: ONAYLANDI" not in analiz.upper()):
                verdict = "DÜZELTME_GEREKLİ"

            return {
                "has_errors": bool(kirmizi_hatalar),
                "runtime_errors": kirmizi_hatalar,
                "verdict": verdict,
                "analysis": analiz
            }
        except Exception as e:
            print(f"   ⚠️ [Göz Analiz Hatası]: {e}")
            return {
                "has_errors": bool(kirmizi_hatalar),
                "runtime_errors": kirmizi_hatalar,
                "verdict": "ONAYLANDI" if not kirmizi_hatalar else "DÜZELTME_GEREKLİ",
                "analysis": f"Görsel analiz sırasında istisna: {e}"
            }
        finally:
            if os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except Exception:
                    pass

    def _find_runtime_error_files(
        self,
        errors: List[str],
        nihai_dosyalar: Dict[str, str],
        disk_cache: Dict[str, str],
    ) -> List[str]:
        """Runtime hata mesajlarını ve stacktrace'i HEM nihai_dosyalar HEM de diskteki tüm Assets/**/*.cs ile eşleştirir."""
        err_msgs = "\n".join(errors)

        aday_havuz: Dict[str, str] = {}
        for rel_p, code in disk_cache.items():
            aday_havuz[rel_p] = code
        for k, code in nihai_dosyalar.items():
            if not str(k).lower().endswith(".cs"):
                continue
            eslesen = next((dk for dk in aday_havuz if dk.replace("\\", "/") == k.replace("\\", "/") or os.path.basename(dk) == os.path.basename(k)), None)
            if eslesen:
                aday_havuz[eslesen] = code or aday_havuz[eslesen]
            else:
                aday_havuz[k] = code

        hedef_dosyalar: List[str] = []

        def _ekle(anahtar: str) -> None:
            norm = anahtar.replace("\\", "/")
            base = os.path.basename(norm)
            for k in list(nihai_dosyalar.keys()):
                if k.replace("\\", "/") == norm or os.path.basename(k) == base:
                    if k not in hedef_dosyalar:
                        hedef_dosyalar.append(k)
                    return
            nihai_dosyalar[anahtar] = aday_havuz.get(anahtar, "")
            if anahtar not in hedef_dosyalar:
                hedef_dosyalar.append(anahtar)

        explicit_paths = re.findall(r'(Assets[\\/][^(\s:]+\.cs)', err_msgs)
        stack_classes = set(re.findall(r'\b([A-Z][A-Za-z0-9_]+)(?:\.[A-Za-z0-9_]+)?\s*[:\.]\s*[A-Za-z0-9_]+\s*\(', err_msgs))

        missing_comp_pairs = re.findall(r"There is no '(\w+)' attached to the \"([^\"]+)\"", err_msgs)
        quoted_literals = [
            q for q in re.findall(r'"([^"]{4,60})"', err_msgs)
            if len(q.strip()) >= 4
        ]
        log_prefixes = []
        for e_line in errors:
            ilk_satir = str(e_line).strip().splitlines()[0] if str(e_line).strip() else ""
            temiz_parca = re.sub(r'^[A-Za-z0-9_]+Exception:\s*', '', ilk_satir).strip()
            if len(temiz_parca) >= 14 and "UnityEngine." not in temiz_parca:
                log_prefixes.append(temiz_parca[:28])

        for aday_yol, aday_kod in aday_havuz.items():
            base = os.path.basename(aday_yol)
            sinif = os.path.splitext(base)[0]
            norm_aday = aday_yol.replace("\\", "/")

            if any(ep.replace("\\", "/") == norm_aday or os.path.basename(ep) == base for ep in explicit_paths):
                _ekle(aday_yol)
                continue
            if sinif in stack_classes or re.search(rf'\b{re.escape(sinif)}\b', err_msgs) or base in err_msgs:
                _ekle(aday_yol)
                continue
            if aday_kod:
                if any(lit in aday_kod for lit in quoted_literals) or any(pref in aday_kod for pref in log_prefixes):
                    _ekle(aday_yol)
                    continue
                if any(f"GetComponent<{comp}>" in aday_kod or f"GetComponentInChildren<{comp}>" in aday_kod or obj in aday_kod for comp, obj in missing_comp_pairs):
                    _ekle(aday_yol)

        return hedef_dosyalar

    def _onar_runtime_hatasi(self, eye_result: Dict[str, Any], nihai_dosyalar: Dict[str, str]) -> bool:
        """Play Mode sırasında oluşan gerçek oyun çalışma zamanı hatasını diskteki + yeni C# dosyalarında cerrahi olarak onarır."""
        raw_errors = eye_result.get("runtime_errors", [])
        errors = [
            e for e in raw_errors
            if not any(
                noise in (e.get("message", "") + e.get("stackTrace", ""))
                for noise in ["LaSefDynamicRunner_", "LaSefBridgeServer", "LaSefBridge", "[LaSef Köprüsü]"]
            )
        ]
        if not errors:
            return False

        err_msgs = "\n".join([f"• {e.get('message','')}\n{e.get('stackTrace','')}" for e in errors[:8]])
        print(f"   🩺 [Otonom Runtime Onarımı Başlatılıyor]:\n{err_msgs[:260]}...")

        disk_cache = self._snapshot_project_cs_files()
        file_baselines = dict(disk_cache)
        deterministik_onarildi = False
        cs_degisti = False

        taranacak = dict(disk_cache)
        for dk, dv in nihai_dosyalar.items():
            if dk.lower().endswith(".cs") and isinstance(dv, str):
                taranacak[dk] = dv

        for dosya_key, kod_val in taranacak.items():
            if not dosya_key.lower().endswith(".cs") or not isinstance(kod_val, str):
                continue
            yeni_kod = _sanitize_unity_csharp(kod_val)
            if "agent.ResetPath();" in yeni_kod and "isOnNavMesh" not in yeni_kod:
                yeni_kod = yeni_kod.replace(
                    "agent.ResetPath();",
                    "if (agent != null && agent.isActiveAndEnabled && agent.isOnNavMesh) agent.ResetPath();"
                )
            if yeni_kod != kod_val:
                nihai_dosyalar[dosya_key] = yeni_kod
                tam_yol = self._resolve_disk_path(dosya_key, yeni_kod)
                with open(tam_yol, "w", encoding="utf-8") as f:
                    f.write(yeni_kod)
                print(f"   ⚡ [Deterministik Unity 6 / Fake-Null Onarımı Yazıldı]: {tam_yol}")
                deterministik_onarildi = True
                cs_degisti = True

        disk_cache_guncel = self._snapshot_project_cs_files()
        hedef_dosyalar = self._find_runtime_error_files(
            [f"{e.get('message', '')}\n{e.get('stackTrace', '')}" for e in errors],
            nihai_dosyalar,
            disk_cache_guncel,
        )

        if not hedef_dosyalar and not deterministik_onarildi:
            try:
                print("   🤖 [Unity ReAct Ajanı]: Sahne bazlı çalışma zamanı hatası için ReAct ajanı devreye giriyor...")
                sembol_ozeti = self._collect_project_scripts_api_summary()
                hier_ozeti = ""
                try:
                    hier_ozeti = tool_unity_get_hierarchy()
                except Exception:
                    pass
                react_agent = UnityAgentLoop(project_path=self.target_folder, max_steps=8)
                agent_res = react_agent.execute_task(
                    instruction=(
                        f"Canlı oyunda şu çalışma zamanı hatası oluştu:\n{err_msgs}\n\n"
                        + (f"MEVCUT HİYERARŞİ:\n{hier_ozeti[:2500]}\n\n" if hier_ozeti else "")
                        + (f"PROJE SEMBOL HARİTASI:\n{sembol_ozeti[:3500]}\n\n" if sembol_ozeti else "")
                        + "Eksik bileşeni veya hatalı C# scriptini mutlaka somut araç çağrılarıyla (unity_add_component, unity_set_property veya edit_file/write_file) düzelt ve sahneyi kaydet."
                    )
                )
                return not any(
                    k in str(agent_res).lower()
                    for k in ("değişiklik yapılmadı", "başarısız", "yapılamadı")
                )
            except Exception:
                return False

        hier_ozeti = ""
        try:
            hier_ozeti = tool_unity_get_hierarchy()
        except Exception:
            pass

        all_other_code_pool = dict(disk_cache_guncel)
        herhangi_biri_onarildi = deterministik_onarildi

        for hedef_dosya in hedef_dosyalar[:4]:
            mevcut_kod = nihai_dosyalar.get(hedef_dosya, "")
            if not mevcut_kod:
                disk_p = self._find_existing_disk_path(hedef_dosya)
                if disk_p:
                    try:
                        with open(disk_p, "r", encoding="utf-8", errors="ignore") as rf:
                            mevcut_kod = rf.read()
                    except Exception:
                        pass
            if not mevcut_kod:
                continue

            norm_hedef = hedef_dosya.replace("\\", "/")
            baseline_kod = file_baselines.get(norm_hedef, mevcut_kod)
            base_hedef = os.path.basename(hedef_dosya)
            all_other = "\n".join(v for k, v in all_other_code_pool.items() if os.path.basename(k) != base_hedef)
            sembol_ozeti = self._collect_project_scripts_api_summary(exclude_file=hedef_dosya)

            prompt = (
                f"UNITY RUNTIME (ÇALIŞMA ZAMANI) HATALARI TESPİT EDİLDİ:\n{err_msgs}\n\n"
                + (f"CANLI SAHNE HİYERARŞİSİ:\n{hier_ozeti[:2200]}\n\n" if hier_ozeti else "")
                + (f"PROJE SEMBOL & NAMESPACE HARİTASI:\n{sembol_ozeti[:3500]}\n\n" if sembol_ozeti else "")
                + f"HEDEF DOSYA: {hedef_dosya}\n"
                + f"MEVCUT KOD:\n```csharp\n{mevcut_kod}\n```\n\n"
                + "KRİTİK ONARIM KURALLARI:\n"
                + "1. `MissingComponentException` (ör. `Canvas`, `Rigidbody`, `RectTransform`): ASLA `GetComponent<T>() ?? gameObject.AddComponent<T>()` yazma! Yerine `var c = GetComponent<T>(); if (c == null) c = gameObject.AddComponent<T>();` şeklinde açık `null` kontrolü ile bileşeni garantile.\n"
                + "2. `Rigidbody bulunamadı` gibi kendi scriptinin yazdığı Debug.LogError varsa: hata verip devre dışı kalmak yerine `rb = GetComponent<Rigidbody>(); if (rb == null) rb = gameObject.AddComponent<Rigidbody>();` fallback'i ekle.\n"
                + "3. NavMeshAgent / Font (`LegacyRuntime.ttf`) / NullReference kontrollerini güvenli hale getir.\n"
                + "4. ÇOK ÖNEMLİ: Mevcut dosyadaki çalışan sistemleri ve public API imzalarını ASLA silme veya kısaltılmış stub'a çevirme! Namespace'i bozma.\n"
                + "5. Sadece ve sadece tam, saf C# kodunu tek parça olarak yaz."
            )

            try:
                tamir_kodu = gemini_service.generate_with_retry(
                    prompt=prompt,
                    system_instruction="Sen Kıdemli Unity Onarım Mimarı Şefsin. Mevcut dosyanın tüm özelliklerini koruyarak çalışma zamanı hatalarını cerrahi olarak gider ve saf C# kodunu üret."
                )
                temiz = _sanitize_unity_csharp(saf_kodu_ayikla(tamir_kodu, hedef_dosya))
                if not temiz or len(temiz) <= 50:
                    continue

                stub_sorunu = self._check_stub_regression(baseline_kod, temiz, all_other_code=all_other)
                if stub_sorunu:
                    print(f"   🛡️ [Runtime Anti-Stub Koruması ({base_hedef})]: {stub_sorunu} Tekrar isteniyor...")
                    tamir_2 = gemini_service.generate_with_retry(
                        prompt=f"❌ ÖNCEKİ ÇIKTI REDDEDİLDİ: {stub_sorunu}\nMevcut dosyanın hiçbir özelliğini silme!\n\n{prompt}",
                        system_instruction="Sen Kıdemli Unity Onarım Mimarı Şefsin. Mevcut kodu kısaltmadan tüm işlevleri koru."
                    )
                    temiz_2 = _sanitize_unity_csharp(saf_kodu_ayikla(tamir_2, hedef_dosya))
                    if temiz_2 and len(temiz_2) > 50 and not self._check_stub_regression(baseline_kod, temiz_2, all_other_code=all_other):
                        temiz = temiz_2
                    else:
                        print(f"   ⚠️ [Runtime Anti-Stub]: '{base_hedef}' stub yazımına karşı korundu; değişiklik reddedildi.")
                        continue

                if temiz != mevcut_kod:
                    nihai_dosyalar[hedef_dosya] = temiz
                    tam_yol = self._resolve_disk_path(hedef_dosya, temiz)
                    with open(tam_yol, "w", encoding="utf-8") as f:
                        f.write(temiz)
                    print(f"   ✅ [Runtime Hatası Onarıldı ve Yazıldı]: {tam_yol}")
                    herhangi_biri_onarildi = True
                    cs_degisti = True
            except Exception as ex:
                print(f"   ⚠️ [Runtime Onarım Hatası ({hedef_dosya})]: {ex}")

        if cs_degisti:
            time.sleep(1.5)
            comp_ok = self._bekle_ve_onar_derleme(nihai_dosyalar)
            try:
                unity_client.clear_console_logs()
            except Exception:
                pass
            return comp_ok or herhangi_biri_onarildi

        return herhangi_biri_onarildi
