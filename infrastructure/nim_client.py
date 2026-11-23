import os
import sys
import time
import random
import threading
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openai import OpenAI

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

DEFAULT_NIM_CANDIDATES = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "poolside/laguna-xs-2.1",
    "nvidia/nemotron-3.5-bolt-e4b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "stepfun-ai/step-5-preview",
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "nvidia/cosmos-reason2-8b"
]

KNOWN_EOL_OR_NON_TEXT = (
    "llama-3.2-11b-vision-instruct",
    "nemotron-3-super-120b-a12b",
    "nemotron-nano-3-30b-a3b",
    "codestral-22b-instruct",
    "qwen2.5-coder-32b",
    "diffusiongemma-26b",
)

class NimClient:
    """
    Dayanıklı NVIDIA NIM API İstemcisi.
    - Eşzamanlı istek sınırlayıcı (Concurrency Semaphore) ile 429 ve kuyruk kilitlenmelerini önler
    - Yük dengeleyici (Round-Robin) + sağlıklı/soğuma dışı model seçimi
    - 404/410 EOL modelleri kalıcı kara listeye alıp database.json'dan otomatik düşürür
    - 429/503/Zaman Aşımı hatalarında model bazlı geçici soğuma (circuit breaker) uygular
    - Streaming + wall-clock deadline + max_retries=0 ile 3x timeout çarpanını önler
    """
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://integrate.api.nvidia.com/v1"):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY") or os.getenv("NIM_API_KEY")
        self.base_url = os.getenv("NVIDIA_BASE_URL", base_url)
        self.client: Optional[OpenAI] = None
        self.available_catalog: List[str] = []
        self.verified_models: List[str] = []
        self.model_latencies: Dict[str, float] = {}
        self.capability_model_map: Dict[str, str] = {}
        self.dead_models: set = set()
        self._cooldown_until: Dict[str, float] = {}
        self._failure_counts: Dict[str, int] = {}
        self._cache_checked_at: float = 0.0
        self._is_healthy = False
        self._max_concurrent = int(os.getenv("NIM_MAX_CONCURRENT", "4"))
        self._semaphore = threading.BoundedSemaphore(value=self._max_concurrent)
        self._round_robin_idx = 0
        self._rr_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._load_cached_database()

        if self.api_key:
            try:
                http_timeout: Any = 65.0
                try:
                    import httpx
                    http_timeout = httpx.Timeout(connect=12.0, read=65.0, write=20.0, pool=10.0)
                except Exception:
                    pass
                self.client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    timeout=http_timeout,
                    max_retries=0
                )
            except Exception as e:
                print(f"[NimClient] İstemci başlatılamadı: {e}")

    def _db_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database.json")

    def _load_cached_database(self):
        """database.json'daki canlı modelleri belleğe alır; bilinen EOL modelleri ayıklar."""
        try:
            db_path = self._db_path()
            if os.path.exists(db_path):
                import json
                with open(db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._cache_checked_at = float(data.get("checked_at", 0.0) or os.path.getmtime(db_path))
                for dm in data.get("dead_models", []):
                    self.dead_models.add(dm)
                modeller = []
                for m in data.get("modeller", []):
                    mid = m.get("id")
                    if not mid:
                        continue
                    if any(bad in mid.lower() for bad in KNOWN_EOL_OR_NON_TEXT) or mid in self.dead_models:
                        self.dead_models.add(mid)
                        continue
                    modeller.append(mid)
                    if "latency_sec" in m:
                        self.model_latencies[mid] = float(m["latency_sec"])
                if modeller:
                    self.verified_models = modeller
                    self._is_healthy = True
        except Exception:
            pass

    def _save_cached_database(self):
        """Doğrulanmış canlı model listesini ve ölü model kaydını database.json'a yazar."""
        try:
            import json
            sync_list = []
            for vm in self.verified_models:
                sync_list.append({
                    "id": vm,
                    "tur": "Canlı Doğrulanmış Model",
                    "latency_sec": round(self.model_latencies.get(vm, 0.0), 3)
                })
            payload = {
                "aciklama": "LaSef NVIDIA NIM Canlı Doğrulanmış Model Veritabanı (Otomatik Güncellenir)",
                "checked_at": self._cache_checked_at or time.time(),
                "dead_models": sorted(self.dead_models),
                "modeller": sync_list
            }
            with open(self._db_path(), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def needs_health_refresh(self, max_age_sec: float = 1800.0) -> bool:
        """Önbellek bayatsa veya yeterli sağlıklı hızlı model yoksa True döner."""
        if not self._is_healthy or not self.verified_models:
            return True
        if any(any(bad in m.lower() for bad in KNOWN_EOL_OR_NON_TEXT) for m in self.verified_models):
            return True
        if (time.time() - (self._cache_checked_at or 0.0)) > max_age_sec:
            return True
        return not self.has_healthy_fast_model()

    def _is_model_available(self, model_id: str) -> bool:
        with self._state_lock:
            if model_id in self.dead_models:
                return False
            until = self._cooldown_until.get(model_id, 0.0)
            return time.time() >= until

    def _mark_model_dead(self, model_id: str, reason: str = ""):
        with self._state_lock:
            self.dead_models.add(model_id)
            if model_id in self.verified_models:
                self.verified_models = [m for m in self.verified_models if m != model_id]
            self._save_cached_database()
        print(f"   🚫 [NIM Kalıcı Eleme]: '{model_id}' havuzdan çıkarıldı ({reason[:60]}).")

    def _mark_model_cooldown(self, model_id: str, base_seconds: float = 25.0, reason: str = ""):
        with self._state_lock:
            cnt = self._failure_counts.get(model_id, 0) + 1
            self._failure_counts[model_id] = cnt
            cooldown = min(180.0, base_seconds * (2 ** min(cnt - 1, 3)))
            self._cooldown_until[model_id] = time.time() + cooldown
        print(f"   🧊 [NIM Soğuma ({cooldown:.0f}s)]: '{model_id.split('/')[-1]}' ({reason[:50]}).")

    def _mark_model_success(self, model_id: str, latency: Optional[float] = None):
        with self._state_lock:
            self._failure_counts[model_id] = 0
            self._cooldown_until.pop(model_id, None)
            if latency is not None:
                self.model_latencies[model_id] = round(latency, 3)

    def has_healthy_fast_model(self) -> bool:
        """Soğuma veya kara listede olmayan hızlı en az bir NIM modeli var mı?"""
        return any(
            self._is_model_available(m) and not self._is_vision_only(m)
            for m in (self.verified_models or [])
        )

    @staticmethod
    def _is_vision_only(model_id: str) -> bool:
        low = model_id.lower()
        return any(v in low for v in ("-vl-", "vision", "cosmos-reason", "vila", "neva", "kosmos", "fuyu"))

    def fetch_catalog(self) -> List[str]:
        """NVIDIA NIM üzerindeki tüm güncel canlı model listesini çeker."""
        if not self.client:
            return []
        try:
            res = self.client.models.list()
            self.available_catalog = [m.id for m in res.data]
            return self.available_catalog
        except Exception as e:
            print(f"⚠️ [NIM Katalog Hatası]: {e}")
            return []

    def health_check(self, candidates: Optional[List[str]] = None) -> List[str]:
        """
        NIM modellerinin kataloğunu çeker, aday modellerin EOL olup olmadığını eler,
        mikro ping ile yanıt sürelerini ölçüp en hızlı çalışan modelleri havuzlar.
        """
        if not self.client:
            print("❌ [NIM Sağlık Uyarısı]: API Anahtarı bulunamadı.")
            self._is_healthy = False
            return []

        print("⚡ [NIM Sağlık Kontrolü]: Aktif NIM modelleri taranıyor...")
        catalog = self.fetch_catalog()
        
        db_candidates = []
        try:
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database.json")
            if os.path.exists(db_path):
                import json
                with open(db_path, "r", encoding="utf-8") as f:
                    db_data = json.load(f)
                    db_candidates = [m["id"] for m in db_data.get("modeller", []) if "id" in m]
        except Exception:
            pass

        uygun_anahtarlar = ["instruct", "chat", "nemotron", "llama", "coder", "deepseek", "mistral", "laguna", "step-5", "gpt-oss", "vision"]
        kara_liste = ["embed", "guard", "safety", "reward", "parse", "translate", "audio", "asr", "tts", "whisper", "sdxl", "clip", "ocr", "speech", "retrieval", "moderation", "synthetic-video"]

        katalog_adaylari = [
            m for m in catalog
            if any(k in m.lower() for k in uygun_anahtarlar)
            and not any(ex in m.lower() for ex in kara_liste)
            and not any(bad in m.lower() for bad in KNOWN_EOL_OR_NON_TEXT)
        ] if catalog else []

        birlesik_adaylar = [m for m in DEFAULT_NIM_CANDIDATES if not any(ex in m.lower() for ex in kara_liste)]
        for dbm in db_candidates:
            if dbm not in birlesik_adaylar and not any(ex in dbm.lower() for ex in kara_liste) and not any(bad in dbm.lower() for bad in KNOWN_EOL_OR_NON_TEXT):
                birlesik_adaylar.append(dbm)
        for km in katalog_adaylari:
            if km not in birlesik_adaylar and len(birlesik_adaylar) < 12:
                birlesik_adaylar.append(km)

        valid_candidates = birlesik_adaylar if not catalog else [m for m in birlesik_adaylar if m in catalog]

        canli_listesi = []
        gecikmeler = {}

        def _tekil_ping(m_id: str) -> Tuple[str, bool, float]:
            t0 = time.time()
            try:
                cli = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=4.5, max_retries=0)
                try:
                    res = cli.chat.completions.create(
                        model=m_id,
                        messages=[{"role": "user", "content": "Reply OK"}],
                        max_tokens=32,
                        temperature=0.0,
                        extra_body={"chat_template_kwargs": {"enable_thinking": False}}
                    )
                except Exception as first_err:
                    err_s = str(first_err).lower()
                    if "400" in err_s or "extra_body" in err_s or "unexpected" in err_s or "chat_template" in err_s:
                        res = cli.chat.completions.create(
                            model=m_id,
                            messages=[{"role": "user", "content": "Reply OK"}],
                            max_tokens=64,
                            temperature=0.0
                        )
                    else:
                        raise
                elapsed = time.time() - t0
                msg = res.choices[0].message if res and res.choices else None
                content = (msg.content or "").strip() if msg else ""
                has_reasoning = bool(getattr(msg, "reasoning_content", None)) if msg else False
                success = bool(content or has_reasoning)
                return (m_id, success, elapsed)
            except Exception:
                return (m_id, False, time.time() - t0)

        with ThreadPoolExecutor(max_workers=min(len(valid_candidates), 12) or 1) as pool:
            futures = [pool.submit(_tekil_ping, m) for m in valid_candidates]
            for fut in as_completed(futures):
                m_id, ok, elapsed = fut.result()
                if ok and elapsed < 4.5:
                    canli_listesi.append(m_id)
                    gecikmeler[m_id] = elapsed

        canli_listesi.sort(key=lambda x: (1 if self._is_vision_only(x) else 0, gecikmeler.get(x, 99.0)))
        with self._state_lock:
            self.verified_models = canli_listesi
            self.model_latencies = gecikmeler
            self._cache_checked_at = time.time()
            self._cooldown_until.clear()
            self._failure_counts.clear()
            self._is_healthy = len(canli_listesi) > 0
            if self.verified_models:
                self._save_cached_database()

        if self.verified_models:
            ozet = ", ".join([f"{m.split('/')[-1]} ({gecikmeler.get(m, 0):.2f}s)" for m in self.verified_models])
            print(f"   └ 🟢 {len(self.verified_models)} Canlı NIM Modeli Doğrulandı: {ozet}")
        else:
            print("   └ ❌ Hiçbir NIM modeli yanıt vermedi!")

        return self.verified_models

    def get_best_model_for_capability(self, capability: str, exclude: Optional[set] = None) -> str:
        """Uzmanlık türüne ve model sağlığına (soğuma/kara liste) göre en uygun canlı modeli seçer."""
        if not self.verified_models:
            self.health_check()

        exclude = exclude or set()
        if not self.verified_models:
            return "nvidia/nemotron-3.5-lightning-30b-a3b"

        kucuk = (capability or "general").lower()
        is_vision_req = "vision" in kucuk or "gorsel" in kucuk or "görsel" in kucuk
        havuz = [
            m for m in self.verified_models
            if m not in exclude and self._is_model_available(m) and (is_vision_req or not self._is_vision_only(m))
        ]
        if not havuz:
            havuz = [
                m for m in self.verified_models
                if m not in exclude and m not in self.dead_models and (is_vision_req or not self._is_vision_only(m))
            ]
        if not havuz:
            havuz = [m for m in self.verified_models if m not in exclude] or list(self.verified_models)

        uygun_modeller: List[str] = []

        if any(k in kucuk for k in ["code", "kod", "game", "dev", "unity", "blender", "c#", "python", "web", "html", "fullstack", "js", "javascript"]):
            for m in havuz:
                if any(x in m.lower() for x in ["3.5-lightning", "laguna", "nano-omni", "coder", "deepseek"]):
                    uygun_modeller.append(m)
            if not uygun_modeller:
                for m in havuz:
                    if any(x in m.lower() for x in ["ultra", "550b", "3.5-bolt", "nemotron", "mistral"]):
                        uygun_modeller.append(m)

        elif any(k in kucuk for k in ["reason", "math", "algo", "logic", "fizik", "physics", "consult", "peer", "heavy", "deep"]):
            for m in havuz:
                if any(x in m.lower() for x in ["nano-omni", "3.5-lightning", "ultra", "550b", "laguna", "step-5"]):
                    uygun_modeller.append(m)

        elif any(k in kucuk for k in ["fast", "report", "rapor", "audit", "qa", "review", "judge", "hakem"]):
            for m in havuz:
                if any(x in m.lower() for x in ["laguna", "3.5-lightning", "3.5-bolt", "nano-omni"]):
                    uygun_modeller.append(m)

        elif is_vision_req:
            for m in havuz:
                if self._is_vision_only(m):
                    uygun_modeller.append(m)

        if not uygun_modeller:
            uygun_modeller = havuz

        uygun_modeller.sort(key=lambda m: self.model_latencies.get(m, 5.0))
        top_tier = uygun_modeller[:min(3, len(uygun_modeller))]
        with self._rr_lock:
            secilen = top_tier[self._round_robin_idx % len(top_tier)]
            self._round_robin_idx += 1
            return secilen

    def _call_single_attempt(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout: float,
        disable_thinking: bool = False
    ) -> Tuple[str, float]:
        """Tek bir NIM çağrısını streaming + wall-clock deadline ile yürütür."""
        t0 = time.time()
        deadline = t0 + max(10.0, float(timeout))

        kwargs: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": min(max_tokens, 16384),
            "timeout": timeout,
            "stream": True,
        }
        if disable_thinking:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        with self._semaphore:
            try:
                stream = self.client.chat.completions.create(**kwargs)
            except Exception as e:
                if disable_thinking and ("400" in str(e) or "extra_body" in str(e).lower() or "unexpected" in str(e).lower()):
                    kwargs.pop("extra_body", None)
                    stream = self.client.chat.completions.create(**kwargs)
                else:
                    raise

            chunks: List[str] = []
            reasoning_chunks: List[str] = []
            for chunk in stream:
                if time.time() > deadline:
                    raise TimeoutError(f"NIM streaming zaman aşımı ({timeout:.0f}s)")
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                part = getattr(delta, "content", None)
                if part:
                    chunks.append(part)
                rc = getattr(delta, "reasoning_content", None)
                if rc:
                    reasoning_chunks.append(rc)

        full_text = "".join(chunks).strip()
        if not full_text:
            reasoning_text = "".join(reasoning_chunks).strip()
            if "```" in reasoning_text and len(reasoning_text) > 100:
                return reasoning_text, (time.time() - t0)
            if reasoning_text:
                raise RuntimeError("NIM sadece reasoning üretti, nihai içerik boş kaldı.")
            raise RuntimeError("NIM boş içerik döndürdü.")
        return full_text, (time.time() - t0)

    def complete_with_retry(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.15,
        max_tokens: int = 8192,
        max_retries: int = 2,
        initial_delay: float = 0.8,
        backoff_factor: float = 1.5,
        timeout: float = 45.0,
        disable_thinking: bool = False
    ) -> str:
        """
        NVIDIA NIM üzerinden streaming destekli dayanıklı chat completion çağrısı yapar.
        - Denediği ve başarısız olan modele aynı istek içinde geri dönmez (ping-pong sıfır).
        - Backoff uykularını semafor dışında bekler, diğer worker'ları kilitlemez.
        """
        if not self.client:
            raise RuntimeError("NIM Client yapılandırılmamış (API anahtarı eksik).")

        hedef_model = model_id
        if self.verified_models and (hedef_model not in self.verified_models or not self._is_model_available(hedef_model)):
            hedef_model = self.get_best_model_for_capability("code")
        elif not self.verified_models and not self._is_healthy:
            raise RuntimeError("Aktif veya doğrulanmış canlı NIM modeli yok (403/410/yetki hatası).")

        delay = initial_delay
        son_hata = None
        tried_models: set = set()
        effective_retries = max(1, min(max_retries, len(self.verified_models) or 1, 3))

        for attempt in range(1, effective_retries + 1):
            tried_models.add(hedef_model)
            use_no_think = disable_thinking or any(k in hedef_model.lower() for k in ("lightning", "nano-omni", "bolt"))
            try:
                text, elapsed = self._call_single_attempt(
                    model_id=hedef_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    disable_thinking=use_no_think
                )
                self._mark_model_success(hedef_model, latency=elapsed)
                return text
            except Exception as e:
                son_hata = e
                err_str = str(e)
                is_rate_limit = "429" in err_str or "503" in err_str or "rate limit" in err_str.lower() or "resourceexhausted" in err_str.lower()
                is_gone = "410" in err_str or "Gone" in err_str or "404" in err_str or "Not Found" in err_str
                is_auth = "403" in err_str or "401" in err_str or "Authorization failed" in err_str
                is_timeout = "timeout" in err_str.lower() or "timed out" in err_str.lower() or "zaman aşımı" in err_str.lower()

                if is_auth:
                    self._is_healthy = False
                    raise RuntimeError(f"NVIDIA NIM Yetki Hatası (403 Forbidden): {e}")

                if is_gone:
                    self._mark_model_dead(hedef_model, err_str)
                else:
                    cool_base = 35.0 if is_timeout else (25.0 if is_rate_limit else 15.0)
                    self._mark_model_cooldown(hedef_model, base_seconds=cool_base, reason=err_str)

                next_candidates = [
                    m for m in self.verified_models
                    if m not in tried_models and self._is_model_available(m) and not self._is_vision_only(m)
                ]
                if not next_candidates:
                    next_candidates = [
                        m for m in self.verified_models
                        if m not in tried_models and not self._is_vision_only(m)
                    ]
                if next_candidates:
                    eski_model = hedef_model
                    next_candidates.sort(key=lambda m: (1 if "550b" in m or "ultra" in m else 0, self.model_latencies.get(m, 5.0)))
                    hedef_model = next_candidates[0]
                    print(f"   🔄 [NIM Devre Kesici]: '{eski_model.split('/')[-1]}' -> '{hedef_model.split('/')[-1]}' ({'Timeout' if is_timeout else '410/404' if is_gone else 'Hata'}).")
                else:
                    break

                if attempt < effective_retries:
                    sleep_time = delay + random.uniform(0.05, 0.3)
                    tag = "⏳ 429 Rate-Limit" if is_rate_limit else ("⏱️ Zaman Aşımı" if is_timeout else "⚠️ NIM Yedekleme")
                    print(f"   [{tag}] Deneme {attempt}/{effective_retries}. {sleep_time:.2f}s bekleniyor...")
                    time.sleep(sleep_time)
                    delay *= backoff_factor

        raise son_hata or RuntimeError(f"NIM modelleri yanıt vermedi (Denenenler: {', '.join(m.split('/')[-1] for m in tried_models)}).")

    def chat_completion(self, messages: List[Dict[str, str]], model_id: Optional[str] = None, temperature: float = 0.15, max_tokens: int = 8192, timeout: float = 75.0) -> str:
        """Geriye dönük uyumlu ve doğrudan çağrılabilir chat completion köprüsü."""
        m_id = model_id or self.get_best_model_for_capability("general")
        return self.complete_with_retry(
            model_id=m_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

nim_service = NimClient()

