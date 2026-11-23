"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF ORKESTRASYON MOTORU VE GİRİŞ NOKTASI (orchestrator/__init__.py)
═══════════════════════════════════════════════════════════════════════════════
📌 LASEF KORTEKS MANİFESTOSU — SİSTEMİN TEMEL AMACI:
LaSef (Lider Akıllı Sistemler ve Entegre Fabrika); kullanıcı taleplerini
kapsamlı bir çoklu ajan iş bölümüyle analiz eden, sözleşmeye dayalı
(contract-first) çalışan, kör kod üretimini reddedip bizzat test eden
(The Vision Eye) ve kalıcı korteks hafızasıyla kararları saklayan
otonom bir yapay zeka mühendislik fabrikasıdır.

🔌 STANDART MCP VE ENTEGRASYON YAKLAŞIMI:
- Projeye denenmemiş, işe yaramayan yapay MCP kodları ENJEKTE EDİLMEZ.
- Kullanıcı girdisinden hedef platform (Unity, Web, Blender vb.) tespit edilir.
- Yalnızca endüstri standardı UPM paketleri (CoplayDev/unity-mcp) veya
  yerleşik test edilmiş köprüler (LaSefBridgeServer.cs) devreye alınır.
═══════════════════════════════════════════════════════════════════════════════
"""
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

from infrastructure.file_reader import kaynaklari_tara_ve_birlestir
from infrastructure.gemini_client import gemini_service
from infrastructure.nim_client import nim_service
from agents.chef_architect import niyet_analizi_yap
from core.sourced_memory import SourcedMemory
from core.mcp_router import detect_application_profile
from orchestrator.lifecycle_tracker import lifecycle_tracker
from orchestrator.supervisor_loop import SupervisorOrchestrator

def orkestrayi_yonet(
    kullanici_istegi: str,
    hedef_klasor: str = "",
    kaynak_dosyalar: list = None,
    branch_context: str = "",
    meta_out: dict = None
) -> str:
    """
    LaSef Çoklu Ajan Orkestrasyonunun Ana Yürütme Girişi.
    Şef (Gemini) ve dinamik Amele (NVIDIA NIM / Gemini Fallback) ajanlarını canlı supervisor loop ile koordine eder.
    - branch_context: Aktif konuşma dalındaki (branch) önceki promptların ve üretilen işlerin hafıza özeti.
    - meta_out: Çalışma sonunda üretilen dosyalar, sözleşme ve istatistiklerin aktarıldığı opsiyonel sözlük.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        yeni_gem_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if yeni_gem_key and yeni_gem_key != getattr(gemini_service, "api_key", None):
            gemini_service.__init__(api_key=yeni_gem_key)
            print("🔑 [API Güvenlik]: Yeni GEMINI_API_KEY algılandı ve canlı olarak yüklendi.")
        yeni_nim_key = os.getenv("NVIDIA_API_KEY") or os.getenv("NIM_API_KEY")
        if yeni_nim_key and yeni_nim_key != getattr(nim_service, "api_key", None):
            nim_service.__init__(api_key=yeni_nim_key)
            print("🔑 [API Güvenlik]: Yeni NVIDIA_API_KEY algılandı ve canlı olarak yüklendi.")
    except Exception:
        pass

    if branch_context and len((kullanici_istegi or "").strip()) < 35:
        kisa_istek = (kullanici_istegi or "").strip().lower().rstrip(".! ")
        onay_kelimeleri = {
            "yap", "uygula", "başla", "basla", "devam", "devam et", "evet",
            "evet yap", "tamam", "tamam yap", "onayla", "hadi yap", "kodla",
            "inşa et", "insa et", "kur", "şimdi yap", "simdi yap", "üret", "uret"
        }
        if kisa_istek in onay_kelimeleri:
            import re as _re
            onceki_promptlar = _re.findall(
                r'👤 Önceki Kullanıcı Promptu #\d+:\s*\n"(.*?)"\s*\n(?:📜|🤖|📦|👑|───)',
                branch_context,
                flags=_re.DOTALL
            )
            dolgun_promptlar = [p.strip() for p in onceki_promptlar if len(p.strip()) >= 35]
            if dolgun_promptlar:
                devralinan = dolgun_promptlar[-1]
                print(f"🔗 [Onay Algılandı ('{kullanici_istegi.strip()}')]: Önceki turdaki görev devralındı ({len(devralinan)} karakter).")
                kullanici_istegi = devralinan

    on_profil = detect_application_profile(kullanici_istegi, "", target_folder=hedef_klasor)

    kaynak_baglami = ""
    alakasiz_unity_atlandi = False
    etkin_kaynaklar = list(kaynak_dosyalar or [])
    if not etkin_kaynaklar and hedef_klasor and os.path.isdir(hedef_klasor):
        if os.path.isdir(os.path.join(hedef_klasor, "Assets")) or any(
            os.path.splitext(f)[1].lower() in (".cs", ".py", ".js", ".ts", ".html")
            for f in os.listdir(hedef_klasor)[:40]
            if os.path.isfile(os.path.join(hedef_klasor, f))
        ):
            etkin_kaynaklar = [hedef_klasor]

    if etkin_kaynaklar:
        if on_profil.app_key in ("web", "blender") and any("unity" in str(p).lower() or "mcp deneme" in str(p).lower() for p in etkin_kaynaklar):
            print(f"⚠️ [Bağlam Koruması]: Kullanıcı '{on_profil.app_key}' hedefi belirttiği için önceki alakasız Unity referans klasörü atlandı.")
            alakasiz_unity_atlandi = True
        else:
            kaynak_baglami = kaynaklari_tara_ve_birlestir(etkin_kaynaklar)

    if branch_context:
        print("🌿 [Branch Hafıza Sistemi]: Seçili daldaki önceki promptlar ve yapılan iş kayıtları Şef bağlamına yüklendi.")
        kaynak_baglami = branch_context + ("\n\n" + kaynak_baglami if kaynak_baglami else "")

    if not alakasiz_unity_atlandi and on_profil.app_key not in ("web", "blender"):
        try:
            aday_kokler = list(kaynak_dosyalar or [])
            if hedef_klasor:
                aday_kokler.append(hedef_klasor)
            unity_ilgili = (
                on_profil.app_key == "unity"
                or "unity" in (kullanici_istegi or "").lower()
                or any(os.path.isdir(os.path.join(os.path.abspath(str(p)), "Assets")) for p in aday_kokler if p)
            )
            if unity_ilgili:
                from tools.unity_tools import tool_unity_collect_hierarchy_context
                hiyerarsi_baglami = tool_unity_collect_hierarchy_context(aday_kokler)
                if hiyerarsi_baglami:
                    import re as _re_u
                    unity_root = next(
                        (os.path.abspath(str(p)) for p in aday_kokler if p and os.path.isdir(os.path.join(os.path.abspath(str(p)), "Assets"))),
                        ""
                    )
                    priority_chunks = []
                    if unity_root:
                        search_blob = (kullanici_istegi or "") + "\n" + hiyerarsi_baglami
                        cs_mentions = list(dict.fromkeys(_re_u.findall(r'([A-Za-z0-9_]+\.cs)', search_blob)))
                        assets_dir = os.path.join(unity_root, "Assets")
                        for cs_name in cs_mentions[:8]:
                            for r_dir, _d, f_names in os.walk(assets_dir):
                                if "LaSefBridge" in r_dir or "TutorialInfo" in r_dir:
                                    continue
                                if cs_name in f_names:
                                    fp = os.path.join(r_dir, cs_name)
                                    rel_p = os.path.relpath(fp, unity_root).replace("\\", "/")
                                    try:
                                        with open(fp, "r", encoding="utf-8", errors="ignore") as rf:
                                            txt = rf.read()
                                        priority_chunks.append(f"🎯 [ÖNCELİKLİ DOSYA (Hata/İstekte Geçen): {rel_p}]\n```csharp\n{txt[:9000]}\n```")
                                    except Exception:
                                        pass
                                    break
                    priority_blk = ("\n\n".join(priority_chunks) + "\n\n") if priority_chunks else ""
                    kaynak_baglami = hiyerarsi_baglami + "\n\n" + priority_blk + (kaynak_baglami if kaynak_baglami else "")
        except Exception as _unity_ctx_err:
            print(f"⚠️ [Unity Hiyerarşi Bağlamı]: Atlandı ({_unity_ctx_err})")

    niyet = niyet_analizi_yap(kullanici_istegi, kaynak_baglami, hedef_klasor=hedef_klasor)
    if niyet.get("tur") == "SOHBET_SORU":
        yanit = niyet.get("yanit", "Merhaba!")
        print(f"\n💬 [ŞEF YANITI]:\n{yanit}\n")
        if isinstance(meta_out, dict):
            meta_out["app_key"] = "chat"
            meta_out["target_folder"] = hedef_klasor
        return f"💬 ŞEFİN YANITI:\n\n{yanit}"

    if niyet.get("tur") == "AKTIF_AJAN":
        from agents.active_agent import otonom_ajan_gorevi_yurut
        yanit = otonom_ajan_gorevi_yurut(
            gorev=kullanici_istegi,
            hedef_klasor=hedef_klasor,
            max_adim=6,
            read_only=False,
            kaynak_baglami=kaynak_baglami,
        )
        print(f"\n🤖 [AKTİF AJAN RAPORU]:\n{yanit}\n")
        if isinstance(meta_out, dict):
            meta_out["app_key"] = on_profil.app_key or "agent"
            meta_out["target_folder"] = hedef_klasor
        return f"🤖 AKTİF AJAN RAPORU:\n\n{yanit}"

    print("\n🔍 [Sistem Sağlık Kontrolü]: Şef ve Amele modelleri doğrulanıyor...")
    if not gemini_service._is_healthy:
        gemini_service.health_check()
    if nim_service.needs_health_refresh():
        nim_service.health_check()

    hafiza = SourcedMemory(hedef_klasor)
    app_profile = detect_application_profile(kullanici_istegi, kaynak_baglami, target_folder=hedef_klasor)
    hafiza.remember_application_target(app_profile.app_key)

    lifecycle_tracker.setup_lifecycle_for_request(kullanici_istegi, app_profile.app_key)

    hafiza_baglami = hafiza.get_summary()
    if hafiza_baglami:
        kaynak_baglami = kaynak_baglami + "\n\n" + hafiza_baglami if kaynak_baglami else hafiza_baglami

    orchestrator = SupervisorOrchestrator(sync_timeout=120.0)
    sonuc_raporu = orchestrator.execute(
        user_request=kullanici_istegi,
        target_folder=hedef_klasor,
        source_context=kaynak_baglami
    )

    hafiza.remember_decision(f"'{kullanici_istegi[:50]}' başarıyla üretildi.", "orchestration")

    if isinstance(meta_out, dict):
        meta_out["app_key"] = app_profile.app_key
        meta_out["target_folder"] = orchestrator.last_target_folder or hedef_klasor
        meta_out["architecture_contract"] = orchestrator.last_architecture_contract
        meta_out["token_stats"] = orchestrator.last_token_stats
        meta_out["verification_failed"] = not getattr(orchestrator, "last_verification_passed", True)
        files_list = []
        for f_name, f_content in (orchestrator.last_artifacts or {}).items():
            full_p = os.path.join(orchestrator.last_target_folder or "", f_name) if orchestrator.last_target_folder else f_name
            content_str = f_content if isinstance(f_content, str) else ""
            sz_kb = round(len(content_str.encode("utf-8", errors="ignore")) / 1024.0, 1)
            files_list.append({
                "path": full_p,
                "rel_path": f_name,
                "size_kb": sz_kb,
                "preview": content_str[:12000]
            })
        meta_out["files_produced"] = files_list

    if app_profile.app_key in ["unity", "blender", "unreal"]:
        canli_bagli = (
            "UNITY CANLI TEST & DOĞRULAMA RAPORU:" in sonuc_raporu
            or "BLENDER MCP & DOĞRULAMA RAPORU:" in sonuc_raporu
        )
        kurulum_soruldu = any(k in (kullanici_istegi or "").lower() for k in ("mcp kur", "nasıl kurulur", "paket kur", "package manager"))
        if not canli_bagli or kurulum_soruldu:
            sonuc_raporu += f"\n\n---\n{app_profile.user_guide_markdown}"

    return sonuc_raporu
