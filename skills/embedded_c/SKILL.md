# ⚡ SKILL: Embedded C/C++ & Bare-Metal Firmware Engineering

## 📌 Kesin Mimari Standartlar (Tüm Ajanlar İçin Zorunludur)

### 1. 🛡️ GÜVENLİK, BELLEK VE TİP DİSİPLİNİ:
- Standart C99/C11 kurallarına uy; belirsiz temel tipler yerine mutlaka `<stdint.h>` (`uint8_t`, `int16_t`, `uint32_t`) ve `<stdbool.h>` kullan.
- Dinamik bellek tahsisinden (`malloc`, `free`) kaçın; tüm veri yapılarını derleme zamanında belirlenmiş statik tamponlar (static ring buffers, pool allocators) olarak tasarla.
- Donanım kayıtları (memory-mapped registers) ve kesme (interrupt) ile paylaşılan değişkenleri mutlaka `volatile` olarak tanımla.

### 2. 🔌 DONANIM SOYUTLAMA KATMANI (HAL & Driver Architecture):
- Kod yapısını 3 katmana ayır:
  1. **Donanım/MCU Katmanı:** Kayıtlar, GPIO, I2C, SPI, UART, Timer/PWM sürücüleri.
  2. **Cihaz/Sensör Katmanı:** Örneğin MPU6050, BMP280, SSD1306 OLED, Motor Driver mantığı.
  3. **Uygulama Mantığı:** Durum makineleri (Finite State Machines - FSM), PID kontrolcüleri ve görev yöneticisi.
- Sensör ve haberleşme sürücülerinde hata durumlarını kontrol et (`TIMEOUT`, `NACK`, `CRC_ERROR` kontrolü).

### 3. ⏱️ DETERMINİSTİK ZAMANLAMA & KESME (ISR) YÖNETİMİ:
- Kesme hizmet rutinleri (ISR) son derece kısa ve deterministik olmalıdır.
- ISR içinde uzun döngüler, engelleme yapan (blocking) `delay` fonksiyonları veya ağır hesaplamalar yapma; sadece bayrakları (`flags`) set et ve ana döngüde işle.
- Bloklayıcı `delay_ms` yerine `millis()` veya Hardware Timer tabanlı asenkron zamanlayıcılar kur.
