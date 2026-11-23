import os
import re
import subprocess
from tools.file_system_tools import tool_run_command

def otonom_dogrula_ve_test_et(hedef_klasor: str, uretilen_dosyalar: dict) -> dict:
    """
    🧪 OTONOM TEST & SAĞLIK DENETİMİ (Self-Healing Compiler):
    Üretilen kodların sözdizimini ve çalışabilirliğini yerel ortamda test eder.
    """
    print("\n🧪 [Otonom Test Motoru] Üretilen kodlar yerel ortamda test ediliyor...")
    test_raporu = {"basarili": True, "detaylar": []}

    py_dosyalar = [f for f in uretilen_dosyalar.keys() if f.lower().endswith(".py")]
    for p in py_dosyalar:
        tam_yol = os.path.join(hedef_klasor, p)
        if os.path.exists(tam_yol):
            res = tool_run_command(f"python -m py_compile \"{tam_yol}\"")
            if "Error" in res or "Traceback" in res:
                print(f"   ❌ [Syntax Hatası Tespit Edildi]: {p}")
                test_raporu["basarili"] = False
                test_raporu["detaylar"].append(f"Python Sözdizim Hatası: {p} -> {res}")
            else:
                print(f"   🟢 [Syntax OK]: {p}")

    js_dosyalar = [f for f in uretilen_dosyalar.keys() if f.lower().endswith(".js")]
    for j in js_dosyalar:
        tam_yol = os.path.join(hedef_klasor, j)
        if os.path.exists(tam_yol):
            with open(tam_yol, "r", encoding="utf-8", errors="replace") as f:
                c = f.read()
            guncel_c = c
            if guncel_c.startswith("```") or "```" in guncel_c:
                guncel_c = re.sub(r"^```[a-zA-Z0-9_\-]*\s*\n?", "", guncel_c)
                guncel_c = re.sub(r"\n?```\s*$", "", guncel_c).strip()
                with open(tam_yol, "w", encoding="utf-8") as f:
                    f.write(guncel_c)
                print(f"   🩹 [Otomatik İyileştirildi]: {j} dosyasındaki kaçak markdown blokları temizlendi.")
            
            if guncel_c.count("{") != guncel_c.count("}"):
                print(f"   ⚠️ [JS Parantez Uyarısı]: {j} süslü parantez sayısı uyuşmuyor.")
            else:
                print(f"   🟢 [JS Bütünlüğü Doğrulandı]: {j} ({len(guncel_c) / 1024:.1f} KB)")

    html_dosyalar = [f for f in uretilen_dosyalar.keys() if f.lower().endswith(".html")]
    for h in html_dosyalar:
        tam_yol = os.path.join(hedef_klasor, h)
        if os.path.exists(tam_yol):
            with open(tam_yol, "r", encoding="utf-8", errors="replace") as f:
                c = f.read()

            hatalar = []
            if "<html" not in c.lower() or "</html>" not in c.lower():
                hatalar.append("HTML kök etiketleri eksik")
            is_game_file = (h.lower() == "index.html" or "game" in h.lower() or "oyun" in h.lower())
            has_game_ui = ("<canvas" in c.lower() or "grid" in c.lower() or "board" in c.lower() or "<table" in c.lower() or "cell" in c.lower() or "<button" in c.lower())
            if is_game_file and not has_game_ui:
                hatalar.append("Oyun etkileşim alanı (<canvas>, grid, board veya table) bulunamadı")
            if "<script" in c.lower() and "</script>" not in c.lower():
                hatalar.append("<script> blokları eksik veya kapanmamış")
            
            script_icerikleri = []
            for match in re.finditer(r"<script[^>]*>(.*?)</script>", c, re.DOTALL | re.IGNORECASE):
                script_icerikleri.append(match.group(1))

            js_kodu = "\n".join(script_icerikleri)
            if js_kodu:
                if js_kodu.count("{") != js_kodu.count("}"):
                    hatalar.append(f"JS parantez uyuşmazlığı: '{{' ({js_kodu.count('{')}) != '}}' ({js_kodu.count('}')})")
                if js_kodu.count("(") != js_kodu.count(")"):
                    hatalar.append(f"JS parantez uyuşmazlığı: '(' ({js_kodu.count('(')}) != ')' ({js_kodu.count(')')})")
                if "audiocontext" in js_kodu.lower():
                    print(f"   🔊 [Web Audio Entegrasyonu Doğrulandı]: {h}")

            if not hatalar:
                print(f"   🟢 [HTML/DOM/JS Sağlığı Mükemmel]: {h} ({len(c) / 1024:.1f} KB)")
            else:
                print(f"   ❌ [HTML Bütünlük Kusurları ({h})]: {', '.join(hatalar)}")
                test_raporu["basarili"] = False
                test_raporu["detaylar"].append(f"HTML/DOM Hatası ({h}): {', '.join(hatalar)}")

    cs_dosyalar = [f for f in uretilen_dosyalar.keys() if f.lower().endswith(".cs")]
    for cs in cs_dosyalar:
        basit_ad = os.path.basename(cs)
        sinif_adi = os.path.splitext(basit_ad)[0]
        aday_yollar = [
            os.path.join(hedef_klasor, cs.replace("/", os.sep)),
            os.path.join(hedef_klasor, "Assets", "Editor", basit_ad),
            os.path.join(hedef_klasor, "Assets", "Scripts", basit_ad),
        ]
        tam_yol = next((p for p in aday_yollar if os.path.exists(p)), aday_yollar[0])
        if os.path.exists(tam_yol):
            with open(tam_yol, "r", encoding="utf-8", errors="replace") as f:
                c = f.read()

            onarma_yapildi = False
            if "```" in c or c.strip().lower().startswith(("here's", "sure", "now let me", "thinking", "analyze")):
                from agents.council_engine import _saf_kod_ayir
                temiz_c = _saf_kod_ayir(c, cs)
                if temiz_c and len(temiz_c) > 100:
                    c = temiz_c
                    onarma_yapildi = True
                    print(f"   🩹 [C# Otonom Onarım]: {cs} dosyasındaki sohbet/markdown kalıntıları temizlendi.")

            if re.search(r"class\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)\s*[:{]", c):
                c = re.sub(r"class\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)(\s*[:{])", r"class \1\2\3", c)
                c = re.sub(r"<UI\s+Canvas>", "<UICanvas>", c)
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} dosyasındaki boşluklu sınıf adı birleştirildi.")

            if "[ReadOnly" in c or "ReadOnlyAttribute" in c:
                c = re.sub(r'\[\s*ReadOnly(?:Attribute)?\s*,\s*', '[', c)
                c = re.sub(r',\s*ReadOnly(?:Attribute)?\s*\]', ']', c)
                c = re.sub(r'\[\s*ReadOnly(?:Attribute)?\s*\]\s*', '', c)
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} dosyasındaki dahili olmayan [ReadOnly] attribute'u temizlendi.")

            ui_tipleri = ("CanvasScaler", "GraphicRaycaster", "RawImage", "Image", "Button", "Slider")
            if any(re.search(rf"\b{t}\b", c) for t in ui_tipleri) and "using UnityEngine.UI;" not in c:
                if c.lstrip().startswith("#if UNITY_EDITOR"):
                    c = re.sub(r"^(\s*#if\s+UNITY_EDITOR\s*\n)", r"\1using UnityEngine.UI;\n", c, count=1)
                else:
                    c = "using UnityEngine.UI;\n" + c
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} dosyasına eksik 'using UnityEngine.UI;' eklendi.")

            if "AddComponent<Collider>()" in c:
                c = c.replace("AddComponent<Collider>()", "AddComponent<CapsuleCollider>()")
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} içindeki soyut AddComponent<Collider>() -> AddComponent<CapsuleCollider>() olarak düzeltildi.")

            if "FindObjectOfType<" in c:
                c = re.sub(r"\bFindObjectOfType<([^>]+)>\(\)", r"UnityEngine.Object.FindFirstObjectByType<\1>()", c)
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} içindeki eski FindObjectOfType çağrıları FindFirstObjectByType ile güncellendi.")

            if "FindObjectsOfType<" in c:
                c = re.sub(r"\bFindObjectsOfType<([^>]+)>\(\)", r"UnityEngine.Object.FindObjectsByType<\1>(FindObjectsSortMode.None)", c)
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} içindeki eski FindObjectsOfType çağrıları FindObjectsByType ile güncellendi.")

            if '"Arial.ttf"' in c:
                c = c.replace('"Arial.ttf"', '"LegacyRuntime.ttf"')
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} içindeki eski 'Arial.ttf' fontu Unity 6 uyumlu 'LegacyRuntime.ttf' ile değiştirildi.")

            if "agent.ResetPath();" in c and "agent.isOnNavMesh" not in c.split("agent.ResetPath();")[0][-120:]:
                c = c.replace(
                    "if (useNavMeshAgent && agent != null)\n        {\n            agent.ResetPath();\n        }",
                    "if (useNavMeshAgent && agent != null && agent.isActiveAndEnabled && agent.isOnNavMesh)\n        {\n            agent.ResetPath();\n        }"
                )
                c = re.sub(
                    r"(?<!isOnNavMesh\)\s)\bagent\.ResetPath\(\);",
                    "if (agent != null && agent.isActiveAndEnabled && agent.isOnNavMesh) agent.ResetPath();",
                    c
                )
                onarma_yapildi = True
                print(f"   🩹 [C# Otonom Onarım]: {cs} içindeki NavMeshAgent.ResetPath() çağrısına isOnNavMesh güvenlik koruması eklendi.")

            if onarma_yapildi:
                with open(tam_yol, "w", encoding="utf-8") as f:
                    f.write(c)
                uretilen_dosyalar[cs] = c

            if f"class {sinif_adi}" in c or f"interface {sinif_adi}" in c or f"enum {sinif_adi}" in c or f"struct {sinif_adi}" in c:
                print(f"   🟢 [C# Sınıf/Dosya Eşleşmesi OK]: {sinif_adi}.cs ({len(c)/1024:.1f} KB)")
            else:
                print(f"   ⚠️ [Uyarı]: {cs} dosya adı ile içindeki class adı uyuşmuyor olabilir.")

    return test_raporu
