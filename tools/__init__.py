import json
import os
import re
from typing import Any, Dict, Optional, Tuple

from tools.file_system_tools import (
    tool_list_dir,
    tool_read_file,
    tool_write_file,
    tool_replace_in_file,
    tool_run_command
)
from tools.extended_tools import (
    tool_grep_search,
    tool_check_syntax
)
from tools.unity_tools import (
    tool_unity_status,
    tool_unity_get_hierarchy,
    tool_unity_inspect_object,
    tool_unity_create_object,
    tool_unity_delete_object,
    tool_unity_add_component,
    tool_unity_set_property,
    tool_unity_create_prefab,
    tool_unity_instantiate_prefab,
    tool_unity_execute_csharp,
    tool_unity_get_logs,
    tool_unity_clear_logs,
    tool_unity_wait_compile,
    tool_unity_save_scene,
    tool_unity_set_play_mode,
    tool_unity_capture_screenshot
)
from tools.blender_tools import (
    blender_ping,
    blender_get_scene,
    blender_execute_python,
    blender_run_script_headless
)

KNOWN_TOOLS = {
    "list_directory", "read_file", "write_file", "replace_in_file",
    "run_terminal", "grep_search", "check_syntax", "inspect_image", "search_assets",
    "unity_status", "unity_ping", "unity_get_hierarchy", "unity_inspect_object",
    "unity_create_object", "unity_delete_object", "unity_add_component",
    "unity_set_property", "unity_create_prefab", "unity_instantiate_prefab",
    "unity_execute_csharp", "unity_get_logs", "unity_clear_logs",
    "unity_wait_compile", "unity_save_scene", "unity_set_play_mode",
    "unity_capture_screenshot",
    "browser_open", "browser_click", "browser_type", "browser_press_key",
    "browser_screenshot", "browser_get_logs", "browser_inspect_dom", "browser_close",
    "desktop_screenshot", "computer_use_screenshot",
    "blender_ping", "blender_status", "mcp_blender_ping",
    "blender_get_scene", "mcp_blender_get_scene",
    "blender_execute_python", "mcp_blender_execute_python",
    "blender_run_script_headless", "mcp_blender_run_headless",
}


def extract_tool_call(response_text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Model yanıtından (Gemini veya NVIDIA NIM) ```tool ... ```, ```json {"tool": ...} ```
    veya doğrudan tek başına `tool {"tool": ...}` / `{"tool": ...}` biçimindeki araç çağrısını güvenli şekilde ayıklar.
    Nihai rapor metinleri içindeki satır içi örnek JSON'ları veya kod bloklarını yanlışlıkla araç çağrısı sanmaz.
    """
    if not response_text or not isinstance(response_text, str) or '"tool"' not in response_text:
        return None

    cleaned = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
    if not cleaned or '"tool"' not in cleaned:
        return None

    for block_m in re.finditer(r"```([a-zA-Z0-9_\-#]+)\s*\n(.*?)```", cleaned, re.DOTALL):
        lang = (block_m.group(1) or "").strip().lower()
        body = (block_m.group(2) or "").strip()
        if lang not in ("tool", "json") and len(body) > 40:
            return None

    def _validate_tool_dict(data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        if not isinstance(data, dict):
            return None
        allowed_keys = {"tool", "args", "arguments"}
        if not set(data.keys()).issubset(allowed_keys):
            return None
        t_name = data.get("tool")
        t_args = data.get("args") if isinstance(data.get("args"), dict) else data.get("arguments")
        if t_args is None:
            t_args = {}
        if isinstance(t_name, str) and isinstance(t_args, dict):
            if t_name in KNOWN_TOOLS or t_name.startswith("mcp:"):
                return t_name, dict(t_args)
        return None

    for m in re.finditer(r"```(tool|json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE):
        tag = (m.group(1) or "").strip().lower()
        body = m.group(2).strip()
        if body.startswith("tool"):
            body = body[4:].strip()
        if not (body.startswith("{") and body.endswith("}") and '"tool"' in body):
            continue
        outside_len = len(cleaned) - (m.end() - m.start())
        if tag != "tool" and outside_len > 260:
            continue
        try:
            res = _validate_tool_dict(json.loads(body))
            if res:
                return res
        except Exception:
            continue

    decoder = json.JSONDecoder()
    for line in cleaned.splitlines():
        s_line = line.strip()
        if not s_line:
            continue
        if s_line.lower().startswith("tool"):
            s_line = s_line[4:].strip()
        if not (s_line.startswith("{") and s_line.endswith("}") and '"tool"' in s_line):
            continue
        outside_prose_len = len(cleaned) - len(line)
        if outside_prose_len > 220:
            continue
        try:
            data, end_idx = decoder.raw_decode(s_line)
            if s_line[end_idx:].strip():
                continue
            res = _validate_tool_dict(data)
            if res:
                return res
        except Exception:
            continue

    return None


def resolve_tool_paths(tool_args: Dict[str, Any], base_dir: str) -> Dict[str, Any]:
    """Göreli dosya/dizin argümanlarını proje kök diziniyle güvenli şekilde birleştirir."""
    if not base_dir or not isinstance(tool_args, dict):
        return tool_args
    resolved = dict(tool_args)
    for key in ("file_path", "directory_path", "path", "file", "asset_path", "script_path"):
        val = resolved.get(key)
        if isinstance(val, str) and val.strip() and not os.path.isabs(val):
            if key == "asset_path":
                continue
            resolved[key] = os.path.normpath(os.path.join(base_dir, val))
    return resolved


def _arg_first(arguments: dict, *keys: str, default: Any = "") -> Any:
    for k in keys:
        v = arguments.get(k)
        if v is not None and v != "":
            return v
    return default


def execute_tool_call(tool_name: str, arguments: dict) -> str:
    """Ajanın talep ettiği aracı işletim sisteminde veya Unity Editor'de çalıştırır ve sonucu ajana geri verir."""
    arguments = arguments or {}
    if tool_name == "list_directory":
        return tool_list_dir(_arg_first(arguments, "directory_path", "path", "dir", default="."))
    elif tool_name == "read_file":
        return tool_read_file(_arg_first(arguments, "file_path", "path", "file"))
    elif tool_name == "write_file":
        return tool_write_file(_arg_first(arguments, "file_path", "path", "file"), arguments.get("content", ""))
    elif tool_name == "replace_in_file":
        return tool_replace_in_file(
            _arg_first(arguments, "file_path", "path", "file"),
            _arg_first(arguments, "target_content", "old_content", "target"),
            _arg_first(arguments, "replacement_content", "new_content", "replacement")
        )
    elif tool_name == "run_terminal":
        return tool_run_command(arguments.get("command", ""))
    elif tool_name == "grep_search":
        return tool_grep_search(_arg_first(arguments, "directory_path", "path", default="."), arguments.get("pattern", ""))
    elif tool_name == "check_syntax":
        return tool_check_syntax(_arg_first(arguments, "file_path", "path", "file"))
    elif tool_name == "inspect_image":
        from infrastructure.file_reader import inspect_image_with_cache
        return inspect_image_with_cache(
            _arg_first(arguments, "file_path", "path", "file"),
            detailed=bool(arguments.get("detailed", False)),
        )
    elif tool_name == "search_assets":
        from infrastructure.file_reader import search_asset_manifest
        return search_asset_manifest(
            _arg_first(arguments, "directory_path", "path", default="."),
            query=arguments.get("query", ""),
            limit=int(arguments.get("limit", 40) or 40),
        )

    elif tool_name in ["unity_status", "unity_ping"]:
        return tool_unity_status()
    elif tool_name == "unity_get_hierarchy":
        return tool_unity_get_hierarchy()
    elif tool_name == "unity_inspect_object":
        return tool_unity_inspect_object(_arg_first(arguments, "target", "object_name", "name"))
    elif tool_name == "unity_create_object":
        return tool_unity_create_object(
            name=_arg_first(arguments, "name", "target", "object_name", default="GameObject_Ajan"),
            primitive_type=arguments.get("primitive_type", ""),
            parent=arguments.get("parent", ""),
            px=float(arguments.get("px", 0.0)),
            py=float(arguments.get("py", 0.0)),
            pz=float(arguments.get("pz", 0.0)),
            sx=float(arguments.get("sx", 1.0)),
            sy=float(arguments.get("sy", 1.0)),
            sz=float(arguments.get("sz", 1.0))
        )
    elif tool_name == "unity_add_component":
        return tool_unity_add_component(
            _arg_first(arguments, "target", "object_name", "name"),
            _arg_first(arguments, "component", "component_name", "type")
        )
    elif tool_name == "unity_set_property":
        return tool_unity_set_property(
            target=_arg_first(arguments, "target", "object_name", "name"),
            component=_arg_first(arguments, "component", "component_name"),
            property_name=_arg_first(arguments, "property", "property_name", "field"),
            value=arguments.get("value", ""),
            is_reference=bool(arguments.get("is_reference", False))
        )
    elif tool_name == "unity_create_prefab":
        return tool_unity_create_prefab(_arg_first(arguments, "target", "object_name", "name"), arguments.get("asset_path", ""))
    elif tool_name == "unity_instantiate_prefab":
        return tool_unity_instantiate_prefab(arguments.get("asset_path", ""), arguments.get("parent", ""))
    elif tool_name == "unity_execute_csharp":
        return tool_unity_execute_csharp(_arg_first(arguments, "code", "code_snippet"))
    elif tool_name == "unity_get_logs":
        return tool_unity_get_logs()
    elif tool_name == "unity_wait_compile":
        return tool_unity_wait_compile(float(arguments.get("timeout", 30.0)))
    elif tool_name == "unity_delete_object":
        return tool_unity_delete_object(_arg_first(arguments, "target", "object_name", "name"))
    elif tool_name == "unity_set_play_mode":
        return tool_unity_set_play_mode(bool(arguments.get("play", True)))
    elif tool_name == "unity_capture_screenshot":
        res = tool_unity_capture_screenshot(bool(arguments.get("prefer_game_view", True)))
        if res.get("success"):
            return f"📸 Ekran görüntüsü alındı ({res.get('camera', 'Camera')}, {len(res.get('data',''))} bayt b64)."
        return f"Hata: {res.get('error')}"
    elif tool_name == "unity_clear_logs":
        return tool_unity_clear_logs()
    elif tool_name == "unity_save_scene":
        return tool_unity_save_scene()

    elif tool_name == "browser_open":
        from tools.browser_tools import browser_engine
        url = arguments.get("url", "http://127.0.0.1:8099")
        headless = bool(arguments.get("headless", True))
        res = browser_engine.open_page(url, headless=headless)
        return f"Tarayıcı Açıldı: {res.get('title', url)}" if res.get("success") else f"Hata: {res.get('error')}"
    elif tool_name == "browser_click":
        from tools.browser_tools import browser_engine
        res = browser_engine.click(arguments.get("selector", "button"))
        return f"Tıklandı: {arguments.get('selector')}" if res.get("success") else f"Tıklama Hatası: {res.get('error')}"
    elif tool_name == "browser_type":
        from tools.browser_tools import browser_engine
        res = browser_engine.type_text(arguments.get("selector", "input"), arguments.get("text", ""))
        return f"Yazıldı: '{arguments.get('text')}' -> {arguments.get('selector')}" if res.get("success") else f"Yazma Hatası: {res.get('error')}"
    elif tool_name == "browser_press_key":
        from tools.browser_tools import browser_engine
        res = browser_engine.press_key(arguments.get("key", "Space"))
        return f"Tuşa Basıldı: {arguments.get('key')}" if res.get("success") else f"Hata: {res.get('error')}"
    elif tool_name == "browser_screenshot":
        from tools.browser_tools import browser_engine
        out_p = arguments.get("output_path", "temp_browser_screenshot.png")
        res = browser_engine.capture_screenshot(out_p)
        return f"📸 Tarayıcı Ekranı Kaydedildi: {out_p} ({res.get('size_kb', 0):.1f} KB)" if res.get("success") else f"Ekran Hatası: {res.get('error')}"
    elif tool_name == "browser_get_logs":
        from tools.browser_tools import browser_engine
        res = browser_engine.get_logs_and_errors()
        errs = res.get("page_errors", [])
        logs = [f"[{l['type']}] {l['text']}" for l in res.get("console_logs", [])]
        return f"Sayfa Hataları: {errs}\nKonsol Logları: {logs}" if (errs or logs) else "Tarayıcı konsolu temiz (Hata yok)."
    elif tool_name == "browser_inspect_dom":
        from tools.browser_tools import browser_engine
        res = browser_engine.inspect_dom()
        return f"DOM Özeti: {res.get('dom_info')}" if res.get("success") else f"DOM Hatası: {res.get('error')}"
    elif tool_name == "browser_close":
        from tools.browser_tools import browser_engine
        browser_engine.close()
        return "Tarayıcı kapatıldı."
    elif tool_name in ["desktop_screenshot", "computer_use_screenshot"]:
        from tools.browser_tools import capture_desktop_screenshot
        out_p = arguments.get("output_path", "temp_desktop_screenshot.png")
        res = capture_desktop_screenshot(out_p)
        return f"🖥️ Masaüstü Ekranı Kaydedildi: {out_p} ({res.get('size_kb', 0):.1f} KB)" if res.get("success") else f"Ekran Hatası: {res.get('error')}"

    elif tool_name in ["blender_ping", "blender_status", "mcp_blender_ping"]:
        return blender_ping()
    elif tool_name in ["blender_get_scene", "mcp_blender_get_scene"]:
        return blender_get_scene()
    elif tool_name in ["blender_execute_python", "mcp_blender_execute_python"]:
        return blender_execute_python(arguments.get("code", ""))
    elif tool_name in ["blender_run_script_headless", "mcp_blender_run_headless"]:
        return blender_run_script_headless(
            arguments.get("script_path", ""),
            arguments.get("save_blend_path", ""),
            arguments.get("render_preview_path", "")
        )

    elif tool_name.startswith("mcp:"):
        parts = tool_name.split(":", 2)
        if len(parts) == 3:
            from tools.mcp_client_manager import MCPClientManager
            mgr = MCPClientManager()
            return mgr.call_tool_sync(parts[1], parts[2], arguments)

    return f"Bilinmeyen araç: {tool_name}"
