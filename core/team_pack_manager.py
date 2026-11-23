import os
import json
import time

class TeamPackManager:
    """
    📦 TAŞINABİLİR TAKIM PAKETLERİ (Versioned Team Packs):
    Başarılı bir çoklu ajan kadrosunu, rollerini ve kurallarını
    .lasef-pack dosyası olarak dışa aktarır ve başka projelere anında uygular.
    """
    def __init__(self, workspace_path: str = ""):
        self.workspace = workspace_path or "."

    def pack_olustur(self, takim_adi: str, roller: list, aciklama: str = "") -> str:
        pack_data = {
            "version": "1.0.0",
            "team_name": takim_adi,
            "description": aciklama or "LaSef Otonom Çoklu Ajan Takımı",
            "created_at": time.time(),
            "roles": roller
        }
        pack_dosyasi = os.path.join(self.workspace, f"{takim_adi.lower().replace(' ', '_')}.lasef-pack.json")
        try:
            with open(pack_dosyasi, "w", encoding="utf-8") as f:
                json.dump(pack_data, f, indent=2, ensure_ascii=False)
            print(f"   📦 [Takım Paketi Dışa Aktarıldı]: {pack_dosyasi}")
            return pack_dosyasi
        except Exception:
            return ""

    def pack_yukle(self, pack_dosya_yolu: str) -> dict:
        if os.path.exists(pack_dosya_yolu):
            try:
                with open(pack_dosya_yolu, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
