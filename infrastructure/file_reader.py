import os
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader
from infrastructure.gemini_client import gemini_service

import hashlib
import json
import re
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

KOD_METIN_UZANTILARI = {
    ".c", ".h", ".cpp", ".hpp", ".cs", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".scss", ".sass", ".json", ".csv", ".tsv", ".txt", ".md",
    ".markdown", ".yaml", ".yml", ".sql", ".xml", ".sh", ".bat", ".ini",
    ".env", ".toml", ".rs", ".go", ".java", ".kt", ".dart", ".lua",
    ".glsl", ".hlsl", ".shader", ".cginc", ".compute", ".asmdef", ".asmref",
    ".uxml", ".uss"
}

GORSEL_UZANTILARI = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
BELGE_UZANTILARI = {".pdf", ".docx", ".xlsx", ".xls"}

ATLANACAK_KLASORLER = {
    "library", "obj", "bin", "temp", "packagecache", "logs", ".git", ".vs",
    ".vscode", ".idea", "__pycache__", "node_modules", "build", "builds",
    "dist", "venv", ".venv", ".gradle", ".pytest_cache", ".lasef_memory.json",
    "usersettings", "memorycaptures", "recordings", "projectsettings",
    "lasefbridge", "tutorialinfo", "textmesh pro"
}

ATLANACAK_DOSYALAR = {
    "lasef_memory.json", ".lasef_memory.json", ".lasef_branches.json",
    ".lasef_asset_index.json", "packages-lock.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "composer.lock", "cargo.lock",
    "extensions.json", "mcp.json", "launch.json", "tasks.json"
}

ATLANACAK_SONEKLER = (".lasef-pack.json", ".meta", ".pyc", ".pyo", ".tmp")

_ASSET_CACHE_LOCK = threading.Lock()
_DEFAULT_ASSET_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".lasef_asset_index.json"
)


def _is_unity_project(root_dir: str) -> bool:
    """Belirtilen klasörün bir Unity projesi kökü olup olmadığını hızlıca kontrol eder."""
    if not root_dir or not os.path.isdir(root_dir):
        return False
    assets_dir = os.path.join(root_dir, "Assets")
    return os.path.isdir(assets_dir) and (
        os.path.isdir(os.path.join(root_dir, "ProjectSettings"))
        or os.path.isdir(os.path.join(root_dir, "Packages"))
    )


def _should_skip_dir(dir_name: str, parent_dir: str = "", root_dir: str = "") -> bool:
    """Klasörün taranmadan atlanıp atlanmayacağını belirler."""
    low = dir_name.lower()
    if low in ATLANACAK_KLASORLER:
        return True
    if low.startswith(".") or low.startswith("com.unity."):
        return True
    if root_dir and _is_unity_project(root_dir):
        rel_parent = os.path.relpath(parent_dir, root_dir).replace("\\", "/").lower() if parent_dir else ""
        if rel_parent == "packages" or low == "packages":
            if rel_parent == "packages":
                return True
    return False


_TEKIL_YOL_ATLANACAK_KLASORLER = {
    "library", "packagecache", "lasefbridge", "tutorialinfo", "textmesh pro",
    "node_modules", "__pycache__", ".git", ".vs", ".vscode", ".idea",
    ".pytest_cache", "usersettings", "memorycaptures", "recordings", "projectsettings"
}


def is_excluded_path(dosya_yolu: str, root_dir: str = "", strict_filenames: bool = True) -> bool:
    """
    Hem klasör taraması hem de dışarıdan gelen tekil yol listeleri için
    gereksiz önbellek/eklenti/sistem dosyalarını eler.
    Klasör kökü verilmişse üst dizin adlarına (örn. Windows Temp) takılmamak için
    yalnızca kök altındaki göreli segmentleri kontrol eder.
    """
    if not dosya_yolu:
        return True
    norm = os.path.normpath(os.path.abspath(dosya_yolu))

    if root_dir:
        try:
            rel = os.path.relpath(norm, os.path.abspath(root_dir))
            rel_parts = rel.split(os.sep)
        except ValueError:
            rel_parts = norm.split(os.sep)
        dir_parts = rel_parts[:-1]
        yasakli_kume = ATLANACAK_KLASORLER
    else:
        dir_parts = norm.split(os.sep)[:-1]
        yasakli_kume = _TEKIL_YOL_ATLANACAK_KLASORLER

    for seg in dir_parts:
        seg_low = seg.lower()
        if seg_low in yasakli_kume or seg_low.startswith("com.unity."):
            return True
        if root_dir and seg_low.startswith(".") and len(seg_low) > 1 and seg_low not in {".", ".."}:
            return True

    fname = os.path.basename(norm)
    fname_low = fname.lower()
    if fname_low.endswith(ATLANACAK_SONEKLER):
        return True
    if strict_filenames and fname_low in ATLANACAK_DOSYALAR:
        return True

    check_parts = rel_parts if root_dir else norm.split(os.sep)
    lowered_parts = [p.lower() for p in check_parts]
    if "packages" in lowered_parts:
        pkg_idx = len(lowered_parts) - 1 - lowered_parts[::-1].index("packages")
        if pkg_idx == len(lowered_parts) - 2:
            if fname_low != "manifest.json":
                return True
        elif pkg_idx < len(lowered_parts) - 2:
            return True

    return False

def _metin_veya_kod_oku(dosya_yolu: str) -> str:
    """Metin ve kod dosyalarını Türkçe Windows (CP1254) ve UTF-8 uyumlu okur."""
    kodlamalar = ["utf-8", "utf-8-sig", "cp1254", "iso-8859-9", "latin-1"]
    for enc in kodlamalar:
        try:
            with open(dosya_yolu, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return f"[Okuma Hatası: {e}]"
    
    with open(dosya_yolu, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def _pdf_oku(dosya_yolu: str) -> str:
    """PDF belgelerini sayfa sayfa ayıklayarak okur."""
    try:
        reader = PdfReader(dosya_yolu)
        toplam_sayfa = len(reader.pages)
        sayfalar = []
        for i, sayfa in enumerate(reader.pages):
            metin = sayfa.extract_text() or ""
            if metin.strip():
                sayfalar.append(f"--- [Sayfa {i+1} / {toplam_sayfa}] ---\n{metin.strip()}")
        
        if not sayfalar:
            return "[PDF içeriğinde metin bulunamadı (Taranmış görsel belge olabilir).]"
        return "\n\n".join(sayfalar)
    except Exception as e:
        return f"[PDF Okuma Hatası: {e}]"

def _docx_oku(dosya_yolu: str) -> str:
    """Microsoft Word (.docx) belgelerinin metin içeriğini XML üzerinden doğrudan okur."""
    try:
        with zipfile.ZipFile(dosya_yolu, 'r') as zf:
            if "word/document.xml" not in zf.namelist():
                return "[DOCX: word/document.xml bulunamadı.]"
            xml_data = zf.read("word/document.xml")
            tree = ET.fromstring(xml_data)
            
            paragraflar = []
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            for p in tree.iter(f"{{{ns['w']}}}p"):
                texts = [t.text for t in p.iter(f"{{{ns['w']}}}t") if t.text]
                if texts:
                    paragraflar.append("".join(texts))
            
            return "\n\n".join(paragraflar) if paragraflar else "[DOCX belgesi boş.]"
    except Exception as e:
        return f"[DOCX Okuma Hatası: {e}]"

def _xlsx_oku(dosya_yolu: str) -> str:
    """Microsoft Excel (.xlsx) tablolarını Markdown formatında çıkarır."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(dosya_yolu, data_only=True)
        tablolar = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            satirlar = []
            for row in ws.iter_rows(values_only=True):
                if any(c is not None for c in row):
                    satirlar.append(" | ".join([str(c) if c is not None else "" for c in row]))
            if satirlar:
                tablolar.append(f"### Sayfa: {sheet}\n" + "\n".join(satirlar[:150]))
        return "\n\n".join(tablolar) if tablolar else "[Excel tablosunda veri bulunamadı.]"
    except Exception as e:
        return f"[Excel Okuma Hatası: {e}]"

def _gorsel_oku(dosya_yolu: str) -> str:
    """Görseli Gemini Multimodal Vision motoru ile analiz eder ve teknik şartname çıkarır."""
    try:
        return gemini_service.analyze_image(dosya_yolu)
    except Exception as e:
        return f"[Görsel Analiz Hatası: {e}]"

def dosyayi_oku(dosya_yolu: str) -> dict:
    """
    Tek bir dosyanın içeriğini türüne göre güvenli ve zenginleştirilmiş şekilde okur.
    Kod, PDF, DOCX, XLSX ve Görselleri (Gemini Vision) destekler.
    """
    if not os.path.exists(dosya_yolu):
        return {"hata": "Dosya bulunamadı", "dosya_adi": os.path.basename(dosya_yolu), "tur": "HATA", "icerik": ""}

    if os.path.isdir(dosya_yolu):
        return {
            "dosya_adi": os.path.basename(dosya_yolu),
            "tur": "KLASOR",
            "icerik": kaynaklari_tara_ve_birlestir([dosya_yolu])
        }

    dosya_adi = os.path.basename(dosya_yolu)
    uzanti = os.path.splitext(dosya_adi)[1].lower()

    try:
        if uzanti in KOD_METIN_UZANTILARI:
            icerik = _metin_veya_kod_oku(dosya_yolu)
            return {"dosya_adi": dosya_adi, "tur": "KOD_METIN", "icerik": icerik}

        elif uzanti == ".pdf":
            icerik = _pdf_oku(dosya_yolu)
            return {"dosya_adi": dosya_adi, "tur": "PDF_BELGESI", "icerik": icerik}

        elif uzanti == ".docx":
            icerik = _docx_oku(dosya_yolu)
            return {"dosya_adi": dosya_adi, "tur": "WORD_BELGESI", "icerik": icerik}

        elif uzanti in {".xlsx", ".xls"}:
            icerik = _xlsx_oku(dosya_yolu)
            return {"dosya_adi": dosya_adi, "tur": "EXCEL_TABLOSU", "icerik": icerik}

        elif uzanti in GORSEL_UZANTILARI:
            icerik = _gorsel_oku(dosya_yolu)
            return {"dosya_adi": dosya_adi, "tur": "GORSEL_ANALIZ", "icerik": icerik}

        icerik = _metin_veya_kod_oku(dosya_yolu)
        return {"dosya_adi": dosya_adi, "tur": "METIN", "icerik": icerik}

    except Exception as e:
        return {"dosya_adi": dosya_adi, "tur": "HATA", "icerik": f"[Okuma Hatası: {e}]"}

def klasoru_tara(klasor_yolu: str) -> List[str]:
    """
    Belirtilen klasörü gereksiz önbellek/araç/Unity hazır eklenti dizinlerini atlayarak özyinelemeli (recursive) tarar.
    Desteklenen tüm kod, doküman ve görsel dosyalarının tam yollarını döndürür.
    """
    if not os.path.isdir(klasor_yolu):
        return []

    dosya_yollari = []
    tum_desteklenen = KOD_METIN_UZANTILARI | GORSEL_UZANTILARI | BELGE_UZANTILARI

    for kok, dizinler, dosyalar in os.walk(klasor_yolu):
        dizinler[:] = sorted(
            d for d in dizinler
            if not _should_skip_dir(d, kok, klasor_yolu)
        )
        for f in sorted(dosyalar):
            if f.startswith(".") and f not in {".env", ".gitignore"}:
                continue
            uzanti = os.path.splitext(f)[1].lower()
            if uzanti not in tum_desteklenen:
                continue
            tam_yol = os.path.join(kok, f)
            if is_excluded_path(tam_yol, root_dir=klasor_yolu, strict_filenames=True):
                continue
            dosya_yollari.append(tam_yol)

    return dosya_yollari


def _resolve_cache_path(cache_path: Optional[str] = None) -> str:
    if cache_path:
        return cache_path
    env_p = os.getenv("LASEF_ASSET_CACHE_PATH", "").strip()
    return env_p if env_p else _DEFAULT_ASSET_CACHE_PATH


def _dosya_sha256(dosya_yolu: str) -> str:
    h = hashlib.sha256()
    with open(dosya_yolu, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_asset_cache(cache_path: Optional[str] = None) -> Dict[str, Any]:
    path = _resolve_cache_path(cache_path)
    with _ASSET_CACHE_LOCK:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _save_asset_cache(data: Dict[str, Any], cache_path: Optional[str] = None) -> None:
    path = _resolve_cache_path(cache_path)
    with _ASSET_CACHE_LOCK:
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def _is_valid_vision_text(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith(("[HATA", "[Gemini", "[API", "[Görsel okunamadı"))


def _gorsel_meta_hizli(dosya_yolu: str) -> Tuple[int, int, float]:
    """Piksel decode etmeden PIL header üzerinden hızlı (en, boy, KB) bilgisini okur."""
    kb = 0.0
    try:
        kb = round(os.path.getsize(dosya_yolu) / 1024.0, 1)
    except OSError:
        pass
    w, h = 0, 0
    try:
        from PIL import Image
        with Image.open(dosya_yolu) as im:
            w, h = im.size
    except Exception:
        pass
    return w, h, kb


def _varyant_grubu_anahtari(rel_path: str) -> Tuple[str, str]:
    """
    Aynı ikonun DPI (@2x/@3x/@4x) ve koyu tema (d_ / d-) varyantlarını
    tek manifest satırında gruplamak için (grup_anahtari, varyant_etiketi) üretir.
    """
    norm = rel_path.replace("\\", "/")
    folder = os.path.dirname(norm)
    fname = os.path.basename(norm)
    stem, ext = os.path.splitext(fname)

    tags = []
    dpi_m = re.search(r"(@\d+x)$", stem, flags=re.IGNORECASE)
    if dpi_m:
        tags.append(dpi_m.group(1).lower())
        stem = stem[:dpi_m.start()]

    if re.match(r"^d[_-]", stem):
        tags.append("dark")
        stem = stem[2:]

    base_rel = f"{folder}/{stem}{ext}" if folder else f"{stem}{ext}"
    variant_label = "+".join(tags) if tags else "base"
    return base_rel, variant_label


def inspect_image_with_cache(
    dosya_yolu: str,
    detailed: bool = False,
    cache_path: Optional[str] = None
) -> str:
    """
    Görseli SHA-256 hash önbelleğini kontrol ederek (gerekirse Gemini Vision ile) analiz eder.
    İkon/asset incelemeleri için varsayılan olarak yoğun (compact) özet üretir; detailed=True ise tam mimari analiz döner.
    """
    if not dosya_yolu or not os.path.exists(dosya_yolu):
        return f"[HATA: Görsel bulunamadı ({dosya_yolu})]"

    w, h, kb = _gorsel_meta_hizli(dosya_yolu)
    try:
        sha = _dosya_sha256(dosya_yolu)
    except Exception:
        sha = ""

    cache = _load_asset_cache(cache_path) if sha else {}
    entry = cache.get(sha, {}) if sha else {}

    if detailed:
        cached = entry.get("detailed")
    else:
        cached = entry.get("compact") or entry.get("detailed")

    if cached:
        return f"[Önbellek · {w}x{h}, {kb} KB] {cached}"

    try:
        from infrastructure.gemini_client import gemini_service
        analiz = gemini_service.analyze_image(dosya_yolu, compact=not detailed)
    except Exception as e:
        return f"[Görsel okunamadı ({os.path.basename(dosya_yolu)}): {e}]"

    if sha and _is_valid_vision_text(analiz):
        key_field = "detailed" if detailed else "compact"
        new_entry = dict(entry)
        new_entry[key_field] = analiz
        new_entry["name"] = os.path.basename(dosya_yolu)
        new_entry["size"] = f"{w}x{h}"
        new_entry["kb"] = kb
        cache[sha] = new_entry
        _save_asset_cache(cache, cache_path)

    return f"[{w}x{h}, {kb} KB] {analiz}"


def gorsel_manifesti_olustur(
    gorsel_ogeleri: List[Dict[str, Any]],
    cache_path: Optional[str] = None,
    max_entries: int = 120
) -> str:
    """
    Proje klasöründeki görseller/ikonlar için sıfır-API-maliyetli (veya önbellek/opsiyonel grid destekli)
    hafif asset envanteri üretir. @2x/@3x ve d_ tema varyantlarını tek satırda gruplar.
    """
    if not gorsel_ogeleri:
        return ""

    cache = _load_asset_cache(cache_path)
    eager_grid = os.getenv("LASEF_EAGER_VISION_GRID", "").strip() == "1"

    gruplar: Dict[str, Dict[str, Any]] = {}
    uncached_rep_paths: List[Tuple[str, str, str]] = []

    for item in gorsel_ogeleri:
        abs_p = item["abs_path"]
        rel_p = item.get("rel_path") or os.path.basename(abs_p)
        w, h, kb = _gorsel_meta_hizli(abs_p)
        try:
            sha = _dosya_sha256(abs_p)
        except Exception:
            sha = ""

        base_rel, v_tag = _varyant_grubu_anahtari(rel_p)
        grp = gruplar.setdefault(base_rel, {
            "rep_abs": abs_p,
            "rep_rel": rel_p,
            "w": w,
            "h": h,
            "kb": kb,
            "variants": [],
            "sha": sha,
            "desc": ""
        })

        if v_tag == "base":
            grp["rep_abs"] = abs_p
            grp["rep_rel"] = rel_p
            grp["w"] = w
            grp["h"] = h
            grp["kb"] = kb
            grp["sha"] = sha
        else:
            if v_tag not in grp["variants"]:
                grp["variants"].append(v_tag)

        if sha and sha in cache and not grp["desc"]:
            grp["desc"] = cache[sha].get("compact") or cache[sha].get("detailed") or ""

    if eager_grid:
        for g_key, grp in gruplar.items():
            if not grp["desc"] and grp["rep_abs"]:
                uncached_rep_paths.append((g_key, grp["rep_abs"], grp["sha"]))

        if uncached_rep_paths:
            try:
                from infrastructure.gemini_client import gemini_service
                grid_res = gemini_service.analyze_images_grid([p for _, p, _ in uncached_rep_paths])
                cache_dirty = False
                for g_key, rep_abs, sha in uncached_rep_paths:
                    desc = grid_res.get(rep_abs, "")
                    if _is_valid_vision_text(desc):
                        gruplar[g_key]["desc"] = desc
                        if sha:
                            ent = dict(cache.get(sha, {}))
                            ent["compact"] = desc
                            ent["name"] = os.path.basename(rep_abs)
                            cache[sha] = ent
                            cache_dirty = True
                if cache_dirty:
                    _save_asset_cache(cache, cache_path)
            except Exception:
                pass

    lines = [
        f"Toplam {len(gorsel_ogeleri)} görsel dosyası ({len(gruplar)} benzersiz ikon/varlık grubu).",
        "Not: Önemli gördüğün herhangi bir ikonu/varlığı incelemek için `inspect_image` veya aramak için `search_assets` aracını dosya yoluyla çağırabilirsin."
    ]
    sorted_keys = sorted(gruplar.keys())
    for g_key in sorted_keys[:max_entries]:
        grp = gruplar[g_key]
        v_str = f" [varyantlar: {', '.join(sorted(grp['variants']))}]" if grp["variants"] else ""
        desc_str = f" -> {grp['desc']}" if grp["desc"] else ""
        lines.append(
            f"• {grp['rep_rel']} ({grp['w']}x{grp['h']}, {grp['kb']} KB){v_str}{desc_str}"
        )

    if len(sorted_keys) > max_entries:
        lines.append(f"... ve {len(sorted_keys) - max_entries} ek görsel grubu (`search_assets` ile aranabilir).")

    return "\n".join(lines)


def search_asset_manifest(
    hedef_kaynaklar: Any,
    query: str = "",
    limit: int = 40,
    cache_path: Optional[str] = None
) -> str:
    """Klasör veya kaynak listesi içindeki görsel/ikon varlıklarını isim, yol ve (varsa) önbellek açıklamasına göre arar."""
    if isinstance(hedef_kaynaklar, str):
        kaynak_listesi = [hedef_kaynaklar]
    elif isinstance(hedef_kaynaklar, (list, tuple, set)):
        kaynak_listesi = list(hedef_kaynaklar)
    else:
        return "[HATA: Geçersiz kaynak parametresi.]"

    gorseller = []
    gorulen = set()
    for k in kaynak_listesi:
        if not k:
            continue
        k_abs = os.path.abspath(k)
        if os.path.isdir(k_abs):
            for p in klasoru_tara(k_abs):
                if os.path.splitext(p)[1].lower() in GORSEL_UZANTILARI and p not in gorulen:
                    gorulen.add(p)
                    rel = os.path.relpath(p, k_abs).replace("\\", "/")
                    gorseller.append({"abs_path": p, "rel_path": rel})
        elif os.path.isfile(k_abs) and os.path.splitext(k_abs)[1].lower() in GORSEL_UZANTILARI:
            if k_abs not in gorulen and not is_excluded_path(k_abs, strict_filenames=False):
                gorulen.add(k_abs)
                gorseller.append({"abs_path": k_abs, "rel_path": os.path.basename(k_abs)})

    q = (query or "").strip().lower()
    cache = _load_asset_cache(cache_path)
    eslesenler = []
    for item in gorseller:
        rel_p = item["rel_path"]
        abs_p = item["abs_path"]
        desc = ""
        try:
            sha = _dosya_sha256(abs_p)
            if sha in cache:
                desc = cache[sha].get("compact") or cache[sha].get("detailed") or ""
        except Exception:
            pass
        if not q or q in rel_p.lower() or (desc and q in desc.lower()):
            w, h, kb = _gorsel_meta_hizli(abs_p)
            desc_part = f" -> {desc}" if desc else ""
            eslesenler.append(f"• {rel_p} ({w}x{h}, {kb} KB) [tam yol: {abs_p}]{desc_part}")

    if not eslesenler:
        return f"'{query}' sorgusuyla eşleşen proje görseli bulunamadı (taranan görsel: {len(gorseller)})."

    gosterilen = eslesenler[:max(1, int(limit))]
    baslik = f"Bulunan görsel/ikon varlıkları ({len(eslesenler)} eşleşme, gösterilen {len(gosterilen)}):"
    return baslik + "\n" + "\n".join(gosterilen)


def _sure_formatla(saniye: float) -> str:
    s = max(0, int(round(saniye)))
    if s < 60:
        return f"{s}sn"
    dk, sn = divmod(s, 60)
    if dk < 60:
        return f"{dk}dk {sn:02d}sn"
    sa, dk = divmod(dk, 60)
    return f"{sa}sa {dk:02d}dk"


def _yayinla_tarama_ilerlemesi(
    done_w: float,
    total_w: float,
    done_items: int,
    total_items: int,
    current_file: str,
    eta_text: str,
    avg_s: float,
    stage_text: str,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> None:
    ratio = min(1.0, max(0.0, done_w / total_w)) if total_w > 0 else 1.0
    percent = round(ratio * 100.0, 1)
    payload = {
        "done_weight": round(done_w, 2),
        "total_weight": round(total_w, 2),
        "ratio": ratio,
        "percent": percent,
        "done_items": done_items,
        "total_items": total_items,
        "current_file": current_file,
        "eta_text": eta_text,
        "avg_per_item_s": round(avg_s, 2),
        "stage_text": stage_text,
    }
    if progress_callback:
        try:
            progress_callback(payload)
        except Exception:
            pass
    try:
        from core.event_bus import event_bus, EVENT_SCAN_PROGRESS
        event_bus.publish(EVENT_SCAN_PROGRESS, "file_reader", payload)
    except Exception:
        pass


def kaynaklari_tara_ve_birlestir(
    kaynaklar: list,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> str:
    """
    Kullanıcının yüklediği tüm kaynakları (klasörler, belgeler, fotoğraflar ve kodlar)
    derler, Unity/araç önbelleklerini temizleyip türlerine göre önceliklendirir:
    1. Kod & Scriptler -> 2. Belgeler -> 3. Tekil Görsel Analizleri -> 4. Hafif Asset Manifesti.
    """
    if not kaynaklar:
        return ""

    hedef_ogeler: List[Dict[str, Any]] = []
    gorulenler = set()

    for k in kaynaklar:
        if not k:
            continue
        k_abs = os.path.abspath(k)
        if os.path.isdir(k_abs):
            alt_dosyalar = klasoru_tara(k_abs)
            for d in alt_dosyalar:
                norm_d = os.path.normpath(d)
                if norm_d not in gorulenler:
                    gorulenler.add(norm_d)
                    ext = os.path.splitext(d)[1].lower()
                    rel = os.path.relpath(d, k_abs).replace("\\", "/")
                    if ext in GORSEL_UZANTILARI:
                        w = 0.5
                    elif ext in BELGE_UZANTILARI:
                        w = 5.0
                    else:
                        w = 1.0
                    hedef_ogeler.append({
                        "abs_path": d,
                        "rel_path": rel,
                        "explicit": False,
                        "ext": ext,
                        "weight": w
                    })
        elif os.path.isfile(k_abs):
            norm_f = os.path.normpath(k_abs)
            if norm_f not in gorulenler and not is_excluded_path(k_abs, strict_filenames=False):
                gorulenler.add(norm_f)
                ext = os.path.splitext(k_abs)[1].lower()
                if ext in GORSEL_UZANTILARI:
                    w = 100.0
                elif ext in BELGE_UZANTILARI:
                    w = 5.0
                else:
                    w = 1.0
                hedef_ogeler.append({
                    "abs_path": k_abs,
                    "rel_path": os.path.basename(k_abs),
                    "explicit": True,
                    "ext": ext,
                    "weight": w
                })

    if not hedef_ogeler:
        return ""

    total_items = len(hedef_ogeler)
    total_weight = sum(o["weight"] for o in hedef_ogeler) or float(total_items)
    print(f"\n📂 [Kaynak Dosya İşleyici]: Toplam {total_items} filtrelenmiş kaynak işleniyor (ağırlık: {int(round(total_weight))})...")

    kod_dosyalari: List[Dict[str, Any]] = []
    belge_dosyalari: List[Dict[str, Any]] = []
    tekil_gorsel_dosyalari: List[Dict[str, Any]] = []
    manifest_gorselleri: List[Dict[str, Any]] = []

    done_weight = 0.0
    baslangic_t = time.perf_counter()
    son_yazdirma_t = baslangic_t
    ema_sn_per_weight: Optional[float] = None

    _yayinla_tarama_ilerlemesi(
        0.0, total_weight, 0, total_items, "", "Başlıyor...", 0.0,
        f"Kaynak taraması başlatıldı ({total_items} dosya)", progress_callback
    )

    for idx, oge in enumerate(hedef_ogeler, 1):
        dosya_yolu = oge["abs_path"]
        rel_yolu = oge["rel_path"]
        ext = oge["ext"]
        w = oge["weight"]
        t0 = time.perf_counter()

        if ext in GORSEL_UZANTILARI and not oge["explicit"]:
            manifest_gorselleri.append(oge)
        elif ext in GORSEL_UZANTILARI and oge["explicit"]:
            analiz_metni = inspect_image_with_cache(dosya_yolu, detailed=True)
            tekil_gorsel_dosyalari.append({
                "dosya_adi": rel_yolu,
                "tur": "GORSEL_ANALIZ",
                "icerik": analiz_metni
            })
        else:
            bilgi = dosyayi_oku(dosya_yolu)
            bilgi["rel_path"] = rel_yolu
            tur = bilgi.get("tur", "METIN")
            if tur in ["PDF_BELGESI", "WORD_BELGESI", "EXCEL_TABLOSU"]:
                belge_dosyalari.append(bilgi)
            else:
                kod_dosyalari.append(bilgi)

        dt = max(0.001, time.perf_counter() - t0)
        done_weight += w
        anlik_oran = dt / max(0.25, w)
        if ema_sn_per_weight is None:
            ema_sn_per_weight = anlik_oran
        else:
            ema_sn_per_weight = 0.35 * anlik_oran + 0.65 * ema_sn_per_weight

        kalan_w = max(0.0, total_weight - done_weight)
        kalan_sn = kalan_w * (ema_sn_per_weight or 0.0)
        eta_text = "Tamamlandı" if idx == total_items else f"~{_sure_formatla(kalan_sn)}"
        gecen_ort = (time.perf_counter() - baslangic_t) / idx
        pct = min(100.0, round((done_weight / total_weight) * 100.0, 1))
        stage_note = f"[{idx}/{total_items} · %{pct:.0f} · Kalan: {eta_text}] {os.path.basename(rel_yolu)}"

        simdi = time.perf_counter()
        if idx == total_items or total_items <= 25 or (oge["explicit"] and ext in GORSEL_UZANTILARI) or (simdi - son_yazdirma_t) >= 0.8:
            print(f"   ⏱️ [{idx}/{total_items} · %{pct:.1f} · Ort: {gecen_ort:.2f}s · Kalan: {eta_text}] {rel_yolu}")
            son_yazdirma_t = simdi
            _yayinla_tarama_ilerlemesi(
                done_weight, total_weight, idx, total_items, rel_yolu, eta_text, gecen_ort,
                stage_note, progress_callback
            )

    def _kod_oncelik_anahtari(b: Dict[str, Any]) -> Tuple[int, str]:
        rp = (b.get("rel_path") or b.get("dosya_adi") or "").replace("\\", "/").lower()
        ext_b = os.path.splitext(rp)[1]
        if rp.startswith("assets/scripts/") and ext_b == ".cs":
            return (0, rp)
        if ext_b in {".cs", ".shader", ".cginc", ".compute", ".py", ".js", ".ts"}:
            return (1, rp)
        return (2, rp)

    kod_dosyalari.sort(key=_kod_oncelik_anahtari)

    manifest_metni = gorsel_manifesti_olustur(manifest_gorselleri) if manifest_gorselleri else ""

    parcalar = [
        "═" * 65,
        f"📦 YÜKLENEN REFERANS KAYNAKLAR VE KOD BAĞLAMI ({total_items} Dosya):",
        f"• 💻 Kaynak Kodlar & Scriptler: {len(kod_dosyalari)} adet",
        f"• 📑 Belgeler ve Tablolar (PDF/Word/Excel): {len(belge_dosyalari)} adet",
        f"• 🎨 Tekil Eklenen Görseller (Gemini Vision): {len(tekil_gorsel_dosyalari)} adet",
        f"• 🗂️ Klasör İkon/Görsel Envanteri (Talep Üzerine İncelenir): {len(manifest_gorselleri)} adet",
        "═" * 65
    ]

    if kod_dosyalari:
        parcalar.append("\n💻 ════════ [1. KAYNAK KODLAR & SCRIPTLER] ════════")
        for b in kod_dosyalari:
            gosterim_adi = b.get("rel_path") or b.get("dosya_adi")
            icerik_metin = b.get("icerik", "")
            if len(icerik_metin) > 15000:
                icerik_metin = icerik_metin[:15000] + f"\n... [Kalan {len(b.get('icerik', '')) - 15000} karakter atlandı]"
            parcalar.append(f"\n📁 [{gosterim_adi}] (Tür: {b.get('tur')}):\n\"\"\"\n{icerik_metin}\n\"\"\"")

    if belge_dosyalari:
        parcalar.append("\n📑 ════════ [2. DOKÜMANLAR & TABLOLAR (PDF / DOCX / EXCEL)] ════════")
        for b in belge_dosyalari:
            gosterim_adi = b.get("rel_path") or b.get("dosya_adi")
            parcalar.append(f"\n📄 [{gosterim_adi}] (Tür: {b.get('tur')}):\n\"\"\"\n{b.get('icerik')}\n\"\"\"")

    if tekil_gorsel_dosyalari:
        parcalar.append("\n🎨 ════════ [3. EKLENEN GÖRSELLER (GEMINI VISION ANALİZİ)] ════════")
        for b in tekil_gorsel_dosyalari:
            parcalar.append(f"\n🖼️ [{b.get('dosya_adi')}] (Tür: {b.get('tur')}):\n\"\"\"\n{b.get('icerik')}\n\"\"\"")

    if manifest_metni:
        parcalar.append("\n🗂️ ════════ [4. PROJE GÖRSEL / İKON ENVANTERİ (HAFİF MANİFEST)] ════════")
        parcalar.append(manifest_metni)

    parcalar.append("\n" + "═" * 65)
    return "\n".join(parcalar)


def toplu_dosyalari_birlestir(dosya_yollari: list) -> str:
    return kaynaklari_tara_ve_birlestir(dosya_yollari)

def klasoru_tara_ve_birlestir(klasor_yolu: str) -> str:
    return kaynaklari_tara_ve_birlestir([klasor_yolu])
