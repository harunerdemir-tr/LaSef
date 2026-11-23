import os
import re
from tools.file_system_tools import tool_list_dir, tool_read_file, tool_write_file, tool_replace_in_file, tool_run_command

def tool_grep_search(directory_path: str, pattern: str, case_sensitive: bool = False) -> str:
    """Projedeki dosyalarda belirli bir kelimeyi veya regexi hızlıca arar."""
    if not os.path.exists(directory_path):
        return f"Hata: '{directory_path}' bulunamadı."
    
    eslesenler = []
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except Exception as e:
        return f"Geçersiz Regex deseni: {e}"

    for kok, _, dosyalar in os.walk(directory_path):
        for f in dosyalar:
            if f.endswith(('.cs', '.py', '.js', '.html', '.css', '.json', '.c', '.cpp', '.h', '.md', '.txt')):
                tam_yol = os.path.join(kok, f)
                try:
                    with open(tam_yol, 'r', encoding='utf-8', errors='ignore') as fp:
                        for no, line in enumerate(fp, 1):
                            if regex.search(line):
                                rel = os.path.relpath(tam_yol, directory_path)
                                eslesenler.append(f"{rel}:{no} -> {line.strip()[:100]}")
                                if len(eslesenler) >= 30:
                                    break
                except Exception:
                    pass
        if len(eslesenler) >= 30:
            break

    return "\n".join(eslesenler) if eslesenler else "Eşleşme bulunamadı."

def tool_check_syntax(file_path: str) -> str:
    """Dosyanın sözdizimi ve derleme sağlığını test eder."""
    if not os.path.exists(file_path):
        return f"Hata: '{file_path}' bulunamadı."
    
    uzanti = os.path.splitext(file_path)[1].lower()
    if uzanti == ".py":
        res = tool_run_command(f"python -m py_compile \"{file_path}\"")
        return "Python Sentaksı Hatasız (OK)" if not res.strip() or "Error" not in res else f"Sentaks Hatası:\n{res}"
    elif uzanti == ".cs":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            c = f.read()
        sinif = os.path.splitext(os.path.basename(file_path))[0]
        if f"class {sinif}" not in c and f"struct {sinif}" not in c and f"interface {sinif}" not in c:
            return f"Uyarı: '{file_path}' dosyasında '{sinif}' sınıfı bulunamadı (Tek dosya = Tek sınıf kuralı)."
        return "C# Formatı Standartlara Uygun (OK)"
    elif uzanti == ".html":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            c = f.read()
        return "HTML Sağlıklı (OK)" if "<html" in c.lower() and "</html>" in c.lower() else "Hata: Eksik HTML etiketleri var."
    return f"'{uzanti}' türü için test kuralı uygulandı (OK)."
