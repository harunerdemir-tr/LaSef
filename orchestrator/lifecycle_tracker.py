"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF BAŞ MİMAR CANLI DÖNGÜ VE ZAMAN ŞERİDİ YÖNETİCİSİ (lifecycle_tracker.py)
═══════════════════════════════════════════════════════════════════════════════
📌 AMACI:
Kullanıcı girdisine özel olarak orkestrasyonun yaşam döngüsü aşamalarını
dinamik kurgular ve yönetir.
Zaman şeridinde:
- ÖNCEKİ İŞ: Kesinlikle YALNIZCA 1 iş birimi önceki görev (2 birim öncesi asla yazılmaz).
- ŞU ANKİ İŞ: Aktif yürütülen döngü ve canlı detay.
- SONRAKİ İŞ: Sırada bekleyen iş birimi.
═══════════════════════════════════════════════════════════════════════════════
"""
import time
from typing import List, Dict, Any, Optional
from core.event_bus import event_bus, EVENT_TIMELINE_STAGE

class LifecycleStage:
    def __init__(self, title: str, default_note: str, icon: str = "⚡"):
        self.title = title
        self.default_note = default_note
        self.icon = icon

class LifecycleTracker:
    """
    Baş Mimar'ın dinamik iş döngüsü yöneticisi.
    Kullanıcının girdisine göre aşamaları dinamik revize eder ve EventBus ile UI'a aktarır.
    """
    def __init__(self):
        self.user_request: str = ""
        self.app_key: str = "general"
        self.stages: List[LifecycleStage] = []
        self.current_index: int = 0
        self.current_detail: str = ""
        self.is_active: bool = False

    def setup_lifecycle_for_request(self, user_request: str, app_key: str, plan_modulleri: Optional[List[Any]] = None):
        """
        Kullanıcı isteğine ve hedef uygulama ortamına göre
        özel yaşam döngüsü zaman şeridini baştan oluşturur.
        """
        self.user_request = user_request
        self.app_key = app_key
        self.current_index = 0
        self.is_active = True
        modul_sayisi = len(plan_modulleri) if plan_modulleri else 4

        if app_key == "unity":
            self.stages = [
                LifecycleStage("İstek Algılandı & Niyet Analizi", "Kullanıcı talebi çözümlendi (3D Unity Projesi)", "🎯"),
                LifecycleStage("Mimari Şartname & Sözleşme", "Zero-Setup ve SceneBuilder kanunları kilitlendi", "📜"),
                LifecycleStage("Amele İş Dağıtımı", f"{modul_sayisi} uzman amele paralel göreve atandı", "🚀"),
                LifecycleStage("Kod Üretimi & QA Konseyi", "C# sınıfları yazılıyor ve güvenlikten geçiyor", "🔍"),
                LifecycleStage("Unity MCP & Sahne Entegrasyonu", "Hiyerarşi taranıyor, objeler ve scriptler bağlanıyor", "🎮"),
                LifecycleStage("Şefin Gözü (Vision Eye)", "GameView ekran görüntüsü ve Play Mode doğrulanıyor", "👁️"),
                LifecycleStage("Proje Mühürlendi & Rapor", "Tüm Unity bileşenleri başarıyla tamamlandı", "✅")
            ]
        elif app_key == "web":
            self.stages = [
                LifecycleStage("İstek Algılandı & Niyet Analizi", "Modern Web Fullstack / Canvas oyunu çözümlendi", "🎯"),
                LifecycleStage("Mimari Şartname & DOM Planı", "HTML5 Canvas, CSS ve JS mimarisi kilitlendi", "📜"),
                LifecycleStage("Amele İş Dağıtımı", f"{modul_sayisi} uzman amele paralel göreve atandı", "🚀"),
                LifecycleStage("Kod Üretimi & DOM Uyumu", "ID ve seçici senkronizasyonu denetleniyor", "🔍"),
                LifecycleStage("Canlı Tarayıcı Testi", "Playwright ile tarayıcıda 60 FPS test ediliyor", "🌐"),
                LifecycleStage("Proje Mühürlendi & Rapor", "Web uygulaması oynanabilir şekilde teslim edildi", "✅")
            ]
        elif app_key == "blender":
            self.stages = [
                LifecycleStage("İstek Algılandı & Niyet Analizi", "Blender 3D modelleme / render talebi çözümlendi", "🎯"),
                LifecycleStage("Mimari Şartname & Sahne Planı", "Mesh, materyal ve render standartları kilitlendi", "📜"),
                LifecycleStage("Amele İş Dağıtımı", "Python bpy script üreticileri görevlendirildi", "🚀"),
                LifecycleStage("Blender MCP Entegrasyonu", "Port 9876 soket köprüsü üzerinden komutlar yürütülüyor", "🧊"),
                LifecycleStage("Render & Görsel Doğrulama", "Kamera çıktısı denetleniyor", "👁️"),
                LifecycleStage("Proje Mühürlendi", "3D varlıklar ve render başarıyla tamamlandı", "✅")
            ]
        else:
            self.stages = [
                LifecycleStage("İstek Algılandı & Niyet Analizi", "Kullanıcı talebi analiz edildi ve kapsam belirlendi", "🎯"),
                LifecycleStage("Mimari Şartname & Sözleşme", "Yazılım ve raporlama standartları kilitlendi", "📜"),
                LifecycleStage("Amele İş Dağıtımı", f"{modul_sayisi} uzman amele görevlendirildi", "🚀"),
                LifecycleStage("Üretim & Hakem Konseyi", "Modüller yazılıyor ve QA oylamasından geçiyor", "🔍"),
                LifecycleStage("Otonom Doğrulama & Test", "Sistem testleri ve sözdizimi doğrulanıyor", "⚡"),
                LifecycleStage("Proje Mühürlendi & Rapor", "Nihai artefaktlar üretildi ve arşivlendi", "✅")
            ]

        self.advance_to_stage(0, "Baş Mimar isteği inceledi ve mimari yol haritasını kilitledi.")

    def advance_to_stage(self, stage_index: int, detail: str = ""):
        """Belirli bir aşamaya ilerler ve EventBus ile UI'a yayınlar."""
        if not self.stages:
            return

        self.current_index = max(0, min(stage_index, len(self.stages) - 1))
        self.current_detail = detail or self.stages[self.current_index].default_note

        payload = self._build_payload()
        event_bus.publish(EVENT_TIMELINE_STAGE, "CHEF", payload)

        print(f"⏱️ [ZAMAN ŞERİDİ] {payload['prev_title']} ──► ⚡ [{payload['current_title']}] ──► {payload['next_title']}")
        if detail:
            print(f"   └ 💬 [Baş Mimar]: {detail}")

    def update_detail(self, detail: str):
        """Aktif aşamanın canlı açıklamasını revize eder."""
        if not self.stages:
            return
        self.current_detail = detail
        payload = self._build_payload()
        event_bus.publish(EVENT_TIMELINE_STAGE, "CHEF", payload)
        print(f"   └ 💬 [Baş Mimar]: {detail}")

    def _build_payload(self) -> Dict[str, Any]:
        cur = self.stages[self.current_index]

        if self.current_index > 0:
            prev_stage = self.stages[self.current_index - 1]
            prev_title = f"{prev_stage.icon} {prev_stage.title}"
            prev_note = prev_stage.default_note
        else:
            prev_title = "🏁 Başlangıç"
            prev_note = "Orkestra henüz ateşlendi"

        current_title = f"{cur.icon} {cur.title}"
        current_note = self.current_detail

        if self.current_index < len(self.stages) - 1:
            next_stage = self.stages[self.current_index + 1]
            next_title = f"{next_stage.icon} {next_stage.title}"
            next_note = next_stage.default_note
        else:
            next_title = "🏁 Mühürleme"
            next_note = "Süreç tamamlanmak üzere"

        progress = (self.current_index + 1) / len(self.stages)

        return {
            "current_index": self.current_index,
            "total_stages": len(self.stages),
            "progress_ratio": progress,
            "prev_title": prev_title,
            "prev_note": prev_note,
            "current_title": current_title,
            "current_note": current_note,
            "next_title": next_title,
            "next_note": next_note,
            "app_key": self.app_key
        }

lifecycle_tracker = LifecycleTracker()
