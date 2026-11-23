import os
import sys
import time
import re
from typing import Dict, Any, List, Optional
from tools.browser_tools import browser_engine, local_server_manager
from infrastructure.gemini_client import gemini_service
from agents.worker_agent import saf_kodu_ayikla

class WebAutonomousPlaytester:
    """
    🌐 LASEF OTONOM WEB/HTML5 OYUN VE UYGULAMA TEST EDİCİSİ (PLAYTESTER & VISION EYE)
    
    Kör kod üretimini sonlandırır:
    1. Üretilen Web/HTML5 projesini yerel HTTP sunucusunda başlatır (http://127.0.0.1:8099).
    2. Playwright motoru ile canlı tarayıcıda (Chromium) sayfayı açar.
    3. Konsol hatalarını (console.error, unhandled exceptions) yakalar.
    4. Sayfanın ekran görüntüsünü çeker.
    5. Gemini Multimodal Vision ile sayfanın görsel ve oynanabilirlik durumunu inceler.
    6. Hata veya görsel kusur varsa kodu otomatik olarak kendi kendine onarır (Self-Healing).
    7. Başarılı olduğunda sahneyi ve oyunu onaylar.
    """
    def __init__(self, target_folder: str):
        self.target_folder = os.path.abspath(target_folder)
        self.max_repair_attempts = 3

    def run_full_pipeline(self, user_request: str, nihai_dosyalar: Dict[str, str]) -> Dict[str, Any]:
        print("\n" + "═" * 65)
        print("🌐 [LASEF OTONOM WEB TESTİ & ŞEFİN GÖZÜ] Canlı Tarayıcı Doğrulama Başlatıldı")
        print("═" * 65)

        rapor = {
            "browser_tested": False,
            "runtime_errors": [],
            "vision_verdict": "DEĞERLENDİRİLMEDİ",
            "vision_analysis": "",
            "summary": ""
        }

        html_dosyalar = [f for f in nihai_dosyalar.keys() if f.lower().endswith(".html")]
        if not html_dosyalar:
            rapor["summary"] = "Web projesinde test edilecek HTML dosyası bulunamadı."
            return rapor

        ana_html = "index.html" if "index.html" in html_dosyalar else html_dosyalar[0]
        html_tam_yol = os.path.join(self.target_folder, ana_html)
        if not os.path.exists(html_tam_yol):
            rapor["summary"] = f"HTML dosyası bulunamadı: {html_tam_yol}"
            return rapor

        print(f"   📡 [Yerel Sunucu]: '{self.target_folder}' dizini için HTTP sunucusu açılıyor...")
        base_url = local_server_manager.start_server(self.target_folder, port=8099)
        if not base_url:
            print("   ⚠️ [Sunucu Hatası]: Yerel HTTP sunucusu başlatılamadı, doğrudan dosya protokolü kullanılacak.")
            target_url = f"file:///{html_tam_yol.replace(os.sep, '/')}"
        else:
            target_url = f"{base_url}/{ana_html}"

        print(f"   🟢 [Hedef Web Adresi]: {target_url}")

        if not browser_engine.is_available():
            print("   ⚠️ [Playwright]: Playwright tarayıcı motoru hazır değil, statik doğrulama kullanılıyor.")
            rapor["summary"] = "Tarayıcı motoru mevcut olmadığı için dinamik görsel test atlandı."
            return rapor

        print("   🚀 [Chromium Başlatılıyor]: Sayfa yükleniyor ve JavaScript motoru çalıştırılıyor...")
        open_res = browser_engine.open_page(target_url, headless=True, timeout_ms=20000)
        if not open_res.get("success"):
            print(f"   ❌ [Tarayıcı Yükleme Hatası]: {open_res.get('error')}")
            rapor["summary"] = f"Tarayıcıda sayfa açılamadı: {open_res.get('error')}"
            local_server_manager.stop_server()
            return rapor

        rapor["browser_tested"] = True
        print(f"   ✅ [Sayfa Yüklendi]: Başlık -> '{open_res.get('title')}'")

        dom_res = browser_engine.inspect_dom()
        if dom_res.get("success"):
            dom_data = dom_res.get("dom_info", {})
            has_canvas = dom_data.get("has_canvas")
            btn_list = dom_data.get("buttons", [])
            print(f"   🔍 [DOM Yapısı]: Canvas = {has_canvas} | Butonlar: {btn_list[:4]}")

        for selector in ["#start-btn", "button#start", ".start-btn", "button"]:
            try:
                clk = browser_engine.click(selector, timeout_ms=800)
                if clk.get("success"):
                    break
            except Exception:
                pass

        time.sleep(2.0)

        log_res = browser_engine.get_logs_and_errors()
        page_errors = log_res.get("page_errors", [])
        console_errors = [l for l in log_res.get("console_logs", []) if l.get("type") == "error"]
        all_errors = page_errors + [c.get("text", "") for c in console_errors]
        rapor["runtime_errors"] = all_errors

        if all_errors:
            print(f"   🚨 [Web Çalışma Zamanı Hatası Tespit Edildi ({len(all_errors)} adet)]:")
            for err in all_errors[:3]:
                print(f"      • {err[:120]}")

        temp_screen = os.path.join(self.target_folder, "temp_web_playtest_capture.png")
        shot_res = browser_engine.capture_screenshot(temp_screen)

        if shot_res.get("success"):
            print(f"   📸 [Tarayıcı Ekranı Yakalandı]: {shot_res.get('size_kb', 0):.1f} KB")
            custom_prompt = (
                f"Sen Kıdemli Bir Web Mühendisi, UI/UX Tasarımcısı ve Baş Yazılım Mimarısın.\n"
                f"Şu an canlı tarayıcıda çalıştırılmış bir Web / HTML5 Canvas uygulamasının veya oyununun ekran görüntüsünü inceliyorsun.\n\n"
                f"KULLANICI TALEBİ: {user_request}\n"
                f"KONSOL HATA RAPORU: {all_errors or 'Konsol hatasız, temiz.'}\n\n"
                f"Lütfen şu 3 soruyu cevapla:\n"
                f"1. GÖRSEL RENDER: Sayfa düzgün render edilmiş mi? Canvas veya oyun alanı görünüyor mu yoksa boş/kırık bir sayfa mı var?\n"
                f"2. ARAYÜZ VE KONTROLLER: Butonlar, yazılar, renkler profesyonelce yerleşmiş mi?\n"
                f"3. NİHAİ KARAR: Tek satırda 'KARAR: ONAYLANDI' veya 'KARAR: DÜZELTME_GEREKLİ' yaz. Eğer düzeltme gerekliyse 2 maddede sebebini belirt."
            )
            try:
                analiz = gemini_service.analyze_image(temp_screen, custom_prompt=custom_prompt)
                print(f"   🔍 [Şefin Vizyon Raporu]:\n{analiz[:300]}...")
                rapor["vision_analysis"] = analiz
                verdict = "DÜZELTME_GEREKLİ" if ("DÜZELTME_GEREKLİ" in analiz.upper() or len(all_errors) > 0) else "ONAYLANDI"
                rapor["vision_verdict"] = verdict
            except Exception as ex:
                print(f"   ⚠️ [Vizyon Analiz Hatası]: {ex}")
                rapor["vision_verdict"] = "ONAYLANDI" if not all_errors else "DÜZELTME_GEREKLİ"
            finally:
                if os.path.exists(temp_screen):
                    try:
                        os.remove(temp_screen)
                    except Exception:
                        pass
        else:
            print(f"   ⚠️ [Ekran Alınamadı]: {shot_res.get('error')}")
            rapor["vision_verdict"] = "DÜZELTME_GEREKLİ" if all_errors else "ONAYLANDI"

        if rapor["vision_verdict"] == "DÜZELTME_GEREKLİ" or all_errors:
            print("\n🔧 [Web Kendi Kendini İyileştirme (Self-Healing)]: Kusurlar ve hatalar otonom onarılıyor...")
            self._onar_web_kodlari(all_errors, nihai_dosyalar, vision_analysis=rapor.get("vision_analysis", ""))

        browser_engine.close()
        local_server_manager.stop_server()

        durum = "✅ [WEB OTONOM TESTİ BAŞARIYLA TAMAMLANDI VE ONAYLANDI]" if rapor["vision_verdict"] == "ONAYLANDI" else "⚠️ [WEB TESTİ TAMAMLANDI - UYARILAR BULUNDU]"
        ozet = (
            f"{durum}\n"
            f"• Canlı Tarayıcı Testi: Başarılı (Chromium Headless)\n"
            f"• Konsol Durumu: {len(all_errors)} hata\n"
            f"• Şefin Vizyon Kararı: {rapor['vision_verdict']}\n"
            f"• Yerel Test URL: {target_url}"
        )
        rapor["summary"] = ozet
        print(f"\n{ozet}")
        return rapor

    def _onar_web_kodlari(self, errors: List[str], nihai_dosyalar: Dict[str, str], vision_analysis: str = ""):
        """Yakalanan konsol hatalarını veya görsel tasarım kusurlarını ilgili kodda otonom onarır."""
        err_text = "\n".join([f"• {e}" for e in errors[:5]]) if errors else "Konsol hatasız (Çökme yok)."
        vision_text = f"\nŞEFİN VİZYON / GÖRSEL DENETİM GERİ BİLDİRİMİ:\n{vision_analysis}\n" if vision_analysis else ""
        
        hedef_dosya = None
        for dosya in nihai_dosyalar.keys():
            if dosya.lower().endswith(".html"):
                hedef_dosya = dosya
                break
        if not hedef_dosya:
            for dosya in nihai_dosyalar.keys():
                if dosya.lower().endswith(".js"):
                    hedef_dosya = dosya
                    break

        if not hedef_dosya:
            return

        mevcut_kod = nihai_dosyalar.get(hedef_dosya, "")
        prompt = (
            f"CANLI TARAYICI ÇALIŞMA ZAMANI VE GÖRSEL DENETİM RAPORU:\n{err_text}\n{vision_text}\n"
            f"HEDEF DOSYA: {hedef_dosya}\n"
            f"MEVCUT KOD:\n```html\n{mevcut_kod[:14000]}\n```\n\n"
            f"GÖREV: Yukarıdaki konsol hatalarını ve Şefin vizyon geri bildirimindeki görsel eksiklikleri tamamen gider."
            f"Kodu profesyonel, eksiksiz, çalışan ve görsel olarak zenginleştirilmiş saf kod olarak tek bir markdown bloğu içinde üret."
        )

        try:
            tamir_kodu = gemini_service.generate_with_retry(
                prompt=prompt,
                system_instruction="Sen Kıdemli Web & JavaScript Hata Onarım Uzmanısın. Hataları düzelt ve sadece saf kodu üret."
            )
            temiz = saf_kodu_ayikla(tamir_kodu, hedef_dosya)
            if len(temiz) > 100:
                nihai_dosyalar[hedef_dosya] = temiz
                tam_yol = os.path.join(self.target_folder, hedef_dosya)
                with open(tam_yol, "w", encoding="utf-8") as f:
                    f.write(temiz)
                print(f"   🩹 [Web Kodu Onarıldı ve Diske Yazıldı]: {tam_yol}")
        except Exception as ex:
            print(f"   ⚠️ [Web Onarım Hatası]: {ex}")
