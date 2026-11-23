"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF MCP UYGULAMA YÖNLENDİRİCİSİ VE ENTEGRASYON MERKEZİ (core/mcp_router.py)
═══════════════════════════════════════════════════════════════════════════════
📌 LASEF KORTEKS PRENSİBİ:
LaSef, körü körüne ya da denenmemiş yapay MCP kodlarını projeye entegre etmez!
Kullanıcının talep ettiği görevi (Unity, Web, Blender, Unreal, SQL vb.) analiz eder,
hangi uygulama ortamının hedeflendiğini anlar ve yalnızca ENDÜSTRİDE DENENMİŞ,
ÇALIŞAN ve GÜVENİLİR standart MCP / araç çözümlerini ve kurulum yönergelerini sunar.
═══════════════════════════════════════════════════════════════════════════════
"""
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class MCPAppProfile:
    app_key: str
    display_name: str
    is_mcp_supported: bool
    standard_package_name: str
    installation_type: str
    direct_install_target: str
    mcp_config_snippet: Dict[str, Any]
    user_guide_markdown: str
    builtin_alternative: str
    recommended_tools: List[str] = field(default_factory=list)

MCP_CATALOG: Dict[str, MCPAppProfile] = {
    "unity": MCPAppProfile(
        app_key="unity",
        display_name="Unity Game Engine (2D / 3D)",
        is_mcp_supported=True,
        standard_package_name="CoplayDev/unity-mcp (Topluluk Standardı UPM Paketi)",
        installation_type="UPM_GIT",
        direct_install_target="https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#main",
        mcp_config_snippet={
            "unity": {
                "command": "python",
                "args": ["-m", "tools.unity_mcp_server"],
                "env": {
                    "UNITY_PORT": "8088"
                }
            }
        },
        user_guide_markdown="""### 🎮 Unity MCP Kurulum ve Entegrasyon Yönergesi:
Unity ile çalışırken harici karmaşık kod yazmaya gerek yoktur. 2 denenmiş ve çalışan yöntem mevcuttur:

1. **YÖNTEM 1 (Resmi/Topluluk Standardı UPM Paketi - CoplayDev/unity-mcp):**
   - Unity Editor'ü açın.
   - Üst menüden `Window` -> `Package Manager` penceresine gidin.
   - Sol üstteki `+` butonuna tıklayıp **"Add package from git URL..."** seçeneğini seçin.
   - Şu adresi yapıştırın ve Add'e basın:
     `https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#main`
   - Paket yüklendiğinde Editor içerisinde doğrudan MCP araçları aktifleşir.

2. **YÖNTEM 2 (LaSef Yerleşik Köprüsü - Sıfır Dış Bağımlılık):**
   - Projenizdeki `unity_bridge/Editor/LaSefBridge/LaSefBridgeServer.cs` dosyasını Unity projenizin `Assets/Editor/` klasörüne kopyalayın.
   - Unity otomatik derler ve 8088 portunda güvenli yerel köprüyü ayağa kaldırır.
   - LaSef'in Şefin Gözü (Vision Eye) ve `UnityAutonomousPlaytester` aracı sahnede anında canlı test ve onarım yapabilir.""",
        builtin_alternative="LaSef UnityAutonomousPlaytester (Play Mode + Vision Eye Screenshot + C# Canlı REPL)",
        recommended_tools=[
            "unity_status",
            "unity_get_hierarchy",
            "unity_create_object",
            "unity_add_component",
            "unity_set_property",
            "unity_wait_compilation",
            "unity_capture_screenshot"
        ]
    ),

    "web": MCPAppProfile(
        app_key="web",
        display_name="Web & Modern Tarayıcı (HTML5, Canvas, DOM)",
        is_mcp_supported=True,
        standard_package_name="@modelcontextprotocol/server-puppeteer",
        installation_type="NPM",
        direct_install_target="npx -y @modelcontextprotocol/server-puppeteer",
        mcp_config_snippet={
            "puppeteer": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
            }
        },
        user_guide_markdown="""### 🌐 Web & Tarayıcı MCP Entegrasyonu:
- Web projelerinde canlı DOM denetimi ve ekran yakalama için resmi `@modelcontextprotocol/server-puppeteer` MCP sunucusu kullanılır.
- Veya LaSef'in yerleşik `WebAutonomousPlaytester` modülü doğrudan Playwright ile tarayıcıyı başlatıp 60 FPS denetimini gerçekleştirir.""",
        builtin_alternative="LaSef WebAutonomousPlaytester (Playwright Canlı Tarayıcı, Konsol Dinleme & Vision Eye)",
        recommended_tools=["browser_navigate", "browser_screenshot", "browser_click"]
    ),

    "blender": MCPAppProfile(
        app_key="blender",
        display_name="Blender 3D & Headless / Live MCP Köprüsü",
        is_mcp_supported=True,
        standard_package_name="lasef-orchestrator / ahujasid/mcp-for-blender",
        installation_type="BUILTIN_AND_ADDON",
        direct_install_target="blender_addon/lasef_blender_bridge.py",
        mcp_config_snippet={
            "blender": {
                "command": "python",
                "args": ["-m", "blender_mcp.server"],
                "env": {
                    "BLENDER_PORT": "9876"
                }
            }
        },
        user_guide_markdown="""### 🎨 Blender 3D MCP & Otonom Doğrulama:
- LaSef yerel `Blender 4.x/5.x` kurulumunu (`--background --python`) veya `blender_addon/lasef_blender_bridge.py` eklentisini (port `9876`) otomatik kullanarak üretilen `bpy` betiklerini çalıştırır, `.blend` ve PNG önizleme alır.
- Harici MCP istemcileri `tools/lasef_mcp_server.py` ile hem LaSef orkestrasyonunu hem Blender araçlarını doğrudan çağırabilir.""",
        builtin_alternative="LaSef BlenderBridgeClient + BlenderAutonomousRunner",
        recommended_tools=["mcp_blender_ping", "mcp_blender_get_scene", "mcp_blender_execute_python", "mcp_blender_run_headless"]
    ),

    "unreal": MCPAppProfile(
        app_key="unreal",
        display_name="Unreal Engine 5 (C++, Blueprints, Remote Control)",
        is_mcp_supported=True,
        standard_package_name="ChiR24/Unreal_mcp (veya chongdashu/unreal-mcp)",
        installation_type="UE_PLUGIN",
        direct_install_target="https://github.com/ChiR24/Unreal_mcp",
        mcp_config_snippet={
            "unreal": {
                "command": "npx",
                "args": ["-y", "unreal-mcp-server"]
            }
        },
        user_guide_markdown="""### 🎮 Unreal Engine MCP Entegrasyonu:
- Unreal Engine 5 için denenmiş yöntem: Projenin `Plugins/` klasörüne `Unreal_mcp` eklentisini ekleyip Remote Control API'sini etkinleştirmektir.
- Bu sayede AI, Actor'leri sahnede oluşturabilir ve Blueprint fonksiyonlarını uzaktan çağırabilir.""",
        builtin_alternative="Unreal Remote Control HTTP API",
        recommended_tools=["unreal_spawn_actor", "unreal_call_function", "unreal_get_actors"]
    ),

    "database": MCPAppProfile(
        app_key="database",
        display_name="Veritabanı (SQLite / PostgreSQL)",
        is_mcp_supported=True,
        standard_package_name="@modelcontextprotocol/server-sqlite",
        installation_type="NPM",
        direct_install_target="npx -y @modelcontextprotocol/server-sqlite",
        mcp_config_snippet={
            "sqlite": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sqlite", "--db-path", "./database.sqlite"]
            }
        },
        user_guide_markdown="""### 🗄️ Veritabanı MCP Entegrasyonu:
- Veritabanı şemalarını okumak ve sorgu çalıştırmak için resmi `@modelcontextprotocol/server-sqlite` veya `postgres` sunucuları kullanılır.""",
        builtin_alternative="Python sqlite3 / SQLAlchemy",
        recommended_tools=["read_query", "write_query", "describe_table"]
    )
}

def _is_unity_workspace(target_folder: str) -> bool:
    if not target_folder or not os.path.isdir(target_folder):
        return False
    assets_dir = os.path.join(target_folder, "Assets")
    return os.path.isdir(assets_dir) and (
        os.path.isdir(os.path.join(target_folder, "ProjectSettings"))
        or os.path.isdir(os.path.join(target_folder, "Packages"))
    )


def detect_application_profile(
    user_request: str,
    source_context: str = "",
    target_folder: str = "",
) -> MCPAppProfile:
    """
    Kullanıcının girdisini, çalışma alanı klasörünü ve kaynak bağlamını analiz ederek
    uygun uygulama alanını ve standart MCP profilini belirler.
    Unity projelerinde geçen 'canvas' (Unity UI Canvas) ifadesini HTML5 Canvas ile karıştırmaz.
    """
    req_low = (user_request or "").lower()
    src_low = (source_context or "")[:4000].lower()
    is_unity_dir = _is_unity_workspace(target_folder)
    has_unity_ctx = is_unity_dir or any(
        sig in src_low
        for sig in (
            "canlı unity editör", "port 8088", "assets/scripts/", "assets\\scripts\\",
            "monobehaviour", "unityengine", "packages/manifest.json"
        )
    )

    unity_keywords = [
        "unity", "monobehaviour", "gameobject", "rigidbody", "c#", ".cs",
        "scenebuilder", "gamebootstrapper", "prefab", "collider", "unityengine",
        "unityeditor", "urp", "unity projesi", "lasefbridge", "samplescene",
        "hiyerarşi", "hiyerarsi", "derlenmiyor", "derleme hatası", "konsol",
        "charactercontroller", "navmesh"
    ]
    blender_keywords = [
        "blender", "bpy", ".blend", "3d modelleme", "shader node", "cycles",
        "eevee", "geometry nodes", "armature", "uv unwrap", "mesh model", "glb", "fbx"
    ]
    unreal_keywords = ["unreal", "ue5", "ue4", "blueprint", "unreal engine", "uproperty", "aactor"]
    web_exclusive_strong = [
        "index.html", "html5", "css", "javascript", "vanilla js",
        "tarayıcı", "browser", "web oyunu", "web tabanlı", "react", "next.js",
        "fastapi", "frontend", "tek html", "web ortamı"
    ]
    web_soft = ["web", "html", "site", "dashboard", "dom", "svg"]
    db_keywords = ["sql", "sqlite", "postgres", "supabase", "veritabanı", "database", "tablo şeması"]

    has_explicit_web_in_req = any(k in req_low for k in web_exclusive_strong) or any(
        re.search(rf"\b{re.escape(k)}\b", req_low) for k in ("html", "web", "dom", "react", "css", "js")
    )

    def _score(text: str, treat_canvas_as_web: bool) -> Dict[str, float]:
        sc = {"unity": 0.0, "blender": 0.0, "unreal": 0.0, "web": 0.0, "database": 0.0}
        for k in unity_keywords:
            if k in text:
                sc["unity"] += 3.5
        for k in blender_keywords:
            if k in text:
                sc["blender"] += 3.0
        for k in unreal_keywords:
            if k in text:
                sc["unreal"] += 3.0
        for k in web_exclusive_strong:
            if k in text:
                sc["web"] += 4.0
        if treat_canvas_as_web and "canvas" in text:
            sc["web"] += 4.0
        for k in web_soft:
            if re.search(rf"\b{re.escape(k)}\b", text):
                sc["web"] += 1.5
        for k in db_keywords:
            if k in text:
                sc["database"] += 2.5
        return sc

    unity_in_req = any(k in req_low for k in ("unity", ".cs", "sahne", "konsol", "derlen", "prefab", "monobehaviour"))
    canvas_is_web = (not unity_in_req and not is_unity_dir) or has_explicit_web_in_req

    req_scores = _score(req_low, treat_canvas_as_web=canvas_is_web)
    if is_unity_dir and not has_explicit_web_in_req:
        req_scores["unity"] += 4.0
    elif has_unity_ctx and not has_explicit_web_in_req and "canvas" in req_low:
        req_scores["unity"] += 4.0

    best_req = max(req_scores, key=lambda k: req_scores[k])

    if req_scores[best_req] >= 1.5:
        selected_key = best_req
    else:
        src_scores = _score(src_low, treat_canvas_as_web=not has_unity_ctx)
        combined = {k: req_scores[k] * 2.0 + src_scores[k] for k in req_scores}
        best_comb = max(combined, key=lambda k: combined[k])
        selected_key = best_comb if combined[best_comb] > 0.0 else "general"

    if selected_key in MCP_CATALOG:
        return MCP_CATALOG[selected_key]
    return MCPAppProfile(
        app_key="general",
        display_name="Genel Yazılım & Dosya Sistemi",
        is_mcp_supported=True,
        standard_package_name="@modelcontextprotocol/server-filesystem",
        installation_type="NPM",
        direct_install_target="npx -y @modelcontextprotocol/server-filesystem",
        mcp_config_snippet={
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
            }
        },
        user_guide_markdown="Genel projeler için yerleşik dosya sistemi araçları kullanılmaktadır.",
        builtin_alternative="LaSef FileSystemTools"
    )

def generate_client_mcp_config_json(active_profiles: List[MCPAppProfile], include_lasef_orchestrator: bool = True) -> Dict[str, Any]:
    """
    Claude Desktop, Cursor veya Antigravity için hazır mcpServers JSON nesnesi üretir.
    Varsayılan olarak LaSef-Orchestrator unified MCP sunucusunu da dahil eder.
    """
    import sys as _sys
    import os as _os
    servers = {}
    if include_lasef_orchestrator:
        lasef_srv = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "lasef_mcp_server.py")
        servers["lasef-orchestrator"] = {
            "command": _sys.executable,
            "args": [lasef_srv]
        }
    for p in active_profiles:
        if p.mcp_config_snippet:
            servers.update(p.mcp_config_snippet)
    return {"mcpServers": servers}
