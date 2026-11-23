"""
═══════════════════════════════════════════════════════════════════════════════
🧠 LASEF KORTEKS VE KALICI HAFIZA SİSTEMİ (core/sourced_memory.py)
═══════════════════════════════════════════════════════════════════════════════
📌 LASEF KORTEKS MANİFESTOSU VE SİSTEMİN TEMEL AMACI:
Bu dosya, LaSef (Lider Akıllı Sistemler ve Entegre Fabrika) orkestrasyonunun
kalıcı zihnidir (Cortex). Model bağlamı (context window) temizlense, oturumlar
yenilense dahi sistem kim olduğunu, mimari prensiplerini ve geçmişte aldığı
kararları bu korteks üzerinden hatırlar.

👑 LASEF KİMDİR VE NASIL ÇALIŞIR?
1. ÇOKLU AJAN ORKESTRASYON FABRİKASI:
   LaSef, karmaşık yazılım, oyun (özellikle Unity ve Web), teknik rapor ve gömülü
   sistemleri sıfır hatayla üreten otonom bir AI mühendislik ekosistemidir.

2. BAŞ ŞEF (CHEF SUPERVISOR & ARCHITECT - Google Gemini):
   Tüm mimariyi kurgulayan, kullanıcının niyetini anlayan, projeyi bağımsız
   ve tek sorumluluklu (Single Responsibility) amele modüllerine bölen ve
   küresel "Mimari Sözleşme"yi (Architecture Contract) belirleyen ana beyindir.

3. UZMAN AMELE AJANLAR (WORKER AGENTS - NVIDIA NIM / Gemini):
   Her biri tek bir hedefe kilitlenmiş, worktree dal izolasyonuyla birbirinin
   alanına girmeden çalışan ve tam kod üreten uygulayıcılardır.

4. HAKEM KONSEYİ (COUNCIL ENGINE):
   Kritik kodları çoklu LLM oylaması ve güvenlik denetimiyle süzen kuruldur.

5. ŞEFİN GÖZÜ VE OTONOM ONARIM (THE VISION EYE & SELF-HEALING):
   Kör kod üretimini reddeder! Unity veya Web arayüzlerinde oyunu bizzat başlatır,
   ekran görüntüsü (multimodal vision) alır, derleme hatalarını canlı okur ve
   onarım döngüsüyle kusursuzlaştırır.

6. STANDART MCP VE UYGULAMA TESPİT PRENSİBİ:
   Kullanıcının girdisinden hedef uygulamayı (Unity, Web, Blender vb.) anlar.
   Projeye ASLA denenmemiş, işe yaramayan yapay MCP kodları ENJEKTE ETMEZ!
   Bunun yerine endüstri standardı UPM paketleri (CoplayDev/unity-mcp gibi)
   veya LaSef'in yerleşik çalışan köprülerini (LaSefBridgeServer.cs) önerir.
═══════════════════════════════════════════════════════════════════════════════
"""
import os
import json
import time
from typing import Dict, Any, List, Optional
from core.mcp_router import detect_application_profile, MCP_CATALOG

LASEF_PERMANENT_MANIFESTO = """👑 [LASEF KORTEKS HAFIZASI & MİMARİ KİMLİK]:
- Kimlik: LaSef Otonom Çoklu Ajan AI Mühendislik Orkestrası.
- Şef (Gemini): Mimari tasarım, dekompozisyon, mimari sözleşme ve QA onayı.
- Ameleler (NIM/Gemini): Tek sorumluluklu, eksiksiz saf kod üreten uzman işçiler.
- Şefin Gözü (Vision Eye): Canlı oyun/web çalıştırma, görüntü analizi ve self-healing.
- MCP İlkesi: Denenmemiş harici MCP kodu yazılmaz; resmi/UPM paketleri (örn. CoplayDev/unity-mcp) ve yerleşik köprüler kullanılır."""

class SourcedMemory:
    """
    🧠 Proje Kalıcı Hafızası (Vectorless Sourced Memory & Cortex):
    Projeyle ilgili alınan mimari kararları, tercihleri, aktif becerileri ve
    uygulama MCP gereksinimlerini hatırlar.
    """
    def __init__(self, workspace_path: str = ""):
        self.workspace_path = workspace_path or "."
        self.memory_file = os.path.join(self.workspace_path, ".lasef_memory.json")
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "manifesto" not in data:
                        data["manifesto"] = LASEF_PERMANENT_MANIFESTO
                    return data
            except Exception:
                pass
        return {
            "system_name": "LaSef Multi-Agent Orchestrator",
            "manifesto": LASEF_PERMANENT_MANIFESTO,
            "decisions": [],
            "skills_used": [],
            "project_type": None,
            "detected_applications": [],
            "last_updated": time.time()
        }

    def remember_decision(self, decision: str, category: str = "general"):
        """Mimari bir kararı veya başarıyla tamamlanan görevi hafızaya kaydeder."""
        if "decisions" not in self._data:
            self._data["decisions"] = []
        self._data["decisions"].append({
            "category": category,
            "decision": decision,
            "timestamp": time.time()
        })
        self._data["last_updated"] = time.time()
        self._save()

    def remember_application_target(self, app_key: str):
        """Projenin hedeflediği uygulamayı (unity, web, blender vb.) hafızaya ekler."""
        if "detected_applications" not in self._data:
            self._data["detected_applications"] = []
        if app_key not in self._data["detected_applications"]:
            self._data["detected_applications"].append(app_key)
            self._save()

    def get_core_manifesto(self) -> str:
        """LaSef'in temel amacını ve çalışma ilkelerini döner."""
        return self._data.get("manifesto", LASEF_PERMANENT_MANIFESTO)

    def get_summary(self) -> str:
        """
        LLM modellerine prompt başında enjekte edilecek özet hafıza metni.
        Model LaSef'in kim olduğunu ve önceki kararları bu özet üzerinden anlar.
        """
        ozet = [
            LASEF_PERMANENT_MANIFESTO,
            "\n📌 [ÇALIŞMA ALANI GEÇMİŞİ VE ALINAN KARARLAR]:"
        ]

        apps = self._data.get("detected_applications", [])
        if apps:
            ozet.append(f"- Aktif Hedef Uygulamalar: {', '.join(apps).upper()}")

        decisions = self._data.get("decisions", [])
        if decisions:
            for d in decisions[-5:]:
                ozet.append(f"- ({d.get('category', 'genel')}) {d.get('decision')}")
        else:
            ozet.append("- Henüz kayıtlı önceki karar bulunmuyor (Yeni Oturum).")

        return "\n".join(ozet)

    def _save(self):
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
