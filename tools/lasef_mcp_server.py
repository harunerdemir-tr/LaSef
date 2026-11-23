
import contextlib
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

with contextlib.redirect_stdout(sys.stderr):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError("MCP paketi yüklü değil. Kurmak için: pip install mcp>=1.0.0") from exc

    from core.mcp_router import detect_application_profile
    from infrastructure.gemini_client import gemini_service
    from infrastructure.nim_client import nim_service
    from tools.blender_tools import (
        blender_execute_python,
        blender_get_scene,
        blender_ping,
        blender_run_script_headless,
    )
    from tools.unity_bridge_client import unity_client
    from tools.unity_tools import (
        tool_unity_add_component,
        tool_unity_capture_screenshot,
        tool_unity_create_object,
        tool_unity_execute_csharp,
        tool_unity_get_hierarchy,
        tool_unity_get_logs,
        tool_unity_set_play_mode,
        tool_unity_set_property,
        tool_unity_status,
    )

mcp = FastMCP("LaSef-Orchestrator")


def _unity_alive() -> bool:
    try:
        st = unity_client.get_status() if hasattr(unity_client, "get_status") else unity_client._send_request("/status", method="GET", timeout=1.5, retries=0)
        return bool(isinstance(st, dict) and st.get("online"))
    except Exception:
        return False


@mcp.tool()
def lasef_analyze_input(prompt: str, project_dir: str = "") -> str:
    """
    Kullanıcı girdisini ve opsiyonel proje dizinini analiz ederek hedef uygulamayı
    (unity, blender, web, unreal, database, general), uygun skill/model yönlendirmesini
    ve canlı köprü durumunu döndürür.
    """
    with contextlib.redirect_stdout(sys.stderr):
        profile = detect_application_profile(prompt, project_dir)
        unity_ok = _unity_alive()
        b_status = json.loads(blender_ping())
    return json.dumps({
        "app_key": profile.app_key,
        "display_name": profile.display_name,
        "recommended_tools": profile.recommended_tools,
        "unity_bridge_alive": unity_ok,
        "blender_status": b_status,
        "nim_verified_models": nim_service.verified_models[:6],
        "gemini_active_model": gemini_service.active_model,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def lasef_model_health(refresh: bool = False) -> str:
    """Gemini Şef ve NVIDIA NIM alt ajan modellerinin canlı sağlık ve gecikme durumunu raporlar."""
    with contextlib.redirect_stdout(sys.stderr):
        if refresh or nim_service.needs_health_refresh():
            nim_service.health_check()
        if refresh or not gemini_service._is_healthy:
            gemini_service.health_check()
    return json.dumps({
        "gemini_healthy": gemini_service._is_healthy,
        "gemini_active_model": gemini_service.active_model,
        "nim_healthy": nim_service._is_healthy,
        "nim_verified_models": [
            {"id": m, "latency_sec": nim_service.model_latencies.get(m)}
            for m in nim_service.verified_models
        ],
        "nim_dead_models": sorted(nim_service.dead_models),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def lasef_run_orchestration(
    prompt: str,
    output_dir: str = "",
    source_paths_csv: str = "",
    dry_plan_only: bool = False,
) -> str:
    """
    LaSef Şef (Gemini) + Optimize NVIDIA NIM Alt Ajanlar + Uygulama Doğrulayıcı (Unity/Blender/Web)
    orkestrasyonunu verilen girdi üzerinde uçtan uca çalıştırır.
    dry_plan_only=True ise dosya üretmeden sadece Şef mimari görev planını döndürür.
    """
    with contextlib.redirect_stdout(sys.stderr):
        if dry_plan_only:
            from agents.chef_supervisor import chef_supervisor
            if nim_service.needs_health_refresh():
                nim_service.health_check()
            plan = chef_supervisor.gorevi_planla(prompt, source_paths_csv)
            return json.dumps({
                "mode": "dry_plan",
                "proje_klasor_adi": plan.proje_klasor_adi,
                "mimari_sozlesme": plan.mimari_sozlesme,
                "moduller": [
                    {
                        "adim": m.adim_no,
                        "dosya": m.dosya_adi,
                        "baslik": m.baslik,
                        "uzmanlik": m.uzmanlik,
                        "model_onerisi": m.model_onerisi,
                        "bagimli": m.bagimli_adimlar,
                    }
                    for m in plan.moduller
                ],
            }, ensure_ascii=False, indent=2)

        from orchestrator import orkestrayi_yonet
        sources = [p.strip() for p in source_paths_csv.split(",") if p.strip()] if source_paths_csv else None
        meta_out: dict = {}
        report = orkestrayi_yonet(
            kullanici_istegi=prompt,
            hedef_klasor=output_dir,
            kaynak_dosyalar=sources,
            meta_out=meta_out,
        )
    return json.dumps({
        "mode": "executed",
        "app_key": meta_out.get("app_key", "general"),
        "target_folder": meta_out.get("target_folder", output_dir),
        "files_produced": meta_out.get("files_produced", []),
        "token_stats": meta_out.get("token_stats", {}),
        "report": report,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_blender_ping() -> str:
    """Blender canlı MCP köprüsü (9876) ve Blender CLI kurulum durumunu kontrol eder."""
    with contextlib.redirect_stdout(sys.stderr):
        return blender_ping()


@mcp.tool()
def mcp_blender_get_scene() -> str:
    """Canlı Blender sahne hiyerarşisini ve nesneleri listeler."""
    with contextlib.redirect_stdout(sys.stderr):
        return blender_get_scene()


@mcp.tool()
def mcp_blender_execute_python(code: str) -> str:
    """Canlı Blender sahnesinde doğrudan bpy Python kodu yürütür."""
    with contextlib.redirect_stdout(sys.stderr):
        return blender_execute_python(code)


@mcp.tool()
def mcp_blender_run_headless(script_path: str, save_blend_path: str = "", render_preview_path: str = "") -> str:
    """Blender --background --python ile bpy betiğini doğrular, .blend ve PNG önizleme üretir."""
    with contextlib.redirect_stdout(sys.stderr):
        return blender_run_script_headless(script_path, save_blend_path, render_preview_path)


@mcp.tool()
def mcp_unity_status() -> str:
    """Canlı Unity Editor köprüsü (127.0.0.1:8088) bağlantı durumunu döndürür."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_status()


@mcp.tool()
def mcp_unity_get_hierarchy() -> str:
    """Unity Editor aktif sahne hiyerarşisini okur."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_get_hierarchy()


@mcp.tool()
def mcp_unity_create_object(
    name: str,
    primitive_type: str = "",
    parent: str = "",
    px: float = 0.0,
    py: float = 0.0,
    pz: float = 0.0,
    sx: float = 1.0,
    sy: float = 1.0,
    sz: float = 1.0,
) -> str:
    """Unity sahnesine yeni GameObject veya Primitive ekler."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_create_object(name, primitive_type, parent, px, py, pz, sx, sy, sz)


@mcp.tool()
def mcp_unity_add_component(target: str, component_name: str) -> str:
    """Unity nesnesine bileşen (Rigidbody, AudioSource, script vb.) ekler."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_add_component(target, component_name)


@mcp.tool()
def mcp_unity_set_property(target: str, component: str, property_name: str, value: str, is_reference: bool = False) -> str:
    """Unity bileşen özelliğini veya Inspector referansını ayarlar."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_set_property(target, component, property_name, value, is_reference)


@mcp.tool()
def mcp_unity_execute_csharp(code_snippet: str) -> str:
    """Unity Editor içinde statik C# metodu veya SceneBuilder çalıştırır."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_execute_csharp(code_snippet)


@mcp.tool()
def mcp_unity_get_logs() -> str:
    """Unity Editor Console derleme ve çalışma zamanı loglarını okur."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_get_logs()


@mcp.tool()
def mcp_unity_capture_screenshot(prefer_game_view: bool = True) -> str:
    """Unity Game/Scene görünümünün ekran görüntüsünü yakalar."""
    with contextlib.redirect_stdout(sys.stderr):
        res = tool_unity_capture_screenshot(prefer_game_view)
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
def mcp_unity_set_play_mode(play: bool) -> str:
    """Unity Editör Play Mode durumunu açar/kapatır."""
    with contextlib.redirect_stdout(sys.stderr):
        return tool_unity_set_play_mode(play)


if __name__ == "__main__":
    mcp.run()
