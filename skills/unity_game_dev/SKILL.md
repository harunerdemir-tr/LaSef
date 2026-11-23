# 🎮 SKILL: Unity 3D/2D Game Development & Live Editor ReAct Architecture

## 📌 Kesin Mimari Standartlar (Tüm Ajanlar İçin Zorunludur)

### 1. 🚨 TEK DOSYA = TEK PUBLIC CLASS (Unity Derleme Garantisi):
- Her `.cs` dosyasında YALNIZCA dosya adıyla birebir aynı isimde TEK BİR `public class` bulunacaktır!
- Asla bir dosyanın altına `PlayerController`, `GameManager`, `CameraController` gibi diğer sınıfları ekleme! Her sınıf kendi bağımsız `.cs` dosyasında olmalıdır.
- Dosya adı `PlayerController.cs` ise sınıf adı kesinlikle `public class PlayerController : MonoBehaviour` olmalıdır.

### 2. 🎮 İKİ KADEMELİ UNITY MİMARİSİ (Two-Tier Architecture):

#### Kademe A: Canlı Editör ve Araç Katmanı (Unity Bridge Canlı İken):
- **Canlı İnşa:** Sahneye nesne ekleme (`unity_create_object`), bileşen takma (`unity_add_component`), ve alanları bağlama (`unity_set_property`) işlemlerini doğrudan canlı Unity köprüsü üzerinden yap.
- **Prefab-First Yaklaşımı:** Karakter, düşman ve çevre modellerini `Assets/Prefabs/` altına kaydet (`unity_create_prefab`). Sahne çakışmalarını önlemek için prefab tabanlı çalış.
- **Canlı Derleme ve Hata Doğrulama:** Her `.cs` dosyası yazıldıktan veya değiştirildikten sonra `unity_wait_compile` ile Unity'nin derleme durumunu sorgula. Konsol hatalarını (`unity_get_logs`) kontrol et.
- **SerializedProperty Referansları:** Inspector'daki boş referansları `unity_set_property(..., is_reference=true)` ile bağla.

#### Kademe B: Sıfır Kurulum / Otonom Bootstrapper (Unity Çevrimdışı İken Yedek Yol):
- Eğer Unity Editor açık değilse veya köprüye erişilemiyorsa:
  - Projeye bir `GameBootstrapper.cs` ekle:
    ```csharp
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    public static void AutoBootstrap()
    {
        // Sahneyi kodla inşa et: Zemin, Player, Camera, GameManager
    }
    ```
  - Bu sayede kullanıcı Unity'yi daha sonra açıp sadece Play (▶) tuşuna bastığında oyun otomatik kurulur.

### 3. Fizik, Karakter ve Kontroller:
- Karakter hareketi için `CharacterController` ve `SimpleMove` / `Move` veya `Rigidbody` + `FixedUpdate` kullan.
- Çarpışma ve temas mekanikleri için `OnControllerColliderHit` veya `OnTriggerEnter` kullan.
- Tüm fonksiyonlar satır satır tam dolu ve derleme hatasız olmalıdır.
