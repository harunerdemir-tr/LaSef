import os
import sys
import time
import random
from typing import Optional, List, Dict, Any
import logging
import warnings
from dotenv import load_dotenv
from google import genai
from google.genai import types

logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
warnings.filterwarnings("ignore", message=".*AFC.*")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

DEFAULT_GEMINI_CANDIDATES = [
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.6-flash",
    "gemini-3.5-flash"
]

class GeminiClient:
    """
    Dayanıklı ve Otonom Google Gemini API İstemcisi.
    - Model sağlık kontrolü (startup health check)
    - RPM (dakikalık rate-limit) ile RPD (günlük kota tükenmesi) ayrımı
    - Dakikalık 429 için geçici bekleme / soğuma penceresi (cooling window)
    - Günlük kota bittiğinde oturum boyunca kalıcı NIM Mimar devri (Surrogate Brain)
    - Şef'in mimari kimliği korunur; NIM sadece geçici/oturum boyu çıkarım motoru görevi görür.
    """
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.configured_model = default_model or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
        self.active_model = self.configured_model
        self.client: Optional[genai.Client] = None
        self._is_healthy = False
        
        self._daily_quota_exhausted = False
        self._cooldown_until: float = 0.0
        self._consecutive_rate_limits = 0
        self._model_cooldowns: Dict[str, float] = {}
        self._dead_models: set = set()

        if self.api_key:
            try:
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(
                        timeout=90000,
                        retry_options=types.HttpRetryOptions(attempts=1)
                    )
                )
            except Exception as e:
                print(f"[GeminiClient] İstemci başlatılamadı: {e}")

    def health_check(self, candidates: Optional[List[str]] = None) -> bool:
        """
        Başlangıçta modelin kullanılabilirliğini kontrol eder.
        Eğer yapılandırılan model 404/kullanım dışı ise otomatik olarak ilk çalışan adaya geçer.
        """
        if not self.client:
            print("❌ [Gemini Sağlık Uyarısı]: API Anahtarı bulunamadı.")
            self._is_healthy = False
            return False

        model_list = [self.configured_model] + [m for m in (candidates or DEFAULT_GEMINI_CANDIDATES) if m != self.configured_model]
        
        print(f"🔍 [Gemini Sağlık Kontrolü]: Model testi yapılıyor (Öncelikli: '{self.configured_model}')...")
        for model_name in model_list:
            try:
                res = self.client.models.generate_content(
                    model=model_name,
                    contents="ping"
                )
                if res and res.text:
                    self.active_model = model_name
                    self._is_healthy = True
                    print(f"   └ 🟢 [Gemini Aktif]: '{model_name}' başarıyla doğrulandı ve kilitlendi.")
                    return True
            except Exception as e:
                err_str = str(e)
                if "404" in err_str or "NOT_FOUND" in err_str or "no longer available" in err_str:
                    print(f"   └ ⚠️ [Gemini Uyarısı]: '{model_name}' kullanım dışı / bulunamadı. Sonraki model deneniyor...")
                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"   └ ⚠️ [Gemini Sağlık Uyarısı]: '{model_name}' şu an kotalı/meşgul (429).")
                    self._handle_rate_limit_error(err_str)
                else:
                    print(f"   └ ⚠️ [Gemini Test Hatası]: '{model_name}' -> {err_str[:90]}")
                continue

        print("⚠️ [Gemini Sağlık Notu]: Gemini adayı doğrudan yanıt vermedi. Şef görevleri NIM Mimar motoruna devredilebilir.")
        self._is_healthy = False
        return False

    def analyze_images_grid(self, image_paths: list, tile_size: int = 128, cols: int = 8) -> dict:
        """
        🧩 Toplu Küçük Görsel / İkon Grid Kolajı Analizi (PIL Contact Sheet).
        Maksimum (cols x cols) adet görseli numaralı tek bir ızgara görselinde birleştirerek
        tek Gemini Vision API çağrısı ile her öğe için 1 cümlelik teknik özet çıkarır.
        """
        if not image_paths or not self.client:
            return {}

        import re
        import tempfile
        from PIL import Image, ImageDraw, ImageFont

        valid_paths = [p for p in image_paths if p and os.path.exists(p)]
        if not valid_paths:
            return {}

        cols = max(2, int(cols))
        batch_size = cols * cols
        label_h = 22
        cell_h = tile_size + label_h
        results = {}
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
        font = ImageFont.load_default()

        for start in range(0, len(valid_paths), batch_size):
            chunk = valid_paths[start:start + batch_size]
            n = len(chunk)
            rows = (n + cols - 1) // cols
            sheet = Image.new("RGB", (cols * tile_size, rows * cell_h), (36, 38, 44))
            draw = ImageDraw.Draw(sheet)

            tile_manifest = []
            for idx, img_path in enumerate(chunk, 1):
                r = (idx - 1) // cols
                c = (idx - 1) % cols
                x0 = c * tile_size
                y0 = r * cell_h

                draw.rectangle([x0 + 1, y0 + 1, x0 + tile_size - 2, y0 + tile_size - 2], fill=(54, 58, 66), outline=(85, 92, 105))
                try:
                    with Image.open(img_path) as raw_im:
                        rgba = raw_im.convert("RGBA")
                        bg = Image.new("RGBA", rgba.size, (54, 58, 66, 255))
                        comp = Image.alpha_composite(bg, rgba).convert("RGB")
                        comp.thumbnail((tile_size - 8, tile_size - 8), resampling)
                        tw, th = comp.size
                        sheet.paste(comp, (x0 + (tile_size - tw) // 2, y0 + (tile_size - th) // 2))
                except Exception:
                    draw.line([x0 + 4, y0 + 4, x0 + tile_size - 5, y0 + tile_size - 5], fill=(200, 80, 80), width=2)

                short_name = os.path.basename(img_path)[:16]
                draw.rectangle([x0 + 1, y0 + tile_size, x0 + tile_size - 2, y0 + cell_h - 2], fill=(22, 24, 28))
                draw.text((x0 + 4, y0 + tile_size + 4), f"#{idx} {short_name}", fill=(235, 240, 248), font=font)
                tile_manifest.append(f"#{idx}: {os.path.basename(img_path)}")

            grid_prompt = (
                f"Bu ızgara görselinde #1'den #{n}'e kadar numaralandırılmış {n} adet proje ikonu/görseli vardır.\n"
                "Her kare için SADECE aşağıdaki tek satır biçiminde 1 kısa teknik cümle yaz (ikonun sembolü, renk/şekli, okunan metin varsa yazısı ve muhtemel UI/oyun rolü):\n"
                "[#1] <kısa açıklama>\n"
                f"...\n[# {n}] değil -> [#{n}] <kısa açıklama>\n\nDosya listesi:\n" + "\n".join(tile_manifest)
            )

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                    tmp_path = tf.name
                sheet.save(tmp_path, format="PNG")
                raw_text = self.analyze_image(tmp_path, custom_prompt=grid_prompt)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

            if not raw_text or raw_text.startswith(("[HATA", "[Gemini", "[API")):
                continue

            for line in raw_text.splitlines():
                m = re.match(r"^\s*\*{0,2}\[?\s*#\s*(\d+)\s*\]?\*{0,2}\s*[:\-–]?\s*(.+)$", line)
                if m:
                    idx_num = int(m.group(1))
                    desc = m.group(2).strip()
                    if 1 <= idx_num <= n and desc:
                        results[chunk[idx_num - 1]] = desc

        return results

    def analyze_image(self, image_path: str, custom_prompt: Optional[str] = None, compact: bool = False) -> str:
        """
        👁️ Gemini Vision / Çok Modlu Görsel Analizi.
        Görseli piksel piksel inceleyerek UI/UX düzenini, OCR metinlerini, renk paletini,
        oyun varlıklarını ve yazılım mimarisi için teknik gereksinimleri çıkarır.
        compact=True verildiğinde tekil ikon/varlıklar için 1-2 cümlelik yoğun özet üretir.
        """
        if not os.path.exists(image_path):
            return f"[HATA: Görsel bulunamadı ({image_path})]"

        if not self.client:
            return f"[Gemini Vision İstemcisi Başlatılamadı - Dosya: {os.path.basename(image_path)}]"

        if compact and not custom_prompt:
            fname = os.path.basename(image_path)
            custom_prompt = (
                f"Describe this asset/icon image ('{fname}') concisely in 1-2 technical sentences in Turkish. "
                "Identify what it depicts (UI icon, sprite, texture, screenshot, diagram), any readable text/labels, "
                "main colors/shape, and its likely role in software or game UI."
            )

        from PIL import Image
        try:
            with Image.open(image_path) as pil_img:
                if pil_img.mode not in ("RGB", "RGBA"):
                    pil_img = pil_img.convert("RGB")
                w, h = pil_img.size
                format_adi = pil_img.format or os.path.splitext(image_path)[1].upper().replace(".", "")
                boyut_kb = os.path.getsize(image_path) / 1024

                prompt = custom_prompt or (
                    "Sen dünya çapında bir Baş Yazılım Mimarı, UI/UX Tasarımcısı ve Bilgisayarlı Görme (Computer Vision) Uzmanısın.\n"
                    "Bu görseli bir yazılım veya oyun projesinde kaynak/referans olarak kullanılmak üzere en ince detayına kadar teknik olarak analiz et:\n\n"
                    "1. GÖRSEL KATEGORİSİ: (Örn: Arayüz/Web Tasarımı, Oyun Sahnesi/Level Mockup, Karakter/Sprite, Sistem/Akış Diyagramı, Belge/Form, Fotoğraf vb.)\n"
                    "2. BİLEŞENLER VE DÜZEN (LAYOUT): Görseldeki tüm butonlar, kartlar, pencereler, karakterler, zeminler, düşmanlar, engeller veya mimari bloklar.\n"
                    "3. TESPİT EDİLEN TÜM METİNLER (OCR): Görsel üzerindeki tüm yazılar, buton etiketleri, başlıklar, menüler ve sayılar.\n"
                    "4. RENK PALETİ VE GÖRSEL STİL: Hakim renkler (Hex/RGB tahminleri), tema (karanlık mod, piksel sanatı, flat design vb.), tipografi özellikleri.\n"
                    "5. KODLAMA VE ENTEGRASYON YÖNERGELERİ: Bu görseli koda (HTML5/CSS/JS, Unity C#, Python vb.) dökecek olan amele yapay zeka ajanları için kesin ve net parametreler.\n\n"
                    "Net, maddeler halinde ve profesyonel bir teknik şartname diliyle açıkla:"
                )

                print(f"   👁️ [Gemini Vision]: '{os.path.basename(image_path)}' ({w}x{h}, {boyut_kb:.1f} KB) analiz ediliyor...")
                
                modeller = [self.active_model] + [m for m in DEFAULT_GEMINI_CANDIDATES if m != self.active_model]
                son_err = None

                for hedef_m in modeller:
                    try:
                        response = self.client.models.generate_content(
                            model=hedef_m,
                            contents=[pil_img, prompt]
                        )
                        if response and response.text:
                            self.active_model = hedef_m
                            print(f"   └ 🟢 [Görsel Analizi Başarılı ({hedef_m})]: {os.path.basename(image_path)} ({len(response.text)} karakter analiz üretildi)")
                            return (
                                f"📊 [GÖRSEL BİLGİSİ: {os.path.basename(image_path)} - {w}x{h} px, {boyut_kb:.1f} KB]\n"
                                f"🔍 GEMINI VISION TEKNİK ANALİZİ:\n{response.text.strip()}"
                            )
                    except Exception as me:
                        son_err = me
                        err_s = str(me)
                        if "503" in err_s or "429" in err_s or "404" in err_s:
                            continue
                        break

                if son_err:
                    raise son_err
                return f"[Görsel: {os.path.basename(image_path)} - {w}x{h}, {boyut_kb:.1f} KB - Model analiz metni döndürmedi]"
        except Exception as e:
            print(f"   ⚠️ [Gemini Vision Analiz Uyarısı]: {e}")
            try:
                from PIL import Image
                with Image.open(image_path) as fallback_img:
                    fw, fh = fallback_img.size
                    return f"[Görsel Meta: {os.path.basename(image_path)} - Boyut: {fw}x{fh} px, {os.path.getsize(image_path)//1024} KB (Detaylı analiz hatası: {e})]"
            except Exception:
                return f"[Görsel: {os.path.basename(image_path)} ({os.path.getsize(image_path)//1024} KB)]"

    def _handle_rate_limit_error(self, err_msg: str):
        """Dakikalık limit (RPM) ile Günlük limit (RPD) ayrımını yapar."""
        kucuk = err_msg.lower()
        if "per day" in kucuk or "daily" in kucuk or "quota exceeded for metric ... per day" in kucuk or self._consecutive_rate_limits >= 3:
            if not self._daily_quota_exhausted:
                print("   🚨 [Gemini Devre Kesici]: GÜNLÜK KOTA (RPD) Tükendi! Oturum boyunca Şef NIM Mimar modeline emanet.")
                self._daily_quota_exhausted = True
        else:
            self._consecutive_rate_limits += 1
            self._cooldown_until = time.time() + 60.0
            print(f"   ⏳ [Gemini Devre Kesici]: Dakikalık limit (RPM) aşıldı ({self._consecutive_rate_limits}. kez). 60s soğuma penceresi açıldı, bu istek NIM'e devrediliyor...")

    def _delegate_to_nim(self, prompt: str, system_instruction: str, temperature: float) -> str:
        """Şef'in kimliğini ve talimatlarını koruyarak çıkarımı sağlıklı bir NVIDIA NIM modeline yaptırır."""
        from infrastructure.nim_client import nim_service
        if nim_service.client:
            yedek_m = nim_service.get_best_model_for_capability("reasoning")
            print(f"   👑 [Şef Mimar Devri -> NIM ({yedek_m.split('/')[-1]})]: Çıkarım güvenle yürütülüyor...")
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            return nim_service.complete_with_retry(
                model_id=yedek_m,
                messages=messages,
                temperature=temperature,
                max_tokens=8192
            )
        raise RuntimeError("NVIDIA NIM istemcisi devralamadı.")

    def _pick_next_gemini_model(self, tried: set) -> Optional[str]:
        now = time.time()
        havuz = [self.configured_model] + [m for m in DEFAULT_GEMINI_CANDIDATES if m != self.configured_model]
        for cand in havuz:
            if cand in tried or cand in self._dead_models:
                continue
            if now >= self._model_cooldowns.get(cand, 0.0):
                return cand
        for cand in havuz:
            if cand not in tried and cand not in self._dead_models:
                return cand
        return None

    def generate_with_retry(
        self,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.2,
        max_retries: int = 4,
        initial_delay: float = 1.0,
        backoff_factor: float = 1.5,
        allow_nim_fallback: bool = True
    ) -> str:
        """
        Exponential backoff ve devre kesici ile güvenli metin üretimi yapar.
        - 503/404 hatalarında aynı modele dönmeden sağlıklı alternatif Gemini modellerini dener.
        - Günlük kota bittiyse (ve allow_nim_fallback=True ise) NIM'e geçer; Worker fallback'larında NIM<->Gemini döngüsünü önler.
        """
        if self._daily_quota_exhausted:
            if allow_nim_fallback:
                return self._delegate_to_nim(prompt, system_instruction, temperature)
            raise RuntimeError("Gemini günlük kotası tükenmiş ve NIM geri dönüşü devre dışı.")

        suan = time.time()
        if suan < self._cooldown_until:
            if allow_nim_fallback:
                kalan = int(self._cooldown_until - suan)
                print(f"   ⏳ [Gemini Soğuma Modu]: {kalan}s kaldı. İstek NIM Mimar modeline yönlendiriliyor...")
                return self._delegate_to_nim(prompt, system_instruction, temperature)

        if not self.client:
            if allow_nim_fallback:
                return self._delegate_to_nim(prompt, system_instruction, temperature)
            raise RuntimeError("Gemini istemcisi yapılandırılmamış.")

        delay = initial_delay
        son_hata = None
        tried_models: set = set()
        if time.time() < self._model_cooldowns.get(self.active_model, 0.0) or self.active_model in self._dead_models:
            next_ok = self._pick_next_gemini_model(tried_models)
            if next_ok:
                self.active_model = next_ok

        attempts_budget = max(max_retries, len(DEFAULT_GEMINI_CANDIDATES))

        for attempt in range(1, attempts_budget + 1):
            hedef_model = self.active_model
            tried_models.add(hedef_model)
            try:
                cfg_kwargs: Dict[str, Any] = {
                    "temperature": temperature,
                    "system_instruction": system_instruction if system_instruction else None
                }
                config = types.GenerateContentConfig(**cfg_kwargs)
                response = self.client.models.generate_content(
                    model=hedef_model,
                    contents=prompt,
                    config=config
                )
                if response and response.text:
                    self._consecutive_rate_limits = 0
                    self._is_healthy = True
                    return response.text.strip()
                raise RuntimeError("Gemini boş yanıt döndürdü.")
            except Exception as e:
                son_hata = e
                err_msg = str(e)
                is_rate_limit = "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "rate limit" in err_msg.lower()
                is_dead = "404" in err_msg or "NOT_FOUND" in err_msg or "no longer available" in err_msg.lower()
                is_unavailable = is_dead or "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower()

                if is_dead:
                    self._dead_models.add(hedef_model)
                elif is_unavailable:
                    self._model_cooldowns[hedef_model] = time.time() + 45.0
                elif is_rate_limit:
                    self._model_cooldowns[hedef_model] = time.time() + 60.0

                next_m = self._pick_next_gemini_model(tried_models)
                if next_m:
                    print(f"   🔄 [Gemini Model Değişimi ({hedef_model} {'404/Kapalı' if is_dead else 'Yoğun/Limit'})]: '{next_m}' devreye alınıyor...")
                    self.active_model = next_m
                    if not is_unavailable and attempt < attempts_budget:
                        time.sleep(min(delay, 1.5))
                        delay *= backoff_factor
                    continue

                if is_rate_limit:
                    self._handle_rate_limit_error(err_msg)
                break

        if allow_nim_fallback:
            from infrastructure.nim_client import nim_service
            if nim_service.client and nim_service.has_healthy_fast_model():
                try:
                    return self._delegate_to_nim(prompt, system_instruction, temperature)
                except Exception as fallback_err:
                    print(f"   ⚠️ [NIM Fallback Hatası]: {fallback_err}")

        raise son_hata or RuntimeError(f"Tüm Gemini modelleri yanıt vermedi (Denenen: {', '.join(tried_models)}).")

gemini_service = GeminiClient()

