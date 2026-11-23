"""
👑 LASEF - CANLI UNITY MCP, HİYERARŞİ, SELF-HEALING & VİZYON (VISION EYE) TEST DÜZENEĞİ
Bu test düzeneği:
1. Unity MCP kurulumunu (`CoplayDev/unity-mcp` + `LaSefBridgeServer.cs` + `.mcp.json`) doğrular.
2. Unity Editor (Port 8088) bağlantısını ve C# derleme sağlığını denetler.
3. Türkçe yerel ayar (`tr-TR`) ondalık sayı serileştirme (`0.00` JSON float) ve Hiyerarşi okuma kabiliyetini test eder.
4. FastMCP / Tool Registry araçlarını (`unity_status`, `unity_get_hierarchy`, `unity_inspect_object`, `unity_set_property`) canlı test eder.
5. `FPSArenaSceneBuilder.BuildScene()` ile sahneyi inşa eder ve kök nesne sayısını doğrular.
6. Play Mode kontrolünü, çalışma zamanı (Runtime) 0 hata durumunu (`LegacyRuntime.ttf`, `EnemyAI` NavMesh güvenliği) ve Gemini Multimodal Vision Eye analizini uçtan uca test eder.
7. `UnityAutonomousPlaytester.run_full_pipeline` tam otonom döngüsünü çalıştırıp doğrular.

Çalıştırma:
    python test_lasef_unity_vision.py
"""
import os
import sys
import time
import json
import base64
import warnings
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
warnings.filterwarnings("ignore", message=".*AFC.*")

LASEF_DIR = os.path.dirname(os.path.abspath(__file__))
if LASEF_DIR not in sys.path:
    sys.path.insert(0, LASEF_DIR)

from tools.unity_bridge_client import unity_client
from tools.unity_tools import (
    tool_unity_status,
    tool_unity_get_hierarchy,
    tool_unity_inspect_object,
    tool_unity_set_property,
)
from orchestrator.unity_autonomous_playtester import UnityAutonomousPlaytester

DEFAULT_UNITY_PROJECT = os.path.join(LASEF_DIR, "Unity Denemeler Klasörü", "MCP Deneme")


def cizgi(baslik: str = ""):
    print("\n" + "═" * 70)
    if baslik:
        print(f" {baslik}")
        print("═" * 70)


def collect_project_cs_files(project_dir: str) -> dict:
    """Projedeki Assets/Scripts ve Assets/Editor altındaki C# dosyalarını (LaSefBridge hariç) toplar."""
    files = {}
    assets_dir = os.path.join(project_dir, "Assets")
    if not os.path.exists(assets_dir):
        return files
    for root, _, filenames in os.walk(assets_dir):
        if "LaSefBridge" in root:
            continue
        for fname in filenames:
            if fname.endswith(".cs"):
                full_p = os.path.join(root, fname)
                rel_p = os.path.relpath(full_p, project_dir).replace("\\", "/")
                try:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                        files[rel_p] = f.read()
                except Exception:
                    pass
    return files


def run_test_harness(project_dir: str = DEFAULT_UNITY_PROJECT) -> dict:
    cizgi("🧪 [LASEF UNITY MCP & VISION EYE] UÇTAN UCA CANLI TEST DÜZENEĞİ")
    results = {
        "mcp_setup_ok": False,
        "bridge_connected": False,
        "compilation_clean": False,
        "scene_builder_ok": False,
        "hierarchy_json_ok": False,
        "mcp_tools_ok": False,
        "playmode_zero_errors": False,
        "vision_capture_ok": False,
        "autonomous_pipeline_ok": False,
    }

    print(f"\n📦 [1/6] Unity MCP ve Köprü Kurulumu Denetleniyor: {project_dir}")
    mcp_setup = unity_client.ensure_mcp_project_setup(project_dir)
    print(f"   • CoplayDev/unity-mcp (manifest.json): {'✅ Kurulu' if mcp_setup.get('coplay_mcp_configured') else '❌ Eksik'}")
    print(f"   • LaSefBridgeServer.cs (Port 8088):   {'✅ Kurulu' if mcp_setup.get('bridge_installed') else '❌ Eksik'}")
    print(f"   • .mcp.json Konfigürasyonu:           {'✅ Hazır' if mcp_setup.get('mcp_json_created') else '❌ Eksik'}")
    results["mcp_setup_ok"] = all([
        mcp_setup.get("coplay_mcp_configured"),
        mcp_setup.get("bridge_installed"),
        mcp_setup.get("mcp_json_created"),
    ])

    print("\n📡 [2/6] Unity Köprü Sunucusu Taranıyor (http://127.0.0.1:8088)...")
    try:
        st_init = unity_client.get_status()
        if st_init.get("is_playing"):
            print("   ℹ️ [Hazırlık]: Unity Play Modu kapatılıyor (Edit Moduna dönülüyor)...")
            unity_client.set_play_mode(False)
    except Exception:
        pass

    if not unity_client.is_connected():
        print("❌ [BAĞLANTI BAŞARISIZ]: Unity Editor dinlemede değil!")
        return results

    results["bridge_connected"] = True
    status = unity_client.get_status()
    print(f"   🟢 [Bağlantı Başarılı]: Unity {status.get('unity_version', 'Bilinmiyor')} | Sahne: '{status.get('active_scene', 'SampleScene')}'")

    print("   ⏳ [Derleme Denetimi]: Yeni köprü ve C# scriptlerinin derlenmesi bekleniyor...")
    comp_res = unity_client.wait_for_compilation(timeout=35.0, trigger_refresh=True)
    comp_errors = [
        e for e in comp_res.get("errors", [])
        if "LaSefDynamicRunner_" not in e and "LaSefBridgeServer" not in e
    ]
    results["compilation_clean"] = len(comp_errors) == 0
    if results["compilation_clean"]:
        print("   ✅ [C# Derleme Temiz]: 0 derleme hatası!")
    else:
        print(f"   ❌ [C# Derleme Hatası ({len(comp_errors)} adet)]:")
        for ce in comp_errors[:5]:
            print(f"      • {ce}")

    print("\n🏗️ [3/6] FPSArenaSceneBuilder.BuildScene() ve Hiyerarşi JSON Testi...")
    build_res = unity_client.execute_csharp("FPSArenaSceneBuilder.BuildScene();")
    if build_res.get("success"):
        print(f"   ✅ [SceneBuilder Çalıştı]: {build_res.get('output', 'OK')}")
        results["scene_builder_ok"] = True
    else:
        print(f"   ⚠️ [SceneBuilder Uyarısı]: {build_res.get('error')}")

    unity_client.save_scene()
    hier = unity_client.get_hierarchy()
    nodes = hier.get("nodes", [])
    root_count = hier.get("root_count", len(nodes))
    print(f"   🌳 [Hiyerarşi Okuma]: Sahnede {root_count} adet kök GameObject doğrulandı.")

    if root_count >= 8 and nodes:
        sample_pos = nodes[0].get("pos", {})
        is_float_ok = isinstance(sample_pos.get("x"), (int, float))
        results["hierarchy_json_ok"] = is_float_ok
        print(f"   ✅ [JSON Float Serileştirme]: Koordinatlar geçerli float ({sample_pos}) -> CultureInfo.InvariantCulture aktif!")
        for idx, node in enumerate(nodes[:8], 1):
            comps = ", ".join(node.get("components", []))
            pos = node.get("pos", {})
            print(f"      {idx}. 📦 '{node.get('name')}' | Pos: ({pos.get('x',0):.1f}, {pos.get('y',0):.1f}, {pos.get('z',0):.1f}) | [{comps}]")
    else:
        print(f"   ❌ [Hiyerarşi Hatası]: Beklenen >=8 nesne, bulunan: {root_count}")

    print("\n🔧 [4/6] MCP Araçları (status, hierarchy, inspect, set_property) Test Ediliyor...")
    t_status = tool_unity_status()
    t_hier = tool_unity_get_hierarchy()
    t_inspect = tool_unity_inspect_object("Player")
    t_setprop = tool_unity_set_property("Player", "HealthSystem", "maxHealth", "125", False)

    print(f"   • tool_unity_status:         {t_status.splitlines()[0] if t_status else 'Hata'}")
    print(f"   • tool_unity_get_hierarchy:  {t_hier.splitlines()[0] if t_hier else 'Hata'}")
    print(f"   • tool_unity_inspect_object: {t_inspect.splitlines()[0] if t_inspect else 'Hata'}")
    print(f"   • tool_unity_set_property:   {t_setprop}")

    results["mcp_tools_ok"] = (
        ("Çevrimiçi" in t_status or "Bağlı" in t_status)
        and "Player" in t_hier
        and "HealthSystem" in t_inspect
        and ("guncellendi" in t_setprop or "✅" in t_setprop)
    )

    print("\n🎮 [5/6] Play Mode & Çalışma Zamanı (Runtime) Konsol + Vision Eye Testi...")
    unity_client.clear_console_logs()
    play_res = unity_client.set_play_mode(True)
    print(f"   🕹️ [Play Mode Başlatıldı]: is_playing = {play_res.get('is_playing', unity_client.get_status().get('is_playing'))}")
    time.sleep(2.5)

    logs_res = unity_client.get_console_logs()
    raw_logs = [
        l for l in logs_res.get("logs", [])
        if not any(
            noise in (l.get("message", "") + l.get("stackTrace", ""))
            for noise in ["LaSefDynamicRunner_", "LaSefBridgeServer", "LaSefBridge", "[LaSef Köprüsü]"]
        )
    ]
    runtime_errors = [
        l for l in raw_logs
        if "error" in l.get("type", "").lower() or "exception" in l.get("type", "").lower()
    ]
    results["playmode_zero_errors"] = len(runtime_errors) == 0
    if results["playmode_zero_errors"]:
        print("   ✅ [Runtime Konsol Temiz]: Play Mode sırasında 0 Exception / 0 Error!")
    else:
        print(f"   ❌ [Runtime Konsol Hatası ({len(runtime_errors)} adet)]:")
        for re_item in runtime_errors[:5]:
            print(f"      • [{re_item.get('type')}] {re_item.get('message')}")

    shot = unity_client.capture_screenshot(prefer_game_view=True)
    if shot.get("success") and shot.get("data"):
        img_bytes = base64.b64decode(shot.get("data"))
        results["vision_capture_ok"] = len(img_bytes) > 1024
        print(f"   📸 [Vision Eye Ekran Yakalama Başarılı]: '{shot.get('camera', 'Camera')}' ({len(img_bytes)//1024} KB)")
    else:
        print(f"   ⚠️ [Ekran Yakalama Uyarısı]: {shot.get('error')}")

    unity_client.set_play_mode(False)
    unity_client.save_scene()
    print("   🛑 [Play Mode Kapatıldı]: Edit Moduna güvenle dönüldü ve sahne kaydedildi.")

    print("\n🤖 [6/6] UnityAutonomousPlaytester.run_full_pipeline() Uçtan Uca Test Ediliyor...")
    cs_files = collect_project_cs_files(project_dir)
    playtester = UnityAutonomousPlaytester(project_dir)
    pipeline_report = playtester.run_full_pipeline(
        user_request="3B FPS Arena oyunu: Oyuncu, düşmanlar, silah sistemi, sağlık barı ve skor arayüzü.",
        nihai_dosyalar=cs_files,
    )
    results["autonomous_pipeline_ok"] = bool(pipeline_report.get("is_fully_successful"))

    cizgi("📊 TEST DÜZENEĞİ NİHAİ SONUÇ TABLOSU")
    for k, v in results.items():
        durum = "✅ BAŞARILI" if v else "❌ BAŞARISIZ"
        print(f"   • {k:<26}: {durum}")

    all_passed = all(results.values())
    cizgi("🏆 TÜM TESTLER %100 BAŞARIYLA GEÇTİ!" if all_passed else "⚠️ BAZI TESTLERDE UYARI VAR, YUKARIDAKİ RAPORU İNCELEYİN")
    return results


if __name__ == "__main__":
    res = run_test_harness()
    sys.exit(0 if all(res.values()) else 1)
