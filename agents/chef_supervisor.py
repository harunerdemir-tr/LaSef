"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF BAŞ ŞEF VE ORKESTRA SÜPERVİZÖRÜ (agents/chef_supervisor.py)
═══════════════════════════════════════════════════════════════════════════════
📌 LASEF KORTEKS MANİFESTOSU — BAŞ ŞEFİN GÖREV VE PRENSİPLERİ:
LaSef (Lider Akıllı Sistemler ve Entegre Fabrika), otonom ve sözleşmeye dayalı
(contract-first) çalışan bir yapay zeka mühendislik fabrikasıdır.

Bu sınıf (ChefSupervisor - Google Gemini):
1. Sistemdeki TEK BAŞ ŞEF'tir. Kullanıcının girdisini ve niyetini anlar.
2. Hedef uygulama ortamını (Unity, Web, Blender, Unreal vb.) tespit eder.
3. STANDART MCP KURALI: Projeye denenmemiş, işe yaramayan yapay MCP kodları
   ASLA entegre edilmez. Yalnızca test edilmiş endüstri standartları (UPM Git:
   CoplayDev/unity-mcp veya yerleşik LaSefBridgeServer.cs) önerilir ve kullanılır.
4. Karmaşık projeleri en ince parçalarına kadar uzman Amele Ajanlara böler
   (Single Responsibility).
5. Tüm amelelerin uyması zorunlu "Mimari Sözleşme"yi belirler ve çıktıları
   QA / Hakem Konseyi ile denetleyip mühürler.
═══════════════════════════════════════════════════════════════════════════════
"""
import os
import re
import json
import time
from typing import Tuple, List, Dict, Any, Optional

from infrastructure.gemini_client import gemini_service
from core.blackboard import ProjectPlan, AgentTask, SharedBlackboard
from core.task_queue import TaskItem
from capabilities.registry import capability_registry
from agents.council_engine import konsey_kodu_denetle_ve_oyla, konsey_kodu_denetle_ve_oyla_detayli
from core.mcp_router import detect_application_profile, MCPAppProfile

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


def _guvenli_json_yukle(ham_metin: str) -> Dict[str, Any]:
    r"""
    Modelin JSON string değerleri içinde kaçışsız çift tırnak (örn. "Arial.ttf" veya "LegacyRuntime.ttf")
    veya geçersiz ters eğik çizgi (\' ya da Windows yolu Assets\Editor) bırakması durumunda
    satır bazlı iç tırnakları ve kaçışları otomatik onarıp JSON yükler.
    """
    temiz = _json_temizle(ham_metin)
    temiz = temiz.replace("\\'", "'")
    temiz = re.sub(r'\\(?![/\"\\bfnrtu])', r'\\\\', temiz)
    try:
        return json.loads(temiz)
    except json.JSONDecodeError:
        pass

    onarilmis_satirlar = []
    anahtar_deseni = re.compile(r'^(\s*"(?:proje_klasor_adi|hedef_aciklama|mimari_sozlesme|baslik|capability|dosya_adi|gorev)"\s*:\s*")(.*)("(\s*,?\s*))$')
    for satir in temiz.splitlines():
        m = anahtar_deseni.match(satir)
        if m:
            on_ek, ic_metin, son_ek, _ = m.groups()
            ic_temiz = re.sub(r'(?<!\\)"', "'", ic_metin)
            onarilmis_satirlar.append(f"{on_ek}{ic_temiz}{son_ek}")
        else:
            onarilmis_satirlar.append(satir)

    onarilmis = "\n".join(onarilmis_satirlar)
    return json.loads(onarilmis)

class ChefSupervisor:
    """
    👑 ŞEF AJAN (Orchestrator / Supervisor) — Sistemde Tek Bir Tane
    - Model: Google Gemini API (gemini-3.6-flash veya .env üzerinden).
    - Evrensel Niyet Analizi (Intent Classification): Oyun, rapor, video, denetim, web vb. her isteği anlar.
    - Dinamik Amele Görevlendirme: İhtiyaca göre 1 ila 20+ amele ajan planlar.
    - Sürekli Gözetim & QA Denetimi: Amelelerin çıktılarını denetler, yetersizse revizyona gönderir,
      yeterliyse onaylar.
    - Hakem Konseyi (Council Engine) Entegrasyonu: Kritik kodlar için çoklu LLM oylamasını devreye sokar.
    - Standart MCP Uygulama Tespiti: Hedef ortama (Unity, Web vb.) göre en uygun denenmiş MCP profilini seçer.
    - Nihai kontrol ve karar yetkisi HER ZAMAN Şef'tedir.
    """
    def __init__(self):
        self.gemini = gemini_service

    def niyet_ve_gorev_plani_yap(self, kullanici_istegi: str, kaynak_baglami: str = "", blackboard: Optional[SharedBlackboard] = None) -> ProjectPlan:
        """
        Kullanıcının serbest metin isteğini analiz eder;
        alt görevleri, gereken amele sayılarını ve uzmanlıklarını (capabilities) dinamik olarak belirler.
        """
        print(f"\n👑 [BAŞ ŞEF (Gemini)] İstek analiz ediliyor ve otonom iş planı çıkarılıyor...")

        app_profile: MCPAppProfile = detect_application_profile(kullanici_istegi, kaynak_baglami)
        print(f"   🎯 [Uygulama & MCP Tespiti]: {app_profile.display_name}")
        print(f"      └ Standard: {app_profile.standard_package_name}")

        caps = capability_registry.list_all()
        uzmanlik_listesi = "\n".join([f"- {c.name}: {c.description}" for c in caps])

        sistem_talimati = f"""Sen dünya çapında bir Baş Yapay Zeka Mimarı, Sistem Mühendisi ve Otonom Süpervizör Şefsin.
Kullanıcının serbest metin isteğini derinlemesine analiz et.
Bu istek; bir 2D/3D oyun, teknik rapor, video senaryosu/promptu, güvenlik/kod denetimi, web uygulaması veya gömülü sistem olabilir.
Tüm alanları anlayabilmeli ve en optimize modüler alt görevlere bölmelisin.

HEDEF UYGULAMA VE ENTEGRASYON PROFİLİ:
- Hedef Platform: {app_profile.display_name} ({app_profile.app_key})
- Standart Araç/Paket: {app_profile.standard_package_name}
- Kural: Projeye denenmemiş veya işe yaramayan yapay MCP kodları yazma! Resmi paketlere ve yerleşik köprülere sadık kal.

MEVCUT UZMANLIK (CAPABILITY) LİSTESİ:
{uzmanlik_listesi}

KURALLAR:
1. 👑 ŞEFİN DERİN MODÜLER DEKOMPOZİSYONU (ZENGİN ÇOKLU AJAN ORKESTRASYONU):
   - Sen bir Orkestra Şefisin! Karmaşık bir projeyi (özellikle 3D/2D oyunlar, tam teşekküllü web uygulamaları) 3-4 kaba dosyada çözmeye kalkışma.
   - İşi profesyonel bir yazılım stüdyosu gibi EN İNCE MİMARİ PARÇALARINA KADAR DİNAMİK OLARAK UZMAN AMELERE BÖL (İhtiyaca göre 6 ila 12+ uzman amele görevlendir)!
   - Örneğin bir 3D Arena / Hayatta Kalma Oyunu için şu uzmanlıkları bağımsız görevlendir:
     • [Adım 1] PlayerMovement / PlayerController (Karakter Hareketi, Fizik, Zıplama)
     • [Adım 2] PlayerShooting / WeaponSystem (Silah, Ateş Etme, Mermi/Raycast, Cephane)
     • [Adım 3] HealthSystem (Ortak Can, Hasar Alma ve Ölüm Mantığı - Hem oyuncu hem düşman için)
     • [Adım 4] EnemyAI (Düşman Yapay Zekası, Takip, AABB/NavMesh, Saldırı)
     • [Adım 5] EnemyWaveSpawner (Dalga/Wave Yönetimi, Zamanla Zorlaşan Düşman Doğurma)
     • [Adım 6] GameManager (Oyun Durumu: Başlama, Skor, Dalga Sayacı, Game Over)
     • [Adım 7] UIManager / HUD (Can Barı, Skor Sayacı, Mermi Arayüzü, Game Over Paneli)
     • [Adım 8] ArenaBuilder / SceneAssembler (Tüm bu nesneleri sahnede canlı kurup scriptleri bağlayan kurucu)
   - Her amele tek bir sorumluluğa (Single Responsibility) odaklanır; böylece modeller şişmez, token hatası vermez ve kodlar kusursuz çalışır!

2. 🌳 WORKTREE AĞAÇ DALI İZOLASYON KURALI (DALLAR KESİŞMEZ, KÖKTEN BESLENİR):
   - Her amele ajanın 'dosya_adi' ve sınırları kristal netliğinde olmalıdır. Hiçbir amele başka bir amelenin dosyasına müdahale edemez.
   - Bir amele yalnızca 'bagimliliklar' dizisinde belirtilen üst adımların (kökün) çıktılarını okuyabilir; birbirinin sahasına giremez.
   - En son entegrasyon dosyası (veya Şef), üretilen tüm bağımsız dalları tek çatı altında eksiksiz birleştirir.
   - 🌐 WEB / TEK DOSYA `index.html` PARALEL MODÜL KURALI: Kullanıcı "tek bir index.html dosyası" istese bile ASLA birden fazla ajana aynı `dosya_adi: "index.html"` atama ve adımları 1->2->3->4 diye zincirleme! Bunun yerine bağımsız paralel modüller planla (`styles.css`, `audio.js`, `gameCore.js`, `uiManager.js` gibi `bagimliliklar: []`) ki 4 amele aynı anda paralel üretsin; yalnızca SON birleştirici adıma `index.html` (`bagimliliklar: [önceki tüm adımlar]`) ver. Sistem finalde tüm CSS ve JS dosyalarını tek `index.html` içine otomatik gömer!

3. 🎮 UNITY PROJELERİ İÇİN KESİN SIFIR KURULUM & MEVCUT PROJE KORUMA KURALLARI:
   - Unity 3D projelerinde ASLA 2D fizik (Rigidbody2D, Collider2D, Vector2) kullanma; kesinlikle 3D fizik ve yapılar (Rigidbody, CharacterController, Collider, Vector3) kullan!
   - Unity C# dosyalarında 'dosya_adi' ile içindeki 'class' adı birebir aynı olmalıdır (Örn: 'GameManager.cs' içinde 'public class GameManager : MonoBehaviour'). Asla sınıf adında boşluk olamaz!
   - ASLA başka dosyaların sınıflarını veya enumlarını (PlayerController, GameManager, EnemyType, GameState vb.) ikinci bir dosyada yeniden tanımlama (CS0101 mükerrer tanım hatası yaratır)!
   - ASLA 'namespace Global {{ ... }}' bloğu AÇMA! Unity sınıfları gerçek global alanda (hiçbir namespace bloğu olmadan) tanımlanmalıdır! Mevcut projede 'namespace Global' yüzünden CS0246/CS0234 hatası varsa o dosyalardan 'namespace Global' sarmalını kaldırıp global alana al!
   - ASLA UnityEngine.Object / GetComponent<T>() üzerinde C# '??' operatörü kullanma (MissingComponentException üretir); daima 'var c = GetComponent<T>(); if (c == null) c = ...AddComponent<T>();' yaz!
   - 'Assets/Scripts/' altındaki runtime scriptlerinde ASLA 'using UnityEditor;' veya 'UnityEditor.*' kullanma (sadece '#if UNITY_EDITOR' içinde veya 'Assets/Editor/' altında kullan)!
   - 🛑 MEVCUT SAHNEYİ KORUMA vs SIFIRDAN KURMA:
     * Kaynak bağlamında mevcut sahnede nesneler (>= 4 kök nesne) ve 'Assets/Scripts/' dosyaları zaten varsa: kullanıcı açıkça 'sahneyi sıfırla' demedikçe ASLA 'DestroyImmediate' ile mevcut Canvas/Player/Ground/EventSystem nesnelerini yok eden bir SceneBuilder yazma ve sahneye ikinci bir Ground, ikinci bir Player/Hero veya ikinci bir Canvas ekleme! Mevcut 'Player', 'Main Camera', 'GameCanvas'/'UIManager' objelerini bulup güncelle.
     * Kullanıcı yalnızca sıfırdan yeni bir oyun istediğinde veya sahne boşken son adım olarak 'Assets/Editor/<ProjeAdi>SceneBuilder.cs' (public static void BuildScene()) planla.
   - 🚨 HATA ONARIM GÖREVLERİ KURALI:
     * Kullanıcı derleme hatası, konsol hatası veya uyarı (warning) çözmeni istediğinde ASLA 'GlobalNamespaceFix.cs', 'CodeAudit.cs', 'BuildReport.txt' gibi yeni uydurma dosya/rapor modülleri planlama!
     * Doğrudan canlı konsol/Roslyn çıktısında adı geçen GERÇEK mevcut C# dosyalarını (örn. 'Assets/Scripts/CameraManager.cs', 'Assets/Scripts/PlayerController.cs', 'Assets/Editor/GameUpgradeSceneBuilder.cs') tam proje göreli yoluyla hedef dosya olarak planla ki orkestra doğrudan o hatalı dosyaları onarsın!

4. 📜 MİMARİ SÖZLEŞME VE STANDARTLAR KANUNU (CONTRACT-FIRST ARCHITECTURE):
   - Her amele ajanın uyması ZORUNLU olan küresel mimari sözleşmeyi ('mimari_sozlesme') kristal netliğinde tanımla!
   - Unity için: 'Namespace: HİÇBİR namespace bloğu açma (gerçek C# global alanı, ASLA namespace Global yazma), Boyut: 3D (Rigidbody, CharacterController, BoxCollider/CapsuleCollider, Vector3; ASLA BoxCollider2D/Physics2D/Collider2D/OnTriggerEnter2D YOK, soyut AddComponent<Collider>() YOK, GameObject.mesh YOK), Fake-Null: GetComponent<T>() ?? AddComponent<T>() YASAK (if (c == null) kullan), UI: CanvasScaler/GraphicRaycaster/Text/Button/Slider/Image icin using UnityEngine.UI zorunlu, Font olarak Resources.GetBuiltinResource<Font>(\'LegacyRuntime.ttf\') kullan (ASLA Arial.ttf yok), NavMeshAgent kullaniliyorsa agent.isOnNavMesh kontrolu olmadan ResetPath/SetDestination cagirma, Unity 6 API: FindObjectsByType/FindFirstObjectByType kullanilacak, Yasak: [ReadOnly] attribute yok, Assets/Scripts içinde çıplak UnityEditor çağrısı yok.'
   - Web için: 'Ortak DOM ID listesi, CSS class kuralları, script hiyerarşisi.'
   - Rapor/Belge için: 'Ortak şema, veri kaynakları, stil kuralları.'
   Bu sözleşme her amele ajanın sistem yönergesine KANUN olarak enjekte edilecektir.

5. ÇIKTI FORMATI: SADECE VE SADECE aşağıdaki geçerli JSON formatını döndür ('bagimliliklar' dizisinde dosya adı değil, bağlı olduğu üst adımların TAM SAYI 'adim' numaralarını yaz, örn: [1, 2]; JSON string değerlerinin içinde ASLA kaçışsız çift tırnak (") kullanma, iç metinlerde tek tırnak (') kullan!):
{{
  "proje_klasor_adi": "Proje_Adi",
  "hedef_aciklama": "Projenin genel mimari hedefi",
  "mimari_sozlesme": "Tüm amelelerin KESİNLİKLE uyması gereken katı mimari sözleşme kuralları...",
  "moduller": [
    {{
      "adim": 1,
      "baslik": "Modül Başlığı",
      "capability": "game-dev",
      "dosya_adi": "dosya.uzanti",
      "gorev": "Amele ajanın yapacağı detaylı, kesin sınırları çizilmiş görev yönergesi...",
      "bagimliliklar": []
    }}
  ]
}}"""

        mesaj = f"KULLANICI TALEBİ:\n'{kullanici_istegi}'"
        if kaynak_baglami:
            mesaj += f"\n\nKAYNAK / REFERANS BAĞLAMI:\n{kaynak_baglami[:45000]}"

        for deneme in range(3):
            try:
                ham = self.gemini.generate_with_retry(
                    prompt=mesaj,
                    system_instruction=sistem_talimati,
                    temperature=0.1
                )
                if blackboard:
                    chef_tokens = int((len(mesaj) + len(sistem_talimati) + len(ham)) / 3.5)
                    blackboard.record_token_usage("chef", chef_tokens)

                veri = _guvenli_json_yukle(ham)

                ham_moduller = veri.get("moduller", [])
                dosya_adim_haritasi = {}
                for idx, m in enumerate(ham_moduller):
                    adim_no = int(m.get("adim", idx + 1))
                    d_adi = str(m.get("dosya_adi", "")).strip()
                    if d_adi:
                        dosya_adim_haritasi[d_adi.lower()] = adim_no
                        dosya_adim_haritasi[os.path.basename(d_adi).lower()] = adim_no

                moduller = []
                for idx, m in enumerate(ham_moduller):
                    adim_no = int(m.get("adim", idx + 1))
                    ham_deps = m.get("bagimliliklar", []) or []
                    cozulmus_deps: List[int] = []
                    for dep in ham_deps:
                        if isinstance(dep, int):
                            if dep != adim_no and dep not in cozulmus_deps:
                                cozulmus_deps.append(dep)
                        elif isinstance(dep, str):
                            dep_str = dep.strip()
                            if dep_str.isdigit():
                                d_int = int(dep_str)
                                if d_int != adim_no and d_int not in cozulmus_deps:
                                    cozulmus_deps.append(d_int)
                            else:
                                eslesen = dosya_adim_haritasi.get(dep_str.lower()) or dosya_adim_haritasi.get(os.path.basename(dep_str).lower())
                                if eslesen and eslesen != adim_no and eslesen not in cozulmus_deps:
                                    cozulmus_deps.append(eslesen)

                    moduller.append(AgentTask(
                        adim=adim_no,
                        baslik=m.get("baslik", "Modül"),
                        dosya_adi=m.get("dosya_adi", "output.txt"),
                        tip="KOD_YAZMA" if not m.get("dosya_adi", "").endswith(".md") else "RAPOR",
                        gorev=m.get("gorev", ""),
                        capability=m.get("capability", "general"),
                        bagimliliklar=cozulmus_deps
                    ))

                if app_profile.app_key == "unity" and moduller:
                    hayali_isimler = {"buildreport.txt", "codeaudit.cs", "globalnamespacefix.cs"}
                    gercek_cs_var = any(
                        mod.dosya_adi.lower().endswith(".cs")
                        and os.path.basename(mod.dosya_adi).lower() not in hayali_isimler
                        for mod in moduller
                    )
                    if gercek_cs_var:
                        temiz_moduller = [
                            m for m in moduller
                            if os.path.basename(m.dosya_adi or "").lower() not in hayali_isimler
                        ]
                        if temiz_moduller:
                            kalan_adimlar = {m.adim for m in temiz_moduller}
                            for m in temiz_moduller:
                                m.bagimliliklar = [d for d in m.bagimliliklar if d in kalan_adimlar]
                            moduller = temiz_moduller

                    for m in moduller:
                        d = (m.dosya_adi or "").replace("\\", "/").strip()
                        if d.lower().endswith(".cs") and not d.lower().startswith("assets/"):
                            base_d = os.path.basename(d)
                            is_ed = any(k in base_d.lower() for k in ("editor", "scenebuilder", "builder"))
                            m.dosya_adi = f"Assets/Editor/{base_d}" if is_ed else f"Assets/Scripts/{base_d}"

                if app_profile.app_key == "web" and len(moduller) > 1:
                    html_indices = [
                        i for i, mod in enumerate(moduller)
                        if (mod.dosya_adi or "").strip().lower().endswith(".html")
                    ]
                    if len(html_indices) > 1:
                        used_names = {
                            (mod.dosya_adi or "").strip().lower()
                            for i, mod in enumerate(moduller)
                            if i not in html_indices
                        }
                        used_names.add("index.html")
                        last_html_idx = html_indices[-1]
                        disambiguated_steps = []
                        parallel_names: List[str] = []

                        for idx_m in html_indices[:-1]:
                            mod = moduller[idx_m]
                            title_low = (mod.baslik or "").lower()
                            if any(k in title_low for k in ("css", "stil", "tema", "arayüz")) and "styles.css" not in used_names:
                                new_fname = "styles.css"
                            elif any(k in title_low for k in ("ses", "audio", "müzik", "efekt")) and "audio.js" not in used_names:
                                new_fname = "audio.js"
                            else:
                                new_fname = f"module_{mod.adim}.js"
                            while new_fname.lower() in used_names:
                                new_fname = f"part_{mod.adim}_{len(used_names)}.js"
                            used_names.add(new_fname.lower())
                            mod.dosya_adi = new_fname
                            mod.bagimliliklar = []
                            mod.gorev = (
                                f"{mod.gorev}\n\n[MODÜL KURALI]: Bu dosyada <html> veya <body> kök etiketi YAZMA; "
                                f"yalnızca kendi sorumluluğundaki temiz saf {'CSS' if new_fname.endswith('.css') else 'Vanilla JS'} "
                                f"kodunu üret. Finalde 'index.html' içine otomatik gömülecektir."
                            )
                            disambiguated_steps.append(mod.adim)
                            parallel_names.append(new_fname)

                        last_mod = moduller[last_html_idx]
                        last_mod.dosya_adi = "index.html"
                        existing_deps = set(last_mod.bagimliliklar)
                        for sid in disambiguated_steps:
                            if sid != last_mod.adim:
                                existing_deps.add(sid)
                        last_mod.bagimliliklar = sorted(existing_deps)
                        last_mod.gorev = (
                            f"{last_mod.gorev}\n\n[ENTEGRASYON NOTU]: Paralel üretilen şu modülleri bağla: "
                            f"{', '.join(parallel_names)} (<link rel='stylesheet'> / <script src=...>). "
                            f"Ortak DOM ID sözleşmesine birebir uy; sistem finalde bunları tek index.html içine gömecektir."
                        )

                sozlesme_metni = veri.get("mimari_sozlesme", "")
                if app_profile.app_key != "general":
                    sozlesme_metni += f"\n\n[UYGULAMA MİMARİSİ VE STANDART ENTEGRASYON]:\nHedef Ortam: {app_profile.display_name}\nÖnerilen Standart Çözüm: {app_profile.standard_package_name}\nHarici denenmemiş MCP kodu yazılmaz; yerleşik ve standart araçlar esastır."

                plan = ProjectPlan(
                    proje_klasor_adi=veri.get("proje_klasor_adi", f"LaSef_Proje_{int(time.time())}"),
                    moduller=moduller,
                    hedef_aciklama=veri.get("hedef_aciklama", kullanici_istegi),
                    architecture_contract=sozlesme_metni
                )

                if blackboard and sozlesme_metni:
                    blackboard.set_architecture_contract(sozlesme_metni)

                print(f"   └ 🟢 [Şef Planı Hazır]: {len(plan.moduller)} Amele Görevi Tanımlandı (Hedef: {plan.proje_klasor_adi})")
                if sozlesme_metni:
                    print(f"      📜 [Mimari Sözleşme Kilitlendi]: {sozlesme_metni[:120]}...")
                for m in plan.moduller:
                    deps = f"(Bağımlı: {m.bagimliliklar})" if m.bagimliliklar else "(Bağımsız Kök)"
                    print(f"      • [Adım {m.adim}] {m.dosya_adi} [{m.capability}] {deps} -> {m.baslik}")

                return plan

            except Exception as e:
                print(f"   ⚠️ [Şef Planlama Deneme {deneme+1} Hatası]: {e}")
                time.sleep(1.0)

        print(f"   ⚠️ [Şef]: JSON ayrıştırma yedeği devreye alınıyor (Hedef: {app_profile.app_key})...")
        if app_profile.app_key == "unity":
            return ProjectPlan(
                proje_klasor_adi=f"Unity_Proje_{int(time.time())}",
                moduller=[
                    AgentTask(
                        adim=1,
                        baslik="Oyun Mekanikleri ve Sistem Geliştirmesi",
                        dosya_adi="Assets/Scripts/CustomGameplayUpgrade.cs",
                        gorev=f"Kullanıcı talebindeki oyun mekaniklerini eksiksiz Unity 6 3D C# scripti olarak uygula:\n{kullanici_istegi}",
                        capability="unity-dev",
                        bagimliliklar=[]
                    ),
                    AgentTask(
                        adim=2,
                        baslik="Canlı Sahne Kurucu ve Entegratör",
                        dosya_adi="Assets/Editor/CustomUpgradeSceneBuilder.cs",
                        gorev=f"Kullanıcı talebindeki tüm nesneleri ve scriptleri canlı Unity sahnesine kuran BuildScene() metoduna sahip Editor scriptini yaz:\n{kullanici_istegi}",
                        capability="unity-dev",
                        bagimliliklar=[1]
                    )
                ],
                hedef_aciklama=kullanici_istegi
            )
        elif app_profile.app_key == "web":
            return ProjectPlan(
                proje_klasor_adi=f"Web_Proje_{int(time.time())}",
                moduller=[
                    AgentTask(adim=1, baslik="Web Uygulaması", dosya_adi="index.html", gorev=kullanici_istegi, capability="frontend-ui")
                ],
                hedef_aciklama=kullanici_istegi
            )
        return ProjectPlan(
            proje_klasor_adi=f"LaSef_Gorev_{int(time.time())}",
            moduller=[
                AgentTask(adim=1, baslik="Proje Çıktısı", dosya_adi="PROJE_COZUMU.md", gorev=kullanici_istegi, capability="general")
            ],
            hedef_aciklama=kullanici_istegi
        )

    def qa_denetle_ve_onayla(
        self,
        task: TaskItem,
        cikan_icerik: str,
        blackboard: SharedBlackboard,
        use_council: bool = True
    ) -> Tuple[bool, str]:
        """
        Şef'in QA Onay Mekanizması:
        - Token tasarrufu: Konsey heyeti onaylamışsa veya statik kontroller sağlamsa ek Gemini tokenı harcamaz.
        - Kod dosyalarında Hakem Konseyi'ni (council_engine) devreye sokar.
        """
        if not cikan_icerik or len(cikan_icerik.strip()) < 50:
            return (False, "Çıktı boş veya kabul edilemeyecek kadar kısa.")

        dosya = task.target_file
        uzanti = os.path.splitext(dosya)[1].lower()

        if uzanti == ".html":
            c_low = cikan_icerik.lower()
            if len(cikan_icerik.strip()) < 500:
                return (False, f"HTML dosyası çok kısa ({len(cikan_icerik)} bayt). Eksiksiz yazılmalıdır.")
            if "<html" not in c_low or "</html>" not in c_low:
                return (False, "Eksik HTML yapısı: <html> ve </html> kök etiketleri bulunamadı.")
            
            istenen_aciklama = task.instruction.lower()
            canvas_gerekli = any(k in istenen_aciklama for k in ["canvas", "2d render", "arcade", "fizik motoru", "platformer", "flappy"])
            
            if canvas_gerekli:
                if "<canvas" not in c_low or "getcontext" not in c_low:
                    return (False, "Eksik DOM bileşeni: Görev için gerekli <canvas> veya 2D render context tanımlanmamış.")
            else:
                has_ui_element = any(el in c_low for el in ["<canvas", "<table", "grid", "board", "cell", "<button", "<div id=", "class="])
                if not has_ui_element:
                    return (False, "Eksik Arayüz Bileşeni: Sayfada etkileşimli bir oyun/uygulama alanı (<canvas>, grid, board veya table) bulunamadı.")

            if "<script" not in c_low or "</script>" not in c_low:
                return (False, "Eksik Etkileşim: <script> blokları ve JavaScript uygulama mantığı bulunamadı.")

            if "game initialized" in c_low and len(cikan_icerik.strip()) < 800:
                return (False, "Sahte/Boş stub kodu tespit edildi. Gerçek uygulama mantığı üretilmelidir.")

        if cikan_icerik.startswith("[BINARY_MEDIA_FILE:"):
            f_path = cikan_icerik.split("[BINARY_MEDIA_FILE:")[1].split("]")[0].strip()
            if os.path.exists(f_path) and os.path.getsize(f_path) > 300:
                boyut = os.path.getsize(f_path)
                print(f"   └ 🖼️/🎬 [Şef QA Medya Onayı]: {task.target_file} ({boyut / 1024:.1f} KB gerçek binary dosya)")
                return (True, "Gerçek Medya Dosyası Doğrulandı ve ONAYLANDI")
            return (False, "Medya dosyası fiziksel olarak oluşturulamadı veya boş.")

        if use_council and uzanti in [".cs", ".js", ".py", ".html", ".cpp", ".c"]:
            try:
                if blackboard:
                    blackboard.record_token_usage("council", int((len(dosya) + len(cikan_icerik) + len(task.instruction)) / 3.5))

                konsey_onay, iyilestirilmis_kod, konsey_mesaj = konsey_kodu_denetle_ve_oyla_detayli(dosya, cikan_icerik, task.instruction)
                if konsey_onay:
                    if iyilestirilmis_kod != cikan_icerik:
                        blackboard.set_artifact(dosya, iyilestirilmis_kod)
                        task.output = iyilestirilmis_kod
                    return (True, konsey_mesaj)
                else:
                    print(f"   ⚠️ [QA Konsey]: '{dosya}' için konsey onayı çıkmadı ({konsey_mesaj}). Şef doğrudan denetliyor...")
            except Exception as e:
                print(f"   ⚠️ [QA Konsey Uyarısı]: {e}")

        prompt = f"""Sen Baş Mimar ve Kalite Güvence (QA) Süpervizörüsün.
Amele ajanın ürettiği çıktıyı denetle.

GÖREV: {task.instruction}
HEDEF DOSYA: {task.target_file}

ÜRETİLEN İÇERİK:
\"\"\"
{cikan_icerik[:15000]}
\"\"\"

KURALLAR:
1. İçerik verilen görevi ve teknik standartları karşılıyor mu?
2. Geçerliyse SADECE "ONAYLANDI" yaz.
3. Ciddi bir eksik veya mantık hatası varsa: "RED: <eksik ve yapılması gereken net düzeltme>" yaz."""

        try:
            degerlendirme = self.gemini.generate_with_retry(
                prompt=prompt,
                system_instruction="Sen tavizsiz bir Baş Mühendis ve QA Denetçisisin.",
                temperature=0.1
            )
            if blackboard:
                blackboard.record_token_usage("chef", int((len(prompt) + len(degerlendirme)) / 3.5))
            if "ONAYLANDI" in degerlendirme.upper() and len(degerlendirme.strip()) < 40:
                return (True, "ONAYLANDI")
            elif "RED:" in degerlendirme:
                sebep = degerlendirme.split("RED:")[1].strip()
                return (False, sebep)
            else:
                return (True, "ONAYLANDI")
        except Exception as e:
            if uzanti == ".html" and len(cikan_icerik) > 3000 and "<canvas" in cikan_icerik:
                return (True, "Yerel Statik Denetimle Onaylandı (LLM Çevrimdışı)")
            elif uzanti == ".md" and len(cikan_icerik) > 200:
                return (True, "Yerel Statik Doküman Onayı")
            return (False, f"QA denetim hatası ve statik yetersizlik: {e}")

chef_supervisor = ChefSupervisor()
