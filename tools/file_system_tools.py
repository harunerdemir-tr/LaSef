import os
import subprocess
from typing import Dict, Any, List

def tool_list_dir(directory_path: str) -> str:
    """Belirtilen dizindeki dosya ve klasörleri listeler."""
    if not os.path.exists(directory_path):
        return f"Hata: '{directory_path}' dizini bulunamadı."
    try:
        items = os.listdir(directory_path)
        detaylar = []
        for it in items[:60]:
            tam = os.path.join(directory_path, it)
            tur = "[KLASÖR]" if os.path.isdir(tam) else "[DOSYA]"
            boyut = os.path.getsize(tam) if os.path.isfile(tam) else 0
            detaylar.append(f"{tur} {it} ({boyut} bytes)")
        return "\n".join(detaylar) if detaylar else "Dizin boş."
    except Exception as e:
        return f"Listeleme hatası: {str(e)}"

def tool_read_file(file_path: str, max_lines: int = 400) -> str:
    """Belirtilen dosyanın içeriğini okur."""
    if not os.path.exists(file_path):
        return f"Hata: '{file_path}' dosyası bulunamadı."
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            satirlar = f.readlines()
        return "".join(satirlar[:max_lines])
    except Exception as e:
        return f"Dosya okuma hatası: {str(e)}"

def tool_write_file(file_path: str, content: str) -> str:
    """Belirtilen dosyayı oluşturur veya üzerine yazar."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Başarılı: '{file_path}' ({len(content)} karakter) kaydedildi."
    except Exception as e:
        return f"Yazma hatası: {str(e)}"

def tool_replace_in_file(file_path: str, target_content: str, replacement_content: str) -> str:
    """Dosya içindeki belirli bir kod bloğunu yenisiyle değiştirir."""
    if not os.path.exists(file_path):
        return f"Hata: '{file_path}' bulunamadı."
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            icerik = f.read()
        if target_content not in icerik:
            return "Hata: Değiştirilecek hedef metin dosya içinde bulunamadı."
        yeni_icerik = icerik.replace(target_content, replacement_content, 1)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yeni_icerik)
        return f"Başarılı: '{file_path}' güncellendi."
    except Exception as e:
        return f"Değiştirme hatası: {str(e)}"

def tool_run_command(command: str, cwd: str = None) -> str:
    """Terminalde (CMD/PowerShell) komut çalıştırır ve çıktısını döndürür."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180.0
        )
        cikti = result.stdout + "\n" + result.stderr
        return cikti.strip() if cikti.strip() else "[Komut başarıyla çalıştı, çıktı yok]"
    except subprocess.TimeoutExpired:
        return "Hata: Komut zaman aşımına uğradı (180s)."
    except Exception as e:
        return f"Komut çalıştırma hatası: {str(e)}"
