import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.blackboard import SharedBlackboard, AgentTask
from agents.worker_agent import isci_ajani_calistir
from skills import ilgili_beceriyi_yukle

def _isci_sistem_rolu_olustur(dosya_adi: str, gorev_metni: str) -> str:
    """İşçi ajanın sistem rolünü, dosya türüne ve projenin ihtiyacına göre derinlemesine oluşturur."""
    uzanti = os.path.splitext(dosya_adi)[1].lower()
    
    temel = f"Sen dünya çapında bir Kıdemli Yazılım Geliştiricisisin. SADECE '{dosya_adi}' dosyasının eksiksiz, çalışan saf kodunu üret."
    
    if uzanti == ".cs":
        temel += """

🚨 UNITY C# ZORUNLU MİMARİ KURALLARI (MUTLAKA UYGULANACAK):
1. SIFIR KURULUM (ZERO-SETUP) İLKESİ:
   - Kullanıcı Unity sahnesinde ELLERİYLE hiçbir şey yapmak zorunda KALMAMALIDIR!
   - Eğer bu dosya GameBootstrapper veya ana başlatıcı ise: `[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]` kullanarak STATIC bir metod yaz. Bu metod sahneye HİÇBİR obje eklenmese bile Play butonuyla otomatik çalışsın.
   - Karakter, Kamera, Zemin, Işık ve tüm Level objelerini `GameObject.CreatePrimitive()` ve `new GameObject()` ile KOD İÇİNDEN oluştur.
   - ASLA [SerializeField] veya public değişkenle Inspector'dan Prefab/Referans bekleme!
   - ASLA 'sahneye X objesi ekleyin ve bu scripti sürükleyin' deme!
2. Tüm bağımlılıkları (diğer scriptleri) `FindObjectOfType<>()` veya `GetComponent<>()` ile runtime'da bul.
3. Fonksiyon gövdelerini asla boş bırakma; her fonksiyonun içi satır satır dolu ve çalışır olacak."""
    
    skill_eki = ilgili_beceriyi_yukle(gorev_metni)
    if skill_eki:
        temel += f"\n{skill_eki}"
    
    return temel

def tek_adimi_yurut(adim: AgentTask, oncu_rehberi: str, blackboard: SharedBlackboard) -> tuple:
    sistem_rolu = _isci_sistem_rolu_olustur(adim.dosya_adi, adim.gorev)
    talimat = f"GÖREV:\n{adim.gorev}\n\nÖNCÜ ŞARTNAME:\n{oncu_rehberi}"
    
    dom_bilgisi = blackboard.dom_haritasini_al()
    kod = isci_ajani_calistir(
        model_id=adim.model_id,
        sistem_rolu=sistem_rolu,
        gorev_talimati=talimat,
        adim_no=adim.adim,
        dosya_adi=adim.dosya_adi,
        dom_haritasi=dom_bilgisi
    )
    return (adim.adim, kod, adim.dosya_adi)

def dag_ile_paralel_yurut(plan_modulleri: list, oncu_rehberi: str, kaynak_baglami: str, max_workers: int = 8) -> tuple:
    blackboard = SharedBlackboard(kaynak_baglami)
    adim_dosya_haritasi = {}

    print(f"\n⚡ Zincirleme DAG Mimarisinde {len(plan_modulleri)} Uzman Ajan Başlatılıyor...")
    baslangic = time.time()

    oncu_moduller = [m for m in plan_modulleri if m.dosya_adi.lower().endswith(".html")]
    bagimli_moduller = [m for m in plan_modulleri if not m.dosya_adi.lower().endswith(".html")]

    if not oncu_moduller:
        oncu_moduller = []
        bagimli_moduller = plan_modulleri

    for adim in oncu_moduller:
        adim_dosya_haritasi[adim.adim] = adim.dosya_adi
        model_kisa = adim.model_id.split('/')[-1]
        print(f"   ├─ 🚀 [1. Aşama - HTML İskeleti] {adim.dosya_adi} ({model_kisa}) başlatıldı...")
        try:
            adim_no, kod, dosya_adi = tek_adimi_yurut(adim, oncu_rehberi, blackboard)
            blackboard.cikti_yaz(adim_no, kod, dosya_adi)
            dom_ozeti = blackboard.dom_haritasini_al()
            print(f"   └─ 🟢 [1. Aşama Tamamlandı] {dosya_adi} üretildi. ({len(dom_ozeti.get('tum_idler', []))} ID çıkarıldı)")
        except Exception as e:
            print(f"[HATA] HTML öncü ajan hatası: {e}")

    if bagimli_moduller:
        print(f"   ├─ ⚡ [2. Aşama - Paralel DAG] {len(bagimli_moduller)} Uzman Ajan Başlatılıyor...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_adim = {}
            for adim in bagimli_moduller:
                adim_dosya_haritasi[adim.adim] = adim.dosya_adi
                model_kisa = adim.model_id.split('/')[-1]
                print(f"   ├─ [Adım {adim.adim}] {adim.dosya_adi} ({model_kisa}) fırlatıldı...")
                fut = executor.submit(tek_adimi_yurut, adim, oncu_rehberi, blackboard)
                future_to_adim[fut] = adim.adim

            for future in as_completed(future_to_adim):
                try:
                    adim_no, kod, dosya_adi = future.result()
                    blackboard.cikti_yaz(adim_no, kod, dosya_adi)
                except Exception as e:
                    print(f"[HATA] Adım {future_to_adim.get(future)} hatası: {e}")

    print(f"⏱️ Zincirleme DAG orkestrasyonu {time.time() - baslangic:.2f} saniyede tamamlandı.")
    return (blackboard._memory, adim_dosya_haritasi)
