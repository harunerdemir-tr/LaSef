"""
👑 LaSef Unity MCP (Model Context Protocol) Sunucusu
--------------------------------------------------
Unity Editor ile Yapay Zeka Ajanları (LaSef Ajanları, Claude Desktop, Cursor, Antigravity)
arasındaki standart iki yönlü MCP köprüsü.

Bu sunucu çalıştığında:
- Sahne hiyerarşisini okur ve manipüle eder (GameObject, Transform, Prefab).
- Bileşen ekler/kaldırır, SerializedProperty ve referansları bağlar.
- C# REPL kodu çalıştırır (Editor reflection).
- Konsol loglarını ve derleme hatalarını (CS errors) canlı denetler.
- Play Mode'u kontrol eder ve GameView ekran görüntüsünü çeker (Vision Eye).
"""
import os
import sys
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LASEF_ROOT = os.path.dirname(CURRENT_DIR)
if LASEF_ROOT not in sys.path:
    sys.path.insert(0, LASEF_ROOT)

from mcp.server.fastmcp import FastMCP
from tools.unity_bridge_client import unity_client
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

mcp = FastMCP(
    "LaSef-Unity-Bridge",
    description="LaSef Otonom Çoklu Ajan Unity Editor Köprüsü ve Canlı Denetim MCP Sunucusu"
)

@mcp.tool()
def unity_status() -> str:
    """Unity Editor'ün bağlantı durumunu, sürümünü, aktif sahnesini ve derleme vaziyetini sorgular."""
    return tool_unity_status()

@mcp.tool()
def unity_get_hierarchy() -> str:
    """Aktif Unity sahnesindeki tüm GameObject ağacını, koordinatlarını ve bileşenlerini listeler."""
    return tool_unity_get_hierarchy()

@mcp.tool()
def unity_inspect_object(target: str) -> str:
    """Belirli bir GameObject'in tüm bileşenlerini ve SerializedProperty alanlarını detaylı inceler."""
    return tool_unity_inspect_object(target)

@mcp.tool()
def unity_create_object(
    name: str,
    primitive_type: str = "",
    parent: str = "",
    px: float = 0.0, py: float = 0.0, pz: float = 0.0,
    sx: float = 1.0, sy: float = 1.0, sz: float = 1.0
) -> str:
    """Sahneye yeni bir GameObject veya Primitif (Cube, Sphere, Capsule, Plane vb.) ekler."""
    return tool_unity_create_object(name, primitive_type, parent, px, py, pz, sx, sy, sz)

@mcp.tool()
def unity_delete_object(target: str) -> str:
    """Sahnedeki bir GameObject'i güvenle (Undo desteğiyle) siler."""
    return tool_unity_delete_object(target)

@mcp.tool()
def unity_add_component(target: str, component_name: str) -> str:
    """Belirtilen GameObject'e yeni bir bileşen (Rigidbody, BoxCollider, PlayerController vb.) takar."""
    return tool_unity_add_component(target, component_name)

@mcp.tool()
def unity_set_property(
    target: str,
    component: str,
    property_name: str,
    value: str,
    is_reference: bool = False
) -> str:
    """
    Bileşenin alanını (field/property) ayarlar.
    Örnek: target='Player', component='PlayerController', property_name='speed', value='8.5'
    Referans bağlama: target='Player', component='PlayerController', property_name='groundCheck', value='GroundCheck', is_reference=True
    """
    return tool_unity_set_property(target, component, property_name, value, is_reference)

@mcp.tool()
def unity_create_prefab(target: str, asset_path: str = "") -> str:
    """Sahnedeki bir objeyi Assets/Prefabs altında temiz bir Prefab olarak kaydeder."""
    return tool_unity_create_prefab(target, asset_path)

@mcp.tool()
def unity_instantiate_prefab(asset_path: str, parent: str = "") -> str:
    """Diskteki bir Prefab'ı sahneye örnekler (Instantiate)."""
    return tool_unity_instantiate_prefab(asset_path, parent)

@mcp.tool()
def unity_execute_csharp(code: str) -> str:
    """Unity Editor içinde ana thread üzerinde anında C# Editor kodu çalıştırır (REPL)."""
    return tool_unity_execute_csharp(code)

@mcp.tool()
def unity_get_console_logs() -> str:
    """Unity konsolundaki en son kırmızı hataları, uyarıları ve logları okur."""
    return tool_unity_get_logs()

@mcp.tool()
def unity_clear_console_logs() -> str:
    """Unity konsol loglarını temizler."""
    return tool_unity_clear_logs()

@mcp.tool()
def unity_wait_compilation(timeout: float = 30.0) -> str:
    """C# scriptleri yazıldıktan sonra Unity'nin derleme yapmasını (Domain Reload) bekler ve derleme hatalarını bildirir."""
    return tool_unity_wait_compile(timeout)

@mcp.tool()
def unity_save_scene() -> str:
    """Aktif sahneyi diske kaydeder."""
    return tool_unity_save_scene()

@mcp.tool()
def unity_set_play_mode(play: bool = True) -> str:
    """Unity'de Play Mode'u (Oyun modunu) açar (True) veya kapatır (False)."""
    return tool_unity_set_play_mode(play)

@mcp.tool()
def unity_capture_screenshot(prefer_game_view: bool = True) -> str:
    """Unity GameView kamerasından sahnenin görüntüsünü yakalar ve boyutunu döner."""
    res = tool_unity_capture_screenshot(prefer_game_view)
    if res.get("success"):
        return f"📸 Ekran görüntüsü başarıyla alındı ({res.get('camera')}, {len(res.get('data',''))} bayt)."
    return f"Hata: {res.get('error')}"

if __name__ == "__main__":
    mcp.run()
