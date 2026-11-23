import os
import sys
import time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from infrastructure.gemini_client import gemini_service, GeminiClient
from infrastructure.nim_client import nim_service, NimClient
from core.config_manager import load_config, get_resource_path

_env_yolu = get_resource_path(".env")
if os.path.exists(_env_yolu):
    load_dotenv(_env_yolu)
else:
    load_dotenv()

CONFIG = load_config()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

gemini_client = gemini_service.client
nvidia_client = nim_service.client

def cagir_gemini_sef(sistem_talimati: str, kullanici_mesaji: str, temperature: float = 0.1) -> str:
    """
    Google GenAI SDK (Gemini) Şef modellerini çağırır.
    429 Rate-Limit koruması, model fallback ve acil durumda NIM fallback desteği içerir.
    """
    try:
        return gemini_service.generate_with_retry(
            prompt=kullanici_mesaji,
            system_instruction=sistem_talimati,
            temperature=temperature,
            max_retries=3
        )
    except Exception as e:
        print(f"⚠️ [Şef Fallback]: Gemini yanıt vermedi ({e}). NVIDIA NIM Yedek Mimar devreye giriyor...")

    if nim_service.client:
        if not nim_service.verified_models:
            nim_service.health_check()
        yedek_model = nim_service.get_best_model_for_capability("reasoning")
        yedek_modeller = [yedek_model] + [
            m for m in nim_service.verified_models
            if m != yedek_model and not nim_service._is_vision_only(m)
        ]
        for y_model in yedek_modeller[:4]:
            try:
                messages = [
                    {"role": "system", "content": sistem_talimati},
                    {"role": "user", "content": kullanici_mesaji}
                ]
                return nim_service.complete_with_retry(
                    model_id=y_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096,
                    max_retries=2
                )
            except Exception:
                continue

    raise RuntimeError("Tüm Şef ve Mimar modelleri yanıt vermedi. İnternet ve API anahtarınızı kontrol edin.")

def canli_modelleri_yokla() -> list:
    """NVIDIA NIM üzerindeki canlı modellerin mikro nabız yanıt hızlarını test eder."""
    modeller = nim_service.health_check()
    return modeller

def get_canli_havuz() -> list:
    return nim_service.verified_models or canli_modelleri_yokla()
