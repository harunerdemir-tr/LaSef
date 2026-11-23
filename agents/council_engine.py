import os
import re
import json
import time
from typing import Optional
from infrastructure.gemini_client import gemini_service
from infrastructure.nim_client import nim_service

def _kod_gecerli_mi(kod: str, dosya_adi: str) -> bool:
    """Kodun geçerli bir programlama dosyası olup olmadığını denetler (sohbet ve düşünce sızıntısını engeller)."""
    if not kod or len(kod.strip()) < 50:
        return False
    k = kod.strip()
    
    ilk_satir = k.splitlines()[0].strip().lower()
    yasak_baslangiclar = [
        "here's", "here is", "sure", "certainly", "now let me",
        "thinking", "analyze", "i will", "below", "let's", "in this code"
    ]
    if any(ilk_satir.startswith(x) for x in yasak_baslangiclar):
        return False

    uzanti = os.path.splitext(dosya_adi)[1].lower()
    if uzanti == ".cs":
        sinif_adi = os.path.splitext(os.path.basename(dosya_adi))[0]
        has_csharp = any(kw in k for kw in ["using UnityEngine", "using System", "class ", "struct ", "enum "])
        if not has_csharp:
            return False
        if f"class {sinif_adi}" not in k and f"struct {sinif_adi}" not in k and f"enum {sinif_adi}" not in k:
            return False
        if re.search(r"class\s+[a-zA-Z0-9_]+\s+[a-zA-Z0-9_]+\s*[:{]", k):
            return False
        if k.count("{") != k.count("}"):
            return False
        if k.count("#if") != k.count("#endif"):
            return False
        if any(ui_comp in k for ui_comp in ["CanvasScaler", "GraphicRaycaster", "RawImage"]) and "using UnityEngine.UI" not in k:
            return False
        if "AddComponent<Collider>()" in k:
            return False

    return True

def _saf_kod_ayir(metin: str, dosya_adi: str) -> str:
    """Markdown bloklarından saf kodu ayıklar, düşünce ve sohbet metinlerini eler."""
    if not metin:
        return ""
    temiz = re.sub(r"<think>.*?</think>", "", metin, flags=re.DOTALL).strip()

    bloklar = re.findall(r"```(?:[a-zA-Z0-9_\-#]+)?\s*\n(.*?)\n\s*```", temiz, re.DOTALL)
    if bloklar:
        for b in reversed(bloklar):
            b_str = b.strip()
            if _kod_gecerli_mi(b_str, dosya_adi):
                return b_str

    if "```" in temiz:
        parcalar = temiz.split("```")
        if len(parcalar) >= 2:
            olasi = parcalar[1]
            olasi = re.sub(r"^[a-zA-Z0-9_\-#]+\s*\n", "", olasi).strip()
            if _kod_gecerli_mi(olasi, dosya_adi):
                return olasi

    if _kod_gecerli_mi(temiz, dosya_adi):
        return temiz

    return ""

def konsey_kodu_denetle_ve_oyla_detayli(dosya_adi: str, uretilen_kod: str, gorev_tanimi: str) -> tuple:
    """
    ⚖️ ÇOKLU HAKEM KONSEYİ (Multi-LLM Council Decision Engine):
    Üretilen kritik kodları Gemini Sistem Mimarı ve NVIDIA NIM Uzman Hakem modelinden
    oluşan bağımsız jüri heyetinde çapraz denetim ve oylamaya sunar.
    Dönüş: (onay_durumu: bool, nihai_kod: str, karar_aciklamasi: str)
    """
    uzanti = os.path.splitext(dosya_adi)[1].lower()
    if uzanti not in [".cs", ".js", ".py", ".c", ".cpp", ".html"]:
        return (True, uretilen_kod, "Konsey kapsamı dışı uzantı")

    print(f"\n   ⚖️ [Hakem Konseyi] '{dosya_adi}' Çoklu Model Heyetine Sunuluyor (Gemini + NIM)...")

    sinif_adi = os.path.splitext(os.path.basename(dosya_adi))[0]
    prompt = f"""Sen dünya çapında bağımsız bir Baş Kod İnceleme Hakemisin.
Hedef Dosya: '{dosya_adi}' (Beklenen Sınıf Adı: '{sinif_adi}')
Görev Tanımı: '{gorev_tanimi}'

Aşağıdaki kodu satır satır incele:
1. Kod tamamen çalışır, eksiksiz ve syntax hatasız mı?
2. Fonksiyon gövdeleri dolu mu, sahte 'stub' veya 'dummy' var mı?
3. Unity C# için:
   - 3D mekanikler (Rigidbody, CharacterController, BoxCollider/CapsuleCollider) doğru mu? (Soyut `AddComponent<Collider>()` YASAKTIR!)
   - `GameObject.mesh` gibi hatalı çağrılar var mı? (`GetComponent<MeshFilter>().sharedMesh` veya `CreatePrimitive` kullanılmalı)
   - `CanvasScaler`, `GraphicRaycaster`, `RawImage`, `Text` kullanılıyorsa `using UnityEngine.UI;` mevcut mu?
   - `FindObjectsOfType` yerine Unity 6 uyumlu `FindObjectsByType` kullanılmış mı?
4. Sınıf adı dosya adıyla ('{sinif_adi}') birebir örtüşüyor mu?

ÖNEMLİ KURAL: Asla sohbet, açıklama veya düşünce süreci yazma!
EĞER KOD MÜKEMMELSE VE HİÇBİR DERLEME HATASI YOKSA: SADECE "ONAYLANDI" yaz.
EĞER DÜZELTME GEREKİYORSA: Düzeltilmiş eksiksiz çalışan saf kodu tek bir markdown bloğu ``` içinde üret.

KOD:
\"\"\"
{uretilen_kod}
\"\"\""""

    from concurrent.futures import ThreadPoolExecutor

    juri_1_onay = False
    juri_1_kod = ""
    juri_2_onay = False
    juri_2_kod = ""

    def _run_hakem_1():
        nonlocal juri_1_onay, juri_1_kod
        try:
            yanit_1 = gemini_service.generate_with_retry(
                prompt=prompt,
                system_instruction="Sen Baş Hakem Konseyi Mimarisin. Asla gereksiz konuşma, sadece ONAYLANDI veya temiz kod bloğu döndür.",
                temperature=0.1,
                allow_nim_fallback=False
            )
            if "ONAYLANDI" in yanit_1.upper() and len(yanit_1.strip()) < 40 and _kod_gecerli_mi(uretilen_kod, dosya_adi):
                juri_1_onay = True
                print("      └ 🏛️ [Hakem 1 - Gemini]: ONAYLANDI ✅")
            else:
                temiz = _saf_kod_ayir(yanit_1, dosya_adi)
                if _kod_gecerli_mi(temiz, dosya_adi):
                    juri_1_kod = temiz
                    print("      └ 🏛️ [Hakem 1 - Gemini]: Geçerli iyileştirme önerisi sundu.")
                else:
                    print("      └ 🏛️ [Hakem 1 - Gemini]: Öneri geçersiz veya biçim dışı (yoksayıldı).")
        except Exception as e:
            print(f"      └ ⚠️ [Hakem 1 - Gemini]: Atlandı ({e})")

    def _run_hakem_2():
        nonlocal juri_2_onay, juri_2_kod
        if not nim_service.client or not nim_service.has_healthy_fast_model():
            print("      └ ⏭️ [Hakem 2 - NIM]: Sağlıklı hızlı NIM havuzu şu an soğumada, Gemini + Statik Denetim yeterli.")
            return
        try:
            nim_hakem_model = nim_service.get_best_model_for_capability("fast")
            kisa_m = nim_hakem_model.split('/')[-1]
            yanit_2 = nim_service.complete_with_retry(
                model_id=nim_hakem_model,
                messages=[
                    {"role": "system", "content": "Sen bağımsız Kıdemli Kod İnceleme Hakemisin. Yanıtında asla açıklama yazma, sadece ONAYLANDI veya ``` markdown bloğunda saf kod döndür."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4096,
                max_retries=1,
                timeout=22.0,
                disable_thinking=True
            )
            if "ONAYLANDI" in yanit_2.upper() and len(yanit_2.strip()) < 40 and _kod_gecerli_mi(uretilen_kod, dosya_adi):
                juri_2_onay = True
                print(f"      └ 🛡️ [Hakem 2 - NIM ({kisa_m})]: ONAYLANDI ✅")
            else:
                temiz = _saf_kod_ayir(yanit_2, dosya_adi)
                if _kod_gecerli_mi(temiz, dosya_adi):
                    juri_2_kod = temiz
                    print(f"      └ 🛡️ [Hakem 2 - NIM ({kisa_m})]: Geçerli iyileştirme önerisi sundu.")
                else:
                    print(f"      └ 🛡️ [Hakem 2 - NIM ({kisa_m})]: Öneri kod formatında değil/geçersiz (yoksayıldı).")
        except Exception as e:
            print(f"      └ ⚠️ [Hakem 2 - NIM]: Atlandı ({e}).")

    with ThreadPoolExecutor(max_workers=2) as jury_pool:
        f1 = jury_pool.submit(_run_hakem_1)
        f2 = jury_pool.submit(_run_hakem_2)
        f1.result()
        f2.result()

    if not juri_1_onay and not juri_2_onay and not juri_1_kod and not juri_2_kod:
        print(f"      └ 🔄 [Konsey Yeniden Deneme]: İki hakem de geçerli yanıt üretmedi; '{dosya_adi}' yeniden denetleniyor...")
        try:
            if dosya_adi.lower().endswith(".cs"):
                fmt_notu = f"```csharp ... ``` bloğu içinde sadece tam sınıf kodunu (`public class {sinif_adi}`) döndür."
            else:
                fmt_notu = f"'{dosya_adi}' dosyası için tek bir markdown kod bloğu içinde tam, çalışır saf kodu döndür."
            retry_prompt = (
                f"{prompt}\n\n"
                f"DİKKAT: Önceki yanıtın ayrıştırılamadı! "
                f"Lütfen ya tek kelime 'ONAYLANDI' yaz ya da {fmt_notu}"
            )
            yanit_retry = gemini_service.generate_with_retry(
                prompt=retry_prompt,
                system_instruction="Sadece ONAYLANDI veya tek bir markdown kod bloğu içinde tam, hatasız kaynak kodu döndür.",
                temperature=0.1,
                allow_nim_fallback=False
            )
            if "ONAYLANDI" in yanit_retry.upper() and len(yanit_retry.strip()) < 40 and _kod_gecerli_mi(uretilen_kod, dosya_adi):
                juri_1_onay = True
                print("      └ 🏛️ [Konsey Yeniden Deneme]: ONAYLANDI ✅")
            else:
                temiz_retry = _saf_kod_ayir(yanit_retry, dosya_adi)
                if _kod_gecerli_mi(temiz_retry, dosya_adi):
                    juri_1_kod = temiz_retry
                    print("      └ 🛠️ [Konsey Yeniden Deneme]: Geçerli düzeltilmiş kod üretildi.")
        except Exception as re_err:
            print(f"      └ ⚠️ [Konsey Yeniden Deneme Hatası]: {re_err}")

    if juri_1_onay and juri_2_onay:
        print("      └ 🟢 [Konsey Konsensüsü]: Heyet Oy Birliğiyle ONAYLADI!")
        return (True, uretilen_kod, "Hakem Konseyi Oy Birliğiyle ONAYLANDI")
    elif juri_1_kod and _kod_gecerli_mi(juri_1_kod, dosya_adi):
        print("      └ 🛠️ [Konsey Konsensüsü]: Hakem 1 iyileştirmesi mühürlendi.")
        return (True, juri_1_kod, "Konsey (Hakem 1) İyileştirmesiyle ONAYLANDI")
    elif juri_2_kod and _kod_gecerli_mi(juri_2_kod, dosya_adi):
        print("      └ 🛠️ [Konsey Konsensüsü]: Hakem 2 iyileştirmesi mühürlendi.")
        return (True, juri_2_kod, "Konsey (Hakem 2) İyileştirmesiyle ONAYLANDI")
    elif juri_1_onay:
        print("      └ 🟢 [Konsey Konsensüsü]: Baş Şef (Hakem 1) onayladı, sağlam kod mühürlendi.")
        return (True, uretilen_kod, "Baş Şef (Hakem 1) Onayıyla Mühürlendi")
    elif juri_2_onay:
        print("      └ 🟢 [Konsey Konsensüsü]: Uzman Hakem (Hakem 2) onayladı, sağlam kod mühürlendi.")
        return (True, uretilen_kod, "Uzman Hakem (Hakem 2) Onayıyla Mühürlendi")

    print(f"      └ ❌ [Konsey Uyarısı]: '{dosya_adi}' için hiçbir hakem onay vermedi! Doğrudan Şef QA/Revizyon sürecine aktarılıyor.")
    return (False, uretilen_kod, "Hakem Konseyi onay vermedi, revizyon gerekli.")


def konsey_kodu_denetle_ve_oyla(dosya_adi: str, uretilen_kod: str, gorev_tanimi: str) -> str:
    """Geriye dönük uyumlu konsey denetim fonksiyonu."""
    _, nihai_kod, _ = konsey_kodu_denetle_ve_oyla_detayli(dosya_adi, uretilen_kod, gorev_tanimi)
    return nihai_kod
