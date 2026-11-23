import os
import sys
import yaml

def get_resource_path(relative_path: str) -> str:
    """PyInstaller bundle veya normal çalışma dizinine göre dosya yolunu çözer."""
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        p1 = os.path.join(base_path, relative_path)
        if os.path.exists(p1):
            return p1
        p2 = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(p2):
            return p2
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)

def load_config() -> dict:
    """config.yaml dosyasını güvenli yükler."""
    config_path = get_resource_path("config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {
        "sef": {"varsayilan_saglayici": "gemini", "model": "gemini-3.5-flash-lite", "max_deneme": 4, "timeout": 90.0},
        "isci": {"max_paralel": 4, "timeout_per_request": 75.0, "sync_timeout": 120.0},
        "golge_ajan": {"aktif": True, "seviye": 1, "llm_model": "nvidia/nemotron-3.5-lightning-30b-a3b"},
        "modeller": {
            "genel": ["nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "poolside/laguna-xs-2.1"],
            "html": ["nvidia/nemotron-3.5-lightning-30b-a3b", "poolside/laguna-xs-2.1"],
            "css": ["nvidia/nemotron-3.5-bolt-e4b", "nvidia/nemotron-3.5-lightning-30b-a3b"],
            "kodlama": ["nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "poolside/laguna-xs-2.1", "nvidia/nemotron-3-ultra-550b-a55b"],
            "vision": ["nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/cosmos-reason2-8b"]
        }
    }
