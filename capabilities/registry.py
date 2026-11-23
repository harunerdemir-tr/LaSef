import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

@dataclass
class CapabilityDefinition:
    name: str
    description: str
    system_prompt_template: str
    model_tags: List[str] = field(default_factory=list)
    file_extensions: List[str] = field(default_factory=list)
    recommended_tools: List[str] = field(default_factory=list)

class CapabilityRegistry:
    """
    Genişletilebilir Uzmanlık / Yetenek Kayıt Defteri (Capability Registry).
    Yeni uzmanlıklar (game-dev, report-writing, video-generation, qa-audit vb.)
    kolayca eklenebilir veya 'skills/' dizininden otomatik keşfedilebilir.
    """
    def __init__(self):
        self._capabilities: Dict[str, CapabilityDefinition] = {}
        self._load_builtins()
        self._discover_from_skills_dir()

    def register(self, cap: CapabilityDefinition):
        self._capabilities[cap.name.lower()] = cap

    def get(self, name: str) -> CapabilityDefinition:
        name_clean = name.lower().strip()
        if name_clean in self._capabilities:
            return self._capabilities[name_clean]
        
        for k, cap in self._capabilities.items():
            if k in name_clean or name_clean in k:
                return cap
        return self._capabilities.get("general", self._default_general_capability())

    def list_all(self) -> List[CapabilityDefinition]:
        return list(self._capabilities.values())

    def _default_general_capability(self) -> CapabilityDefinition:
        return CapabilityDefinition(
            name="general",
            description="Genel yazılım mühendisliği ve teknik üretim uzmanı",
            system_prompt_template="Sen dünya standartlarında bir Kıdemli Uzmansın. Sana verilen görevi eksiksiz, çalışan ve derinlemesine saf çıktılarla üret.",
            model_tags=["general", "coder"]
        )

    def _load_builtins(self):
        self.register(CapabilityDefinition(
            name="game-dev",
            description="2D/3D Oyun motorları, mekanikler, Unity, C#, HTML5 Canvas oyunları",
            system_prompt_template="""Sen dünya çapında bir Oyun Geliştiricisi ve Oyun Motoru Mimarı uzmanısın.
SADECE istenen oyun mekaniklerini, kontrollerini, render ve oyun döngüsü kodlarını eksiksiz üret.
Unity projelerinde canlı araçları kullanarak sahneye doğrudan nesne ekle, bileşenleri bağla ve derlemeyi doğrula.
Fonksiyon gövdelerini asla boş bırakma; tam çalışan saf kaynak kod üret.""",
            model_tags=["coder", "super", "nemotron"],
            file_extensions=[".cs", ".js", ".py", ".cpp", ".html"],
            recommended_tools=[
                "unity_get_hierarchy",
                "unity_create_object",
                "unity_add_component",
                "unity_set_property",
                "unity_create_prefab",
                "unity_wait_compile",
                "unity_get_logs",
                "unity_execute_csharp"
            ]
        ))

        self.register(CapabilityDefinition(
            name="unity-dev",
            description="Canlı Unity Editor Entegrasyonu, C# Scripting, Sahne İnşası ve Prefab Yönetimi",
            system_prompt_template="""Sen Unity Oyun Motoru konusunda uzmanlaşmış OTONOM BİR OYUN GELİŞTİRİCİSİSİN.
Canlı Unity Köprüsü üzerinden sahneyi gör, objeleri oluştur, C# scriptlerini tak ve hataları canlı denetle.""",
            model_tags=["coder", "super", "nemotron"],
            file_extensions=[".cs"],
            recommended_tools=[
                "unity_get_hierarchy",
                "unity_create_object",
                "unity_add_component",
                "unity_set_property",
                "unity_create_prefab",
                "unity_wait_compile",
                "unity_get_logs",
                "unity_execute_csharp"
            ]
        ))

        self.register(CapabilityDefinition(
            name="blender-3d",
            description="Blender 4.x/5.x Procedural 3D, bpy Python, Materyal/Işık ve Canlı/Headless MCP Entegrasyonu",
            system_prompt_template="""Sen Blender Technical Artist ve Python (bpy 4.x/5.x) otomasyon uzmanısın.
Blender 5 uyumlu Principled BSDF soket adlarını ('Specular IOR Level', 'Coat Weight'), context-safe bpy.data/bmesh API'sini kullan ve sahneyi kamera/ışık dahil eksiksiz kur.""",
            model_tags=["coder", "reasoning", "nemotron"],
            file_extensions=[".py"],
            recommended_tools=[
                "blender_ping",
                "blender_get_scene",
                "blender_execute_python",
                "blender_run_script_headless"
            ]
        ))

        self.register(CapabilityDefinition(
            name="report-writing",
            description="Teknik raporlama, mimari doküman, analiz ve kullanıcı kılavuzları",
            system_prompt_template="""Sen kıdemli bir Teknik Rapor Yazarı ve Sistem Dokümantasyon Uzmanısın.
Projeyi, mimari kararları, bileşenleri, veri akışını ve kurulum yönergelerini detaylı, profesyonel markdown formatında raporla.
Diğer amele ajanların ürettiği ara verileri ve kodları analiz ederek rapora entegre et.""",
            model_tags=["instruct", "llama", "nemotron"],
            file_extensions=[".md", ".txt", ".json"]
        ))

        self.register(CapabilityDefinition(
            name="qa-audit",
            description="Kod kalitesi, sözdizimi, güvenlik açıkları ve mantık hataları denetimi",
            system_prompt_template="""Sen bağımsız bir Baş Kalite Güvence (QA) ve Güvenlik Denetçisisin.
Üretilen kodları; güvenlik, sözdizim doğruluğu, edge-case senaryoları ve standartlara uygunluk açısından satır satır denetle.
Eksik veya hatalı yerleri tespit edip net düzeltmeler sun.""",
            model_tags=["super", "llama", "vision"],
            file_extensions=[".py", ".cs", ".js", ".html"]
        ))

        self.register(CapabilityDefinition(
            name="image-generation",
            description="NVIDIA NIM / Yerel Sentezleyici ile gerçek binary (.png/.jpg) oyun karakteri, arkaplan ve varlık görselleri üretimi",
            system_prompt_template="""Sen bir Görsel Tasarımcı ve Konsept Sanatçısısın. İstenen varlığın görsel tanımını çıkarıp MediaClient ile gerçek binary .png/.jpg dosyası olarak kaydet.""",
            model_tags=["vision", "media"],
            file_extensions=[".png", ".jpg", ".jpeg", ".webp"]
        ))

        self.register(CapabilityDefinition(
            name="video-generation",
            description="NVIDIA NIM / Çoklu Kare Sentezleyici ile gerçek binary (.mp4) oynatılabilir video ve animasyon üretimi",
            system_prompt_template="""Sen bir Video Prodüksiyon Yönetmeni ve Animasyon Sanatçısısın. İstenen sahneyi MediaClient ile gerçek binary .mp4 video dosyası olarak kaydet.""",
            model_tags=["video", "media"],
            file_extensions=[".mp4", ".gif"]
        ))

        self.register(CapabilityDefinition(
            name="web-fullstack",
            description="Modern Web arayüzleri, HTML5, CSS3, JavaScript, React ve API servisleri",
            system_prompt_template="""Sen kıdemli bir Fullstack Web Mühendisisin.
Modern, duyarlı, hatasız ve etkileşimli Web bileşenleri ve API servisleri üret.
Tüm CSS ve JS seçicilerinin HTML ID'leriyle %100 uyumlu olmasını sağla.""",
            model_tags=["coder", "diffusiongemma", "nemotron"],
            file_extensions=[".html", ".css", ".js", ".ts", ".py"]
        ))

        self.register(CapabilityDefinition(
            name="embedded-c",
            description="Gömülü C/C++, mikrodenetleyiciler, sensör sürücüleri ve donanım kontrolü",
            system_prompt_template="""Sen kıdemli bir Gömülü Sistemler ve Firmware Mühendisisin.
Donanım kayıtları, sensör haberleşmesi (I2C, SPI, UART) ve düşük seviyeli optimize C/C++ kodları üret.""",
            model_tags=["coder", "super"],
            file_extensions=[".c", ".h", ".cpp"]
        ))

        self.register(self._default_general_capability())

    def _discover_from_skills_dir(self):
        """Mevcut skills/ dizinindeki SKILL.md dosyalarını otomatik olarak birer capability olarak kaydeder."""
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        skills_yolu = os.path.join(kok, "skills")
        if not os.path.exists(skills_yolu):
            return

        try:
            for item in os.listdir(skills_yolu):
                alt = os.path.join(skills_yolu, item)
                if os.path.isdir(alt):
                    skill_md = os.path.join(alt, "SKILL.md")
                    if os.path.exists(skill_md):
                        with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read(3000)
                        cap_name = item.replace("_", "-").lower()
                        if cap_name not in self._capabilities:
                            self.register(CapabilityDefinition(
                                name=cap_name,
                                description=f"Özel Keşfedilen Beceri: {item}",
                                system_prompt_template=f"Sen bir {item} uzmanısın. Aşağıdaki kılavuza uygun saf kod üret:\n{content[:2000]}",
                                model_tags=["coder"]
                            ))
        except Exception:
            pass

capability_registry = CapabilityRegistry()
