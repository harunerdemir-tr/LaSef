# 📱 SKILL: Mobile Flutter & Dart Cross-Platform Architecture

## 📌 Kesin Mimari Standartlar (Tüm Ajanlar İçin Zorunludur)

### 1. 🏗️ TEMİZ MİMARİ & DURUM YÖNETİMİ (Clean Architecture & State Management):
- UI katmanını iş mantığından (Business Logic) kesin olarak ayır.
- Basit uygulamalar için `ChangeNotifier` / `ValueNotifier` veya modern `Riverpod` / `Bloc` paternlerine uygun durum yöneticileri kur.
- `setState()` kullanımını sadece yerel, küçük UI animasyon durumlarıyla sınırla; global veri akışını merkezi sağlayıcılarla (Providers/Services) yönet.

### 2. 🎨 DUYARLI VE ADAPTİF ARAYÜZ (Responsive UI):
- `MediaQuery`, `LayoutBuilder` veya `Flexible` / `Expanded` widget'ları ile hem dikey (portrait) hem yatay (landscape) hem de tablet ekranlarına tam uyum sağla.
- Taşma (Overflow) hatalarını önlemek için dikey içeriklerde mutlaka `SingleChildScrollView` veya `ListView` kullan.
- Dark ve Light tema desteğini `ThemeData` ve renk şemaları ile dinamik entegre et.

### 3. ⚡ ASENKRON İŞLEMLER VE HATA YÖNETİMİ:
- Tüm ağ, veritabanı veya dosya işlemlerinde `async`/`await` ve `try-catch` bloklarını eksiksiz kur.
- Kullanıcıya yüklenme durumlarını (`CircularProgressIndicator`, Shimmer) ve hata bildirimlerini (`SnackBar`, Dialog) zarifçe göster.
- Bellek sızıntılarını önlemek için `dispose()` metotlarında `TextEditingController`, `AnimationController` ve Stream aboneliklerini kapat.
