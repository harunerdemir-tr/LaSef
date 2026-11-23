import os
import re

def sef_kod_denetimi(orijinal_istek: str, dosyalar: dict) -> dict:
    """
    👑 ÇIKTI TÜRÜNE GÖRE AKILLI BİRLEŞTİRME (Smart Merge Strategy):
    Unity, Web, Rapor veya Medya çıktılarını türlerine özel standartlarla tek çatı altında toplar.
    """
    print("\n👑 [BAŞ ŞEF DENETİMİ] Üretilen tüm dosyalar Şef Mimar tarafından satır satır denetleniyor...")
    
    for ad in list(dosyalar.keys()):
        kod = dosyalar[ad]
        if isinstance(kod, str) and not ad.lower().endswith((".md", ".txt")):
            kod = re.sub(r"^```[a-zA-Z0-9_\-]*\s*\n?", "", kod)
            kod = re.sub(r"\n?```\s*$", "", kod).strip()
            dosyalar[ad] = kod

    for ad, kod in dosyalar.items():
        if isinstance(kod, str):
            if ad.lower().endswith(".css") and "pointer-events" not in kod:
                dosyalar[ad] = kod + "\n\n/* Buton Tıklanabilirlik Garantisi */\nbutton, input, select, textarea, .btn { pointer-events: auto !important; cursor: pointer !important; }\n"
            elif ad.lower().endswith(".html") and "<style>" in kod and "pointer-events" not in kod:
                dosyalar[ad] = kod.replace("</style>", "\nbutton, input, select, textarea, .btn { pointer-events: auto !important; cursor: pointer !important; }\n</style>")

    for ad, kod in list(dosyalar.items()):
        if ad.lower().endswith(".html") and isinstance(kod, str):
            guncel_html = kod
            inlined_paths = set()
            for d_ad, d_kod in dosyalar.items():
                if not isinstance(d_kod, str) or not d_kod.strip():
                    continue
                base_ad = os.path.basename(d_ad)
                temiz_kod = re.sub(r"^```[a-zA-Z0-9_\-]*\s*\n?", "", d_kod)
                temiz_kod = re.sub(r"\n?```\s*$", "", temiz_kod).strip()

                if d_ad.lower().endswith(".css"):
                    css_pattern = rf'<link\b[^>]*rel=["\']stylesheet["\'][^>]*href=["\'](?:\./)?(?:[^"\']*/)?{re.escape(base_ad)}["\'][^>]*/?>|<link\b[^>]*href=["\'](?:\./)?(?:[^"\']*/)?{re.escape(base_ad)}["\'][^>]*rel=["\']stylesheet["\'][^>]*/?>'
                    if re.search(css_pattern, guncel_html, re.IGNORECASE):
                        inline_css = f"<!-- Inline {base_ad} (Bağımsız Tek Dosya Garantisi) -->\n<style>\n{temiz_kod.replace('</style>', '<\\/style>')}\n</style>"
                        guncel_html = re.sub(css_pattern, lambda _m, blk=inline_css: blk, guncel_html, count=1, flags=re.IGNORECASE)
                        inlined_paths.add(d_ad)
                elif d_ad.lower().endswith(".js") and len(temiz_kod) > 20:
                    src_pattern = rf'<script\b[^>]*src=["\'](?:\./)?(?:[^"\']*/)?{re.escape(base_ad)}["\'][^>]*>\s*</script>'
                    if re.search(src_pattern, guncel_html, re.IGNORECASE):
                        inline_block = f"<!-- Inline {base_ad} (Bağımsız Tek Dosya Garantisi) -->\n<script>\n{temiz_kod.replace('</script>', '<\\/script>')}\n</script>"
                        guncel_html = re.sub(src_pattern, lambda _m, blk=inline_block: blk, guncel_html, count=1, flags=re.IGNORECASE)
                        inlined_paths.add(d_ad)

            for d_ad, d_kod in dosyalar.items():
                if d_ad in inlined_paths or not isinstance(d_kod, str) or not d_kod.strip():
                    continue
                base_ad = os.path.basename(d_ad)
                temiz_kod = re.sub(r"^```[a-zA-Z0-9_\-]*\s*\n?", "", d_kod)
                temiz_kod = re.sub(r"\n?```\s*$", "", temiz_kod).strip()
                if d_ad.lower().endswith(".css") and f"Inline {base_ad}" not in guncel_html:
                    block = f"\n<!-- Auto-Inline {base_ad} -->\n<style>\n{temiz_kod.replace('</style>', '<\\/style>')}\n</style>\n"
                    if "</head>" in guncel_html.lower():
                        guncel_html = re.sub(r"</head>", lambda _m, b=block: b + "</head>", guncel_html, count=1, flags=re.IGNORECASE)
                    else:
                        guncel_html = block + guncel_html
                elif d_ad.lower().endswith(".js") and len(temiz_kod) > 20 and f"Inline {base_ad}" not in guncel_html:
                    block = f"\n<!-- Auto-Inline {base_ad} -->\n<script>\n{temiz_kod.replace('</script>', '<\\/script>')}\n</script>\n"
                    if "</body>" in guncel_html.lower():
                        guncel_html = re.sub(r"</body>", lambda _m, b=block: b + "</body>", guncel_html, count=1, flags=re.IGNORECASE)
                    else:
                        guncel_html += block
            dosyalar[ad] = guncel_html

    cs_dosyalar = [f for f in dosyalar.keys() if f.lower().endswith(".cs")]
    for cs_ad in cs_dosyalar:
        icerik = dosyalar[cs_ad]
        if isinstance(icerik, str):
            if '"Arial.ttf"' in icerik:
                icerik = icerik.replace('"Arial.ttf"', '"LegacyRuntime.ttf"')
                dosyalar[cs_ad] = icerik
                print(f"   🩹 [Unity 6 Font Onarımı]: '{cs_ad}' içindeki 'Arial.ttf' -> 'LegacyRuntime.ttf' olarak güncellendi.")

            sinif_adi = os.path.splitext(os.path.basename(cs_ad))[0]
            if f"class {sinif_adi}" not in icerik:
                match = re.search(r'public\s+(?:static\s+)?class\s+(\w+)', icerik)
                if match and match.group(1) != sinif_adi:
                    hatali_sinif = match.group(1)
                    dosyalar[cs_ad] = re.sub(rf'\bclass\s+{re.escape(hatali_sinif)}\b', f'class {sinif_adi}', icerik)
                    print(f"   🩹 [Unity Sınıf Onarımı]: '{cs_ad}' içindeki '{hatali_sinif}' sınıfı '{sinif_adi}' olarak eşitlendi.")

    md_dosyalar = [f for f in dosyalar.keys() if f.lower().endswith(".md") and f != "TAM_PROJE_RAPORU.md"]
    if len(md_dosyalar) > 1 and "TAM_PROJE_RAPORU.md" not in dosyalar:
        print(f"   📑 [Rapor Birleştirme]: {len(md_dosyalar)} rapor modülü 'TAM_PROJE_RAPORU.md' altında birleştiriliyor...")
        birlesik_rapor = [f"# 📋 {orijinal_istek[:60].strip()}\n\n> Bu rapor LaSef AI Çoklu Ajan Orkestrası tarafından otonom olarak üretilmiştir.\n"]
        birlesik_rapor.append("## 📑 İçindekiler Tablosu")
        for m_dosya in md_dosyalar:
            baslik_temiz = os.path.splitext(m_dosya)[0].replace("_", " ").title()
            birlesik_rapor.append(f"- [{baslik_temiz}](#{baslik_temiz.lower().replace(' ', '-')})")
        birlesik_rapor.append("\n---\n")

        for m_dosya in md_dosyalar:
            baslik_temiz = os.path.splitext(m_dosya)[0].replace("_", " ").title()
            birlesik_rapor.append(f"## {baslik_temiz}\n\n{dosyalar[m_dosya]}\n\n---\n")

        dosyalar["TAM_PROJE_RAPORU.md"] = "\n".join(birlesik_rapor)

    return dosyalar

def kaydet_ve_raporla(hedef_klasor: str, dosyalar: dict, orijinal_istek: str, blackboard=None) -> str:
    """Proje dosyalarını Unity/Web/Rapor yapısına uygun şekilde fiziksel diske yazar ve rapor üretir."""
    os.makedirs(hedef_klasor, exist_ok=True)
    print(f"📁 [ONAYLANDI] Proje Klasörü Oluşturuldu: {hedef_klasor}")

    gercek_hedef = hedef_klasor
    is_unity = os.path.exists(os.path.join(hedef_klasor, "Assets")) or os.path.exists(os.path.join(hedef_klasor, "ProjectSettings"))
    
    if not is_unity:
        try:
            for alt in os.listdir(hedef_klasor):
                alt_yol = os.path.join(hedef_klasor, alt)
                if os.path.isdir(alt_yol) and (os.path.exists(os.path.join(alt_yol, "Assets")) or os.path.exists(os.path.join(alt_yol, "ProjectSettings"))):
                    gercek_hedef = alt_yol
                    is_unity = True
                    break
        except Exception:
            pass

    import shutil
    kaydedilenler = []
    istek_kucuk = (orijinal_istek or "").lower()
    sifirlama_istendi = any(k in istek_kucuk for k in ("baştan yaz", "bastan yaz", "sıfırla", "sifirla", "sıfırdan"))

    for dosya_adi, icerik in dosyalar.items():
        if is_unity and os.path.basename(dosya_adi).lower() in ("buildreport.txt", "cikti.txt"):
            continue
        if is_unity and dosya_adi.lower().endswith(".cs") and not dosya_adi.lower().startswith("assets"):
            is_editor_script = "editor" in dosya_adi.lower() or "builder" in dosya_adi.lower() or (isinstance(icerik, str) and "using UnityEditor" in icerik)
            if is_editor_script:
                tam_yol = os.path.join(gercek_hedef, "Assets", "Editor", os.path.basename(dosya_adi))
            else:
                tam_yol = os.path.join(gercek_hedef, "Assets", "Scripts", dosya_adi)
        else:
            tam_yol = os.path.join(gercek_hedef, dosya_adi)

        try:
            os.makedirs(os.path.dirname(tam_yol), exist_ok=True)
            if icerik is None:
                icerik = ""

            if isinstance(icerik, str) and icerik.startswith("[BINARY_MEDIA_FILE:"):
                kaynak_dosya = icerik.split("[BINARY_MEDIA_FILE:")[1].split("]")[0].strip()
                if os.path.exists(kaynak_dosya) and os.path.abspath(kaynak_dosya) != os.path.abspath(tam_yol):
                    shutil.copy2(kaynak_dosya, tam_yol)
                boyut_kb = os.path.getsize(tam_yol) / 1024
                goreli = os.path.relpath(tam_yol, hedef_klasor)
                kaydedilenler.append(f"🖼️/🎬 {goreli} ({boyut_kb:.1f} KB - Gerçek Medya)")
            else:
                if isinstance(icerik, str) and dosya_adi.lower().endswith((".cs", ".js", ".py")) and not icerik.startswith("[BINARY_MEDIA_FILE:"):
                    from agents.worker_agent import saf_kodu_ayikla
                    icerik = saf_kodu_ayikla(icerik, dosya_adi)

                if is_unity and dosya_adi.lower().endswith(".cs") and os.path.isfile(tam_yol) and not sifirlama_istendi:
                    try:
                        with open(tam_yol, "r", encoding="utf-8", errors="ignore") as rf:
                            eski_kod = rf.read()
                        if len(eski_kod) >= 3500 and len(icerik) < len(eski_kod) * 0.42:
                            print(f"   🛡️ [Dosya Koruması]: '{dosya_adi}' boyutu şüpheli küçüldü ({len(eski_kod)}B -> {len(icerik)}B). Mevcut metotlar korunarak birleştiriliyor...")
                            try:
                                from infrastructure.gemini_client import gemini_service
                                merge_prompt = (
                                    f"Aşağıdaki MEVCUT ÇALIŞAN Unity C# dosyası ({dosya_adi}) küçültülmüş taslakla ezilmek üzere.\n"
                                    f"KULLANICI İSTEĞİ: {orijinal_istek}\n\n"
                                    f"MEVCUT TAM DOSYA:\n```csharp\n{eski_kod[:18000]}\n```\n\n"
                                    f"YENİ ÖNERİLEN DEĞİŞİKLİK:\n```csharp\n{icerik}\n```\n\n"
                                    f"GÖREV: Mevcut dosyadaki TÜM çalışan sınıfları, enumları, public metotları ve alanları KORUYARAK yeni değişikliği içine temizce birleştir. Tek parça saf C# kodu üret."
                                )
                                merged_raw = gemini_service.generate_with_retry(
                                    prompt=merge_prompt,
                                    system_instruction="Sen Kıdemli Unity C# Mimarısın. Mevcut kodu silmeden yeni iyileştirmeyi güvenli birleştirirsin.",
                                    temperature=0.1,
                                )
                                merged_cs = saf_kodu_ayikla(merged_raw, dosya_adi)
                                if merged_cs and len(merged_cs) >= len(eski_kod) * 0.55:
                                    icerik = merged_cs
                                else:
                                    print(f"   ⚠️ [Dosya Koruması]: Birleştirme yetersiz kaldığı için mevcut '{dosya_adi}' korundu.")
                                    icerik = eski_kod
                            except Exception:
                                icerik = eski_kod
                    except Exception:
                        pass

                with open(tam_yol, "w", encoding="utf-8") as f:
                    f.write(icerik)
                boyut_kb = len(icerik.encode('utf-8')) / 1024
                goreli = os.path.relpath(tam_yol, hedef_klasor)
                kaydedilenler.append(f"📄 {goreli} ({boyut_kb:.1f} KB)")
        except Exception as e:
            print(f"[HATA] Dosya kaydedilemedi ({dosya_adi}): {e}")

    talimat = "Klasördeki ana dosyayı çift tıklayarak çalıştırabilirsiniz."
    html_list = [k for k in dosyalar if k.lower().endswith(".html")]
    if html_list:
        ana_html = "index.html" if "index.html" in html_list else html_list[0]
        if "index.html" not in html_list:
            try:
                shutil.copy2(os.path.join(gercek_hedef, ana_html), os.path.join(gercek_hedef, "index.html"))
            except Exception:
                pass
        talimat = f"Klasördeki '{ana_html}' (veya 'index.html') dosyasına çift tıklayarak varsayılan tarayıcınızda doğrudan açabilir ve oynayabilirsiniz."
    elif any(k.endswith(".cs") for k in dosyalar):
        from tools.unity_bridge_client import unity_client
        if os.path.exists(os.path.join(gercek_hedef, "Assets")):
            unity_client.install_bridge_to_project(gercek_hedef)
        if unity_client.is_connected():
            talimat = "🎮 Unity Editor canlı olarak bağlı! Sahne ve bileşenler doğrudan canlı editöre aktarıldı. Unity Editor penceresine geçip Play (▶) butonuna basarak anında test edebilirsiniz."
        else:
            talimat = "Unity projenizi açın ve Play butonuna basın. Projeye 'LaSefBridgeServer.cs' köprüsü otomatik yerleştirildi; Unity açıkken ajanlar sahnede canlı çalışacaktır."
    elif any(k.endswith(".md") for k in dosyalar):
        talimat = "Üretilen teknik raporlar klasörde hazırdır. Konsolide 'TAM_PROJE_RAPORU.md' dosyasını herhangi bir Markdown görüntüleyici ile inceleyebilirsiniz."
    elif any(k.endswith(".py") for k in dosyalar):
        talimat = "Komut satırında 'python main.py' çalıştırarak uygulamayı başlatabilirsiniz."

    token_raporu = ""
    if blackboard:
        stats = blackboard.get_token_stats()
        chef_t = stats.get("chef", 0)
        worker_t = stats.get("workers", 0)
        total_t = stats.get("total", 0)
        token_raporu = (
            f"\n📊 TOKEN KULLANIM VE MALİYET OPTİMİZASYON RAPORU:\n"
            f"  • 👑 Şef AI (Gemini): ~{chef_t:,} token\n"
            f"  • ⚙️ Amele Ajanlar (NVIDIA NIM): ~{worker_t:,} token\n"
            f"  • 🎯 Toplam Token: ~{total_t:,} token\n"
        )

    ozet = (
        "\n" + "═" * 60 + "\n" +
        f"✅ PROJE BAŞARIYLA TAMAMLANDI!\n" +
        f"📁 Dizin: {gercek_hedef}\n" +
        "═" * 60 + "\n\n" +
        f"📦 Oluşturulan Dosyalar ({len(kaydedilenler)} Adet):\n" +
        "\n".join([f"  • {k}" for k in kaydedilenler]) + "\n" +
        token_raporu + "\n" +
        f"🛡️ ÇALIŞTIRMA TALİMATI:\n{talimat}\n"
    )
    return ozet
