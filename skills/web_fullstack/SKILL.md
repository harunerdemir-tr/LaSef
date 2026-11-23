# 🌐 SKILL: Modern Web Fullstack & 60 FPS HTML5 Canvas Game Architecture

## 📌 Kesin Mimari Standartlar (Tüm Ajanlar İçin Zorunludur)

### 1. 🚨 SIFIR BAĞIMLILIK (Zero-Dependency) & ÇİFT ÇALIŞMA GARANTİSİ:
- Web projeleri hem yerel dosya sisteminden doğrudan çift tıklamayla (`file:///`) hem de bir HTTP sunucusu üzerinden (`http://localhost`) **sorunsuz ve hatasız** çalışmalıdır.
- CDN bağlantılarına bağımlı kalma; harici kütüphane yerine modern saf HTML5, CSS3 ve Vanilla ES6+ JavaScript kullan.
- Web Audio API ses sentetizörü (8-bit ses efektleri, müzik) dahili fonksiyonlarla saf JS içinden üretilmelidir. Harici `.mp3` dosya yükleme zorunluluğu getirme; sesleri Web Audio osilatörleri ile runtime'da sentezle.

### 2. 🎨 DUYARLI VE MODERN ARAYÜZ (Responsive Layout & Canvas):
- `canvas` boyutu pencereye veya kapsayıcıya göre akıllıca ölçeklenmeli (`resize` dinleyicisi ile DPI duyarlı ölçekleme).
- Sayfada etkileşimli alanlar, butonlar ve kontrol panelleri için `pointer-events: auto !important;` ve `cursor: pointer;` kuralları eksiksiz tanımlanmalıdır.
- Kullanıcı dostu HUD (Skor, Can barı, Dalga/Seviye sayacı, Duraklatma ve Yeniden Başlatma butonları) DOM veya Canvas üzerinde temizce çizilmelidir.

### 3. 🎮 60 FPS OYUN DÖNGÜSÜ (Game Loop & Delta Time):
- Sabit `setInterval` yerine mutlaka `requestAnimationFrame(loop)` kullanılmalıdır.
- Nesnelerin hızı ve fiziği `deltaTime` (zaman farkı) ile çarpılarak ekran yenileme hızından (60Hz, 144Hz) bağımsız pürüzsüz akıcılık sağlanmalıdır.
- Klavye ve dokunmatik (Touch/Virtual D-Pad) kontroller aynı anda desteklenmelidir.

### 4. 🔗 DOM ID & JS/CSS BÜTÜNLÜĞÜ:
- JS dosyalarında `getElementById` veya `querySelector` ile seçilen her ID, `index.html` içinde KESİNLİKLE birebir tanımlı olmalıdır.
- `index.html` modüler JS ve CSS dosyalarını hem `<script src="...">` ile bağlamalı hem de gerektiğinde tek dosya olarak çalışabilecek inline entegrasyona uygun olmalıdır.
