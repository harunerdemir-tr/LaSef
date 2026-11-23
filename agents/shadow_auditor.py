import os
import re

def golge_ajan_denetle(adim_no: int, cikti: str, dosya_adi: str = "", dom_haritasi: dict = None, gorev_tanimi: str = "") -> tuple:
    """Üretilen kodun eksik veya sahte taslak olup olmadığını doğrular."""
    if not cikti or len(cikti.strip()) < 40 or "HATA:" in cikti:
        return (False, "Çıktı kabul edilemeyecek kadar kısa veya boş.", cikti)

    if re.search(r'/\*[\s.]*\*/|//\s*\.\.\.|\{\s*/\*.*?\*/\s*\}|function\s+\w+\s*\([^)]*\)\s*\{\s*\}', cikti):
        return (False, "Fonksiyon gövdeleri boş bırakılmış! Gerçek kod yazılmalı.", cikti)

    if dosya_adi.lower().endswith(".cs"):
        prefab_ihlalleri = re.findall(r'\[SerializeField\]\s*(?:private|public)?\s*GameObject\s+\w*[Pp]refab', cikti)
        if prefab_ihlalleri and "CreatePrimitive" not in cikti and "new GameObject" not in cikti:
            return (False, f"ZERO-SETUP İHLALİ: '{dosya_adi}' fallback olmadan Prefab bağımlılığı kullanıyor. Prefab null olduğunda GameObject.CreatePrimitive/new GameObject ile oluşturmalı!", cikti)

        if re.search(r'GetComponent(?:InChildren|InParent)?<[^>]+>\(\s*\)\s*\?\?', cikti):
            return (False, f"UNITY FAKE-NULL HATASI: '{dosya_adi}' içinde GetComponent<T>() ?? kullanımı MissingComponentException fırlatır; 'if (c == null)' kullanılmalı!", cikti)

        if "editor" not in dosya_adi.lower() and "#if UNITY_EDITOR" not in cikti:
            if "using UnityEditor" in cikti or "UnityEditor." in cikti:
                return (False, f"RUNTIME/EDITOR İHLALİ: '{dosya_adi}' runtime scripti içinde #if UNITY_EDITOR olmadan UnityEditor API kullanıyor!", cikti)

        sinif_adi = os.path.splitext(os.path.basename(dosya_adi))[0]
        public_siniflar = re.findall(r'public\s+(?:static\s+)?class\s+(\w+)', cikti)
        if len(public_siniflar) > 1:
            return (False, f"ÇOKLU CLASS HATASI: '{dosya_adi}' içinde birden fazla public class ({', '.join(public_siniflar)}) var! Unity'de her dosya yalnızca dosya adıyla aynı TEK BİR public class içermelidir.", cikti)
        elif public_siniflar and public_siniflar[0] != sinif_adi:
            return (False, f"CLASS İSİM UYUŞMAZLIĞI: '{dosya_adi}' dosya adı ile içindeki '{public_siniflar[0]}' class adı uyuşmuyor!", cikti)

        if "bootstrapper" in dosya_adi.lower() or "bootstrap" in dosya_adi.lower():
            if "RuntimeInitializeOnLoadMethod" not in cikti:
                return (False, f"ZERO-SETUP İHLALİ: '{dosya_adi}' [RuntimeInitializeOnLoadMethod] kullanmıyor! Sahneye script sürüklemeden çalışmalı.", cikti)

    if dosya_adi.lower().endswith(".js") and dom_haritasi and dom_haritasi.get("tum_idler"):
        html_id_seti = set(dom_haritasi.get("tum_idler", []))
        js_cagrilan_idler = set(
            re.findall(r'getElementById\s*\(\s*["\']([^"\']+)["\']\s*\)', cikti) +
            re.findall(r'querySelector(?:All)?\s*\(\s*["\']#([a-zA-Z0-9_\-]+)', cikti)
        )
        uyusmayan = [jid for jid in js_cagrilan_idler if jid not in html_id_seti]
        if uyusmayan:
            return (False, f"DOM ID Uyuşmazlığı: '{uyusmayan[0]}' HTML'de bulunamadı.", cikti)

    return (True, "Kod Standartları Onaylandı", cikti)

