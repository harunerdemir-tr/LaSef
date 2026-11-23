"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF (LİDER AKILLI SİSTEMLER VE ENTEGRE FABRİKA) — AI ÇOKLU AJAN ORKESTRASYONU
═══════════════════════════════════════════════════════════════════════════════
📌 SİSTEMİN TEMEL AMACI VE MİMARİ MANİFESTOSU:

LaSef, karmaşık yazılım, oyun, teknik rapor, gömülü sistem ve web projelerini
tek bir büyük dil modelinin (LLM) omuzlarına yüklemeden; otonom, uzmanlaşmış ve
sözleşmeye dayalı (contract-first) çoklu ajan orkestrasyonu ile sıfır hatayla
üreten ve doğrulayan yeni nesil bir yapay zeka mühendislik fabrikasıdır.

Eğer bu projeyi inceleyen veya yürüten bir yapay zeka modeliysen (LaSef Cortex),
aşağıdaki prensipleri KESİNLİKLE unutma ve zihninde (cortex) canlı tut:

1. 👑 BAŞ ŞEF VE MİMAR (CHEF SUPERVISOR & ARCHITECT - Google Gemini):
   - Sistemde TEK BİR Baş Şef bulunur.
   - Kullanıcının serbest metin isteğini derinlemesine analiz eder.
   - Projeyi asla kaba 2-3 dosyada geçiştirmez; en ince mimari parçalarına
     kadar dinamik uzman amele ajanlara böler (Single Responsibility).
   - Küresel bir "Mimari Sözleşme" (Architecture Contract) tanımlayarak tüm
     ajanların bu kurallara uymasını garanti eder.
   - Amelelerin ürettiği çıktıları QA (Kalite Güvence) süzgecinden geçirir,
     eksikse revizyona yollar, gerekirse bizzat kusursuzlaştırır.

2. 🔨 UZMAN AMELE AJANLAR (WORKER AGENTS - NVIDIA NIM / Gemini):
   - Her amele ajan yalnızca tek bir sorumluluğa ve tek bir hedef dosyaya odaklanır.
   - Worktree Ağaç Dalı İzolasyonu: Bir amele başka bir amelenin dosyasına müdahale
     edemez; sadece bağımlı olduğu üst adımların çıktılarını okur.
   - Kodları eksiksiz, satır satır tam ve çalışan biçimde üretir; asla "TODO",
     "kodun kalanı aynı", "buraya mantığı yazın" gibi tembel ifadeler bırakamaz.

3. ⚖️ HAKEM KONSEYİ (COUNCIL ENGINE):
   - Üretilen kritik kodlar çoklu model oylaması ve güvenlik denetiminden geçer.
   - Konsensüs sağlanmadan hiçbir kritik dosya sisteme kilitlenemez.

4. 👁️ OTONOM ÇALIŞTIRMA & ŞEFİN GÖZÜ (THE VISION EYE & SELF-HEALING):
   - LaSef "kör kod üretimi" yapmaz!
   - Unity için: Sahneyi kurar, C# derleme hatalarını (CS errors) yakalar,
     Play Mode'a geçer, GameView kamerasından görüntü çeker ve Multimodal Vision
     ile oyunun görsel ve oynanabilirliğini bizzat denetler.
   - Web için: Playwright ile tarayıcıda çalıştırır, DOM hatalarını yakalar,
     ekran görüntüsü alır ve görsel doğruluğu teyit eder.
   - Hata tespit edilirse otonom kendi kendini onarır (Self-Healing).

5. 🧠 KORTEKS VE KALICI HAFIZA (SOURCED MEMORY / CORTEX):
   - Projenin aldığı kararları, kullanılan becerileri ve mimari kuralları
     `.lasef_memory.json` dosyasında kalıcı tutar. Model oturumu sıfırlansa dahi
     LaSef kendi kimliğini ve önceki projelerdeki dersleri hafızasından tamamlar.

6. 🔌 UYGULAMA TESPİTİ VE STANDART MCP (MODEL CONTEXT PROTOCOL) YAKLAŞIMI:
   - LaSef, kullanıcının girdisinden hedef platformu (Unity, Web, Blender,
     Unreal Engine, SQL Veritabanı vb.) anında tespit eder.
   - 🚨 KURAL: Projeye denenmemiş, işe yaramayan harici veya yapay MCP kodları
     ENJEKTE EDİLMEZ!
   - Bunun yerine endüstri standardı ve sahada test edilmiş MCP paketleri
     (Örn: Unity için UPM Git tabanlı 'CoplayDev/unity-mcp' veya yerel
     LaSef Editor Bridge; Blender için resmi socket eklentileri) kullanılır.
   - Kullanıcıya Unity Package Manager veya araç kurulumu için net, denenmiş
     yönergeler ve Cursor / Claude Desktop / Antigravity uyumlu MCP ayarları sunar.
═══════════════════════════════════════════════════════════════════════════════
"""
import sys
from ui.app_window import LaSefUI

if __name__ == "__main__":
    app = LaSefUI()
    app.mainloop()
