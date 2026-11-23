"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF ORTAK DURUM DEPOSU VE VERİ TABLOSU (core/blackboard.py)
═══════════════════════════════════════════════════════════════════════════════
📌 LASEF KORTEKS MANİFESTOSU — ORTAK BİLGİ MERKEZİ (BLACKBOARD):
LaSef'te tüm ajanlar (Şef, Uzman Ameleler, Hakem Konseyi) senkronizasyonunu
ve veri akışını bu ortak pano (SharedBlackboard) üzerinden yürütür.

ÖNEMLİ PRENSİPLER:
1. WORKTREE DAL İZOLASYONU: Ameleler yalnızca bağımlı oldukları adımların
   kodlarını okuyabilir; yabancı dalların sahasına giremez.
2. MİMARİ SÖZLEŞME: Şef'in koyduğu katı mimari kurallar Blackboard'da kilitlenir
   ve her amele ajana bağlayıcı bir yasa olarak iletilir.
3. STANDART ENTEGRASYON BİLGİSİ: Hedef uygulamanın (Unity, Web, Blender vb.)
   standart MCP ve araç gereksinimleri burada tutulur; projeye denenmemiş
   yapay MCP kodu sızdırılmaz.
═══════════════════════════════════════════════════════════════════════════════
"""
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class AgentTask:
    adim: int
    baslik: str
    dosya_adi: str
    tip: str = "KOD_YAZMA"
    gorev: str = ""
    model_id: str = ""
    gorsel_prompt: str = ""
    bagimliliklar: List[int] = field(default_factory=list)
    capability: str = "general"

@dataclass
class ProjectPlan:
    proje_klasor_adi: str
    moduller: List[AgentTask]
    optimizasyon_ozeti: Dict[str, Any] = field(default_factory=dict)
    hedef_aciklama: str = ""
    architecture_contract: str = ""

def html_dom_idlerini_cikar(html_kodu: str) -> dict:
    """HTML kodundaki canvas, id ve class listesini ayıklar."""
    sonuc = {"canvas_id": None, "tum_idler": [], "tum_classlar": []}
    canvas_m = re.search(r'<canvas[^>]+id=["\']([^"\']+)["\']', html_kodu, re.IGNORECASE)
    if canvas_m:
        sonuc["canvas_id"] = canvas_m.group(1)
    sonuc["tum_idler"] = list(set(re.findall(r'\bid=["\']([^"\']+)["\']', html_kodu)))
    sonuc["tum_classlar"] = list(set(re.findall(r'\bclass=["\']([^"\']+)["\']', html_kodu)))
    return sonuc

class SharedBlackboard:
    """
    Gelişmiş Çoklu Ajan Ortak Durum Deposu (Shared Blackboard).
    - Ajanların ara çıktılarının (intermediate data) canlı paylaşımı
    - Nihai üretilen dosyaların/artefaktların depolanması
    - Şef kararlarının ve revizyon notlarının kaydı
    - Geriye dönük DOM haritası ve bellek uyumluluğu
    """
    def __init__(self, kaynak_dosya_baglami: str = ""):
        self._memory: Dict[int, str] = {}
        self._artifacts: Dict[str, str] = {}
        self._intermediate_data: Dict[str, Any] = {}
        self._decisions: List[Dict[str, Any]] = []
        self._gorseller: Dict[int, Any] = {}
        self._dom_haritasi: Dict[int, dict] = {}
        self._kaynak_baglami: str = kaynak_dosya_baglami
        self._architecture_contract: str = ""
        self._lock = threading.RLock()
        self._eszamanlilik_log: List[dict] = []
        self._step_file_map: Dict[int, str] = {}
        self._token_stats: Dict[str, int] = {"chef": 0, "workers": 0, "council": 0, "total": 0}

    def cikti_yaz(self, adim_no: int, cikti: str, dosya_adi: str = ""):
        with self._lock:
            self._memory[adim_no] = cikti
            if dosya_adi:
                self._artifacts[dosya_adi] = cikti
                self._step_file_map[adim_no] = dosya_adi
                if dosya_adi.lower().endswith(".html"):
                    self._dom_haritasi[adim_no] = html_dom_idlerini_cikar(cikti)

    def gorsel_yaz(self, adim_no: int, gorsel_bilgisi: dict):
        with self._lock:
            self._gorseller[adim_no] = gorsel_bilgisi

    def eszamanlilik_kaydet(self, adim_no: int, durum: str):
        with self._lock:
            self._eszamanlilik_log.append({
                "adim": adim_no,
                "durum": durum,
                "zaman": time.time(),
                "thread": threading.current_thread().name
            })

    def dom_haritasini_al(self) -> dict:
        with self._lock:
            birlesik = {"canvas_id": None, "tum_idler": [], "tum_classlar": []}
            for _, dom in self._dom_haritasi.items():
                if dom.get("canvas_id") and not birlesik["canvas_id"]:
                    birlesik["canvas_id"] = dom["canvas_id"]
                birlesik["tum_idler"].extend(dom.get("tum_idler", []))
                birlesik["tum_classlar"].extend(dom.get("tum_classlar", []))
            birlesik["tum_idler"] = list(set(birlesik["tum_idler"]))
            birlesik["tum_classlar"] = list(set(birlesik["tum_classlar"]))
            return birlesik

    def set_intermediate(self, sender_id: str, key: str, value: Any):
        """Bir ajanın ara durum verisini blackboard'a yazar."""
        with self._lock:
            if sender_id not in self._intermediate_data:
                self._intermediate_data[sender_id] = {}
            self._intermediate_data[sender_id][key] = value

    def get_intermediate(self, sender_id: str, key: Optional[str] = None) -> Any:
        """Belirli bir ajanın ara durum verisini okur."""
        with self._lock:
            agent_data = self._intermediate_data.get(sender_id, {})
            if key is None:
                return agent_data
            return agent_data.get(key)

    def get_all_intermediates(self) -> Dict[str, Any]:
        """Tüm amelelerin paylaştığı ara verileri getirir."""
        with self._lock:
            return dict(self._intermediate_data)

    def set_artifact(self, filename: str, content: str):
        with self._lock:
            self._artifacts[filename] = content

    def get_artifact(self, filename: str) -> Optional[str]:
        with self._lock:
            return self._artifacts.get(filename)

    def get_all_artifacts(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._artifacts)

    def add_decision(self, agent_or_chef: str, action: str, details: str):
        with self._lock:
            self._decisions.append({
                "source": agent_or_chef,
                "action": action,
                "details": details,
                "timestamp": time.time()
            })

    def get_decisions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._decisions)

    def get_kaynak_baglami(self) -> str:
        """Kullanıcının yüklediği referans kaynak belgeleri ve görsel analizlerini döndürür."""
        with self._lock:
            return self._kaynak_baglami or ""

    def set_kaynak_baglami(self, baglam: str):
        """Referans kaynak bağlamını günceller."""
        with self._lock:
            self._kaynak_baglami = baglam

    def set_architecture_contract(self, contract: str):
        """Şef'in oluşturduğu küresel mimari sözleşmeyi kaydeder."""
        with self._lock:
            self._architecture_contract = contract

    def get_architecture_contract(self) -> str:
        """Tüm amelelerin uyması gereken mimari sözleşmeyi döndürür."""
        with self._lock:
            return self._architecture_contract or ""

    def register_task_step(self, adim_no: int, target_file: str):
        """Görev adımı ve dosya eşleşmesini kaydeder."""
        with self._lock:
            self._step_file_map[adim_no] = target_file

    def get_scoped_artifacts_for_task(
        self,
        dependencies: List[int],
        current_file: str,
        is_integrator: bool = False
    ) -> Dict[str, str]:
        """
        🌳 WORKTREE DAL İZOLASYON KURALI:
        Amele ajanı yalnızca kendi dalının beslendiği kökleri (bağımlı olduğu adımların artefaktlarını) görebilir.
        Birbiriyle kesişmeyen yabancı dalların kodlarına erişemez.
        Yalnızca ana entegratör (index.html, nihai rapor vb.) görevleri tüm artefaktlara erişebilir.
        """
        with self._lock:
            if is_integrator:
                return {k: v for k, v in self._artifacts.items() if k != current_file}

            if not dependencies:
                return {}

            izinli_dosyalar = {}
            for dep_step in dependencies:
                if isinstance(dep_step, str) and not dep_step.strip().isdigit():
                    dep_str = dep_step.strip()
                    if dep_str in self._artifacts and dep_str != current_file:
                        izinli_dosyalar[dep_str] = self._artifacts[dep_str]
                        continue
                    for art_k, art_v in self._artifacts.items():
                        if art_k != current_file and art_k.lower().endswith(dep_str.lower()):
                            izinli_dosyalar[art_k] = art_v
                            break
                    continue

                step_key = int(dep_step) if isinstance(dep_step, str) and dep_step.strip().isdigit() else dep_step
                dep_file = self._step_file_map.get(step_key)
                if dep_file and dep_file in self._artifacts and dep_file != current_file:
                    izinli_dosyalar[dep_file] = self._artifacts[dep_file]
                elif step_key in self._memory:
                    placeholder_name = f"Adim_{step_key}_Ciktisi"
                    izinli_dosyalar[placeholder_name] = self._memory[step_key]

            return izinli_dosyalar

    def record_token_usage(self, role: str, count: int):
        """Token tüketimini kaydeder."""
        with self._lock:
            if role in self._token_stats:
                self._token_stats[role] += count
            else:
                self._token_stats[role] = count
            self._token_stats["total"] += count

    def get_token_stats(self) -> Dict[str, int]:
        """Token harcama istatistiklerini döndürür."""
        with self._lock:
            return dict(self._token_stats)
