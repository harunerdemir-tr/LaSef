"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF BAŞ MİMAR (CHEF ARCHITECT) MODÜLÜ (agents/chef_architect.py)
═══════════════════════════════════════════════════════════════════════════════
📌 LASEF KORTEKS MANİFESTOSU — BAŞ MİMARIN AMACI:
LaSef (Lider Akıllı Sistemler ve Entegre Fabrika), otonom ve sözleşmeye dayalı
(contract-first) çalışan bir yapay zeka mühendislik fabrikasıdır.

Bu modül (ChefArchitect - Google Gemini):
1. Projenin niyet analizini ve öncü teknik şartnamesini hazırlar.
2. Hedef uygulama ortamını (Unity 3D, Web, Blender, Unreal vb.) anlar.
3. STANDART MCP & ARAÇ PRENSİBİ: Projeye denenmemiş veya işe yaramayan yapay
   MCP kodları eklenmez. Endüstri standardı UPM paketleri (CoplayDev/unity-mcp)
   veya yerel test edilmiş köprüler kullanılır.
4. Sıfır Kurulum (Zero-Setup) mimarisiyle, kullanıcının elle prefab bağlamasına
   gerek kalmadan runtime'da çalışan eksiksiz kod hiyerarşisi tasarlar.
═══════════════════════════════════════════════════════════════════════════════
"""
import re
import json
import time
from infrastructure.llm_client import cagir_gemini_sef, get_canli_havuz
from core.blackboard import AgentTask, ProjectPlan
from skills import ilgili_beceriyi_yukle
from core.mcp_router import detect_application_profile

def _json_temizle(ham_metin: str) -> str:
    metin = ham_metin.strip()
    md_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", metin, re.DOTALL)
    if md_match:
        metin = md_match.group(1).strip()
    ilk = metin.find("{")
    son = metin.rfind("}")
    if ilk != -1 and son != -1 and son > ilk:
        metin = metin[ilk:son + 1]
    metin = re.sub(r",\s*}", "}", metin)
    metin = re.sub(r",\s*]", "]", metin)
    metin = re.sub(r"^\s*//.*$", "", metin, flags=re.MULTILINE)
    return metin.strip()

def _is_readonly_inspection_request(metin: str) -> bool:
    """
    Kullanıcının yeni dosya/kod üretmek veya sahneyi değiştirmek yerine
    mevcut projeyi/sahneyi inceleme, listeleme veya soru sorma niyetinde olup olmadığını tespit eder.
    """
    kucuk = metin.lower().strip()
    if not kucuk:
        return False

    uretim_kaliplari = (
        "baştan yaz", "bastan yaz", "kod yaz", "script yaz", "dosya oluştur", "dosya olustur",
        "oyun yap", "uygulama yap", "site yap", "inşa et", "insa et", "tasarla ve kodla",
        "detaylandır", "detaylandir", "ekranı ekle", "ekrani ekle", "mekanikleri", "mekaniği", "mekanigi",
        "düzelt", "duzelt", "güncelle", "guncelle", "değiştir", "degistir",
        "geliştir", "gelistir", "çevir", "cevir", "dönüştür", "donustur",
        "görevin", "gorevin", "istiyorum", "olmalı", "olmali", "eklemen", "yapmanı", "yapmani",
        "sil ", "kaldır", "kaldir", "implement", "create a ", "build a ", "write code"
    )
    if any(u in kucuk for u in uretim_kaliplari):
        return False

    if re.search(r"\b(ekle|oluştur|olustur|kur|yaz|üret|uret|ata|bağla|bagla|geliştir|gelistir|çevir|cevir|yap|tasarla|düzenle|duzenle|iyileştir|iyilestir|büyüt|buyut)", kucuk):
        return False

    soru_kaliplari = (
        "?", "listele", "listeler misin", "neler var", "nedir", "ne işe", "ne ise",
        "açıkla", "acikla", "anlat", "özetle", "ozetle", "incele", "kontrol et",
        "kaç tane", "kac tane", "hangi ", "kim ", "nasıl ", "nasil ", "nerede",
        "durumu ne", "hiyerarşi", "hiyerarsi", "analiz et", "raporla", "gösterir misin", "gosterir misin"
    )
    return any(s in kucuk for s in soru_kaliplari)


def _is_targeted_active_agent_request(metin: str, kaynak_baglami: str = "") -> bool:
    """
    Çok dosyalı sıfırdan proje üretimi yerine, mevcut sahne veya tekil bir obje/bileşen üzerinde
    doğrudan araç çağıran ajan döngüsüyle (UnityAgentLoop / otonom_ajan_gorevi_yurut) yapılması uygun
    hedefli müdahale isteklerini tespit eder.
    """
    kucuk = metin.lower().strip()
    if len(kucuk) > 260 or "\n" in kucuk:
        return False
    if re.search(r"\b[12]\s*[\.\)]\s*görev", kucuk) or ("1." in kucuk and "2." in kucuk):
        return False
    if any(k in kucuk for k in ("derle", "hata", "konsol", "uyarı", "uyari", "error", "cs0", "cs1", "exception", "script", "düzelt", "duzelt", "çöz", "coz", "onar")):
        return False
    if any(k in kucuk for k in ("oyun yap", "oyunu yap", "projesi yap", "simülasyon", "simulasyon", "baştan yaz", "bastan yaz", "sıfırdan", "sifirdan")):
        return False
    sahne_mudahale = (
        "sahnedeki ", "sahnede ", "sahneye ", "hiyerarşideki ", "hiyerarsideki ",
        "objesine ", "objesini ", "nesnesine ", "nesnesini ", "bileşeni ekle", "bileseni ekle",
        "component ekle", "konumunu ", "pozisyonunu ", "ölçeğini ", "olcegini "
    )
    return any(s in kucuk for s in sahne_mudahale)


def niyet_analizi_yap(kullanici_istegi: str, kaynak_baglami: str = "", hedef_klasor: str = "") -> dict:
    """Kullanıcının niyetini anlamsal olarak analiz eder (SOHBET_SORU, AKTIF_AJAN veya PROJE_URETIM)."""
    metin = kullanici_istegi.strip()
    if len(metin) < 15 and metin.lower() in ["merhaba", "selam", "naber", "nasılsın", "hey", "günaydın"]:
        return {
            "tur": "SOHBET_SORU",
            "yanit": "Merhaba! Ben LaSef AI Orkestra Şefiyim. Geliştirmek istediğiniz projeyi veya hazırlamak istediğiniz teknik dokümanı belirtin; uzman ajanlarımla sizin için hemen hazırlayayım!"
        }

    if _is_readonly_inspection_request(metin):
        try:
            from agents.active_agent import otonom_ajan_gorevi_yurut
            yanit = otonom_ajan_gorevi_yurut(
                gorev=metin,
                hedef_klasor=hedef_klasor,
                max_adim=4,
                read_only=True,
                kaynak_baglami=kaynak_baglami,
            )
            if yanit and not yanit.startswith("[HATA"):
                return {"tur": "SOHBET_SORU", "yanit": yanit}
        except Exception:
            pass
        try:
            sistem = (
                "Sen LaSef Baş Mimarısın. Kullanıcının sorusunu sana verilen canlı Unity hiyerarşisi "
                "ve proje kaynak kodlarına dayanarak, hiçbir dosya oluşturmadan doğrudan, doğru ve öz Türkçe ile yanıtla."
            )
            prompt = f"KULLANICI SORUSU:\n{metin}\n\nMEVCUT PROJE VE SAHNE BAĞLAMI:\n{kaynak_baglami[:35000]}"
            return {"tur": "SOHBET_SORU", "yanit": cagir_gemini_sef(sistem, prompt, temperature=0.1)}
        except Exception as e:
            return {"tur": "SOHBET_SORU", "yanit": f"İnceleme sırasında hata oluştu: {e}"}

    if _is_targeted_active_agent_request(metin, kaynak_baglami):
        return {"tur": "AKTIF_AJAN", "aciklama": "Hedefli canlı sahne / dosya ajan müdahalesi"}

    return {"tur": "PROJE_URETIM", "aciklama": "Proje üretim ve geliştirme görevi"}

def oncu_ajan_kesfi(gorev_metni: str, kaynak_baglami: str = "", niyet_turu: str = "") -> str:
    beceri_rehberi = ilgili_beceriyi_yukle(gorev_metni)
    app_profile = detect_application_profile(gorev_metni, kaynak_baglami)

    prompt = f"""Sen dünya çapında bir Baş Yazılım Mimarı ve Sistem Mühendisisin.
Kullanıcı Talebi: '{gorev_metni}'.
Hedef Ortam: {app_profile.display_name} (Standart Çözüm: {app_profile.standard_package_name})
Kaynak Bağlamı: {kaynak_baglami[:12000]}
{beceri_rehberi}

GÖREVİN:
1. HEDEF MİMARİ VE DİL/PLATFORM (C/C++, C# Unity, Python, Web/HTML, vb.)
2. MODÜLER BİLEŞEN DAĞILIMI (Gereksiz dosya açma, tam ihtiyacı belirle)
3. ENTEGRASYON VE ÇALIŞABİLİRLİK (Denenmemiş harici MCP yazma; standart araçları kullan)
4. KALİTE VE ÇALIŞABİLİRLİK STANDARTLARI (Tüm fonksiyonlar satır satır tam dolu olacak)

Net ve maddeler halinde teknik şartnameyi yaz:"""
    try:
        return cagir_gemini_sef("Sen evrensel baş mimarsın. Teknik şartnameyi net hazırla.", prompt, temperature=0.1)
    except Exception:
        return f"1. GÖREV: '{gorev_metni}' eksiksiz, çalışan ve derinlemesine kodlanmalıdır."

def gorevi_planla(gorev_metni: str, kaynak_baglami: str = "", oncu_rehberi: str = "", canli_modeller: list = None) -> ProjectPlan:
    if not canli_modeller:
        canli_modeller = get_canli_havuz()

    katalog = "\n".join([f"- ID: \"{m}\"" for m in canli_modeller])
    app_profile = detect_application_profile(gorev_metni, kaynak_baglami)

    sistem_talimati = f"""Sen dünya çapında bir Baş Yapay Zeka Mimarı ve Otonom Sistem Orkestra Şefisin.
Kullanıcının isteğini ve şartnameyi analiz ederek projeyi EN DOĞRU DOSYA MODÜLLERİNE BÖL.

CANLI İŞÇİ MODELLER:
{katalog}

HEDEF UYGULAMA VE STANDART MCP PROFİLİ:
- Hedef: {app_profile.display_name}
- Standart Araç/Paket: {app_profile.standard_package_name}

MİMARİ KURALLARI:
1. KAPSAMLI VE %100 OTONOM OYNANABİLİR MİMARİ:
   - Kullanıcı Unity 3D oyunu istediğinde işi yarım bırakma; kullanıcının sahnede elle hiçbir Prefab sürüklemesine veya Inspector atamasına GEREK KALMADAN çalışacak mimari kur!
   - 🚨 KESİNLİKLE TEK DOSYA TEK CLASS KURALI (UNITY DERLEME GARANTİSİ):
     * Her C# dosyasında YALNIZCA dosya adıyla birebir aynı isimde TEK BİR `public class` bulunacaktır!
     * `GameBootstrapper.cs` içine asla `PlayerController` veya `GameManager` gibi diğer class'ları gömme; her sistem kendi bağımsız dosyasında yaşayacak!
   - 🚨 SIFIR KURULUM (ZERO-SETUP) VE [RuntimeInitializeOnLoadMethod]:
     * `GameBootstrapper.cs` sınıfında `[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]` kullanarak, kullanıcı sahneye HİÇBİR obje eklemese bile oyun başlar başlamaz sahneyi, `Player` karakterini, `Main Camera`yı ve diğer yöneticileri C# içinden otonom inşa et.
   - Gerekli tüm sistemleri (Örn: `GameBootstrapper.cs`, `PlayerController.cs`, `DynamicCamera.cs`, `TagGameManager.cs`, `PlayerTagLogic.cs`, `GameUIManager.cs`) eksiksiz ve derinlemesine modüllere böl.
2. ZORUNLU MODEL ATAMALARI:
   - Her modül için en uygun uzman canlı modeli ata.
3. SADECE JSON formatında döndür:
{{"proje_klasor_adi": "Proje_Adi", "moduller": [
  {{"adim": 1, "baslik": "Modül Başlığı", "dosya_adi": "dosya.uzanti", "tip": "KOD_YAZMA", "gorev": "Detaylı, derin ve sıfır bağımlılıkla çalışan görev tanımı...", "model_id": "<canli_model_id>", "bagimliliklar": []}}
]}}"""

    mesaj = f"GÖREV:\n{gorev_metni}\n\nŞARTNAME:\n{oncu_rehberi}"
    if kaynak_baglami:
        mesaj += f"\n\nREFERANS KAYNAK BAĞLAMI:\n{kaynak_baglami[:45000]}"
    
    for _ in range(2):
        try:
            ham = cagir_gemini_sef(sistem_talimati, mesaj, temperature=0.1)
            veri = json.loads(_json_temizle(ham))
            modul_listesi = []
            for m in veri.get("moduller", []):
                modul_listesi.append(AgentTask(
                    adim=m.get("adim", 1),
                    baslik=m.get("baslik", "Modül"),
                    dosya_adi=m.get("dosya_adi", "output.txt"),
                    tip=m.get("tip", "KOD_YAZMA"),
                    gorev=m.get("gorev", ""),
                    model_id=m.get("model_id") or canli_modeller[0],
                    bagimliliklar=m.get("bagimliliklar", [])
                ))
            return ProjectPlan(proje_klasor_adi=veri.get("proje_klasor_adi", f"Proje_{int(time.time())}"), moduller=modul_listesi)
        except Exception:
            continue

    return ProjectPlan(
        proje_klasor_adi=f"LaSef_Proje_{int(time.time())}",
        moduller=[AgentTask(adim=1, baslik="Ana Kod", dosya_adi="index.html", gorev=gorev_metni, model_id=canli_modeller[0])]
    )
