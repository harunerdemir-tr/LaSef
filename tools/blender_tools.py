import json
from tools.blender_bridge_client import blender_bridge, find_blender_executable


def blender_ping() -> str:
    """Blender MCP köprüsünün ve yerel Blender kurulumunun durumunu kontrol eder."""
    live = blender_bridge.ping()
    exe = find_blender_executable()
    if live.get("success"):
        return json.dumps({
            "live_bridge": True,
            "blender_exe": exe,
            **live
        }, ensure_ascii=False, indent=2)
    return json.dumps({
        "live_bridge": False,
        "bridge_message": live.get("error", ""),
        "headless_available": bool(exe),
        "blender_exe": exe,
    }, ensure_ascii=False, indent=2)


def blender_get_scene() -> str:
    """Canlı Blender sahnesindeki nesneleri, kameraları, ışıkları ve materyalleri okur."""
    res = blender_bridge.get_scene_info()
    return json.dumps(res, ensure_ascii=False, indent=2)


def blender_execute_python(code: str) -> str:
    """Canlı Blender sahnesinde doğrudan bpy Python kodu çalıştırır."""
    res = blender_bridge.execute_python(code)
    return json.dumps(res, ensure_ascii=False, indent=2)


def blender_run_script_headless(script_path: str, save_blend_path: str = "", render_preview_path: str = "") -> str:
    """Verilen bpy Python betiğini Blender --background --python ile gerçekten çalıştırır ve sahne raporu döner."""
    res = blender_bridge.run_script_headless(
        script_path=script_path,
        save_blend_path=save_blend_path or None,
        render_preview_path=render_preview_path or None,
    )
    return json.dumps(res, ensure_ascii=False, indent=2)
