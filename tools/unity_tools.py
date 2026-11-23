import json
from typing import Dict, Any, Optional
from tools.unity_bridge_client import unity_client

def tool_unity_status() -> str:
    """Unity Editor'ün açık olup olmadığını, derleme durumunu ve aktif sahneyi döner."""
    res = unity_client.get_status()
    if not res.get("online"):
        return f"Unity Kapalı: {res.get('error', 'Bilinmeyen hata')}"
    return (
        f"🟢 Unity Çevrimiçi\n"
        f"- Sürüm: {res.get('unity_version')}\n"
        f"- Aktif Sahne: {res.get('active_scene')}\n"
        f"- Derleme Durumu: {'Derleniyor (Kilitli)' if res.get('is_compiling') else 'Hazır (Boşta)'}\n"
        f"- Oyun Modu (PlayMode): {'Açık' if res.get('is_playing') else 'Kapalı'}\n"
        f"- Derleme Hataları: {len(res.get('compile_errors', []))} adet"
    )

def tool_unity_get_hierarchy() -> str:
    """Aktif Unity sahnesindeki tüm GameObject ağacını ve bileşenlerini listeler."""
    res = unity_client.get_hierarchy()
    if not res.get("success"):
        return f"Hata: {res.get('error', 'Hiyerarşi alınamadı.')}"
    
    nodes = res.get("nodes", [])
    if not nodes:
        return f"Sahne '{res.get('scene')}' tamamen boş."

    lines = [f"📂 Sahne: {res.get('scene')} (Toplam Kök Nesne: {res.get('root_count')})"]

    def print_node(node: dict, indent: int = 0):
        prefix = "  " * indent + "└─ "
        comps = ", ".join(node.get("components", []))
        pos = node.get("pos", {})
        pos_str = f"({pos.get('x',0)}, {pos.get('y',0)}, {pos.get('z',0)})"
        lines.append(f"{prefix}📦 {node.get('name')} [ID:{node.get('id')}] Pos:{pos_str} Bileşenler:[{comps}]")
        for child in node.get("children", []):
            print_node(child, indent + 1)

    for root in nodes:
        print_node(root, indent=0)

    return "\n".join(lines)

def tool_unity_inspect_object(target: str) -> str:
    """Belirli bir GameObject'in tüm bileşenlerini ve SerializedProperty alanlarını detaylı inceler."""
    res = unity_client.inspect_gameobject(target)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    
    lines = [f"🔍 Obje İncelemesi: '{res.get('name')}' (ID: {res.get('id')}, Tag: {res.get('tag')}, Layer: {res.get('layer')})"]
    for c in res.get("components", []):
        lines.append(f"\n  ⚙️ Bileşen: {c.get('type')}")
        for p_name, p_val in c.get("properties", {}).items():
            lines.append(f"     • {p_name} = {p_val}")
    return "\n".join(lines)

def tool_unity_create_object(
    name: str,
    primitive_type: str = "",
    parent: str = "",
    px: float = 0.0, py: float = 0.0, pz: float = 0.0,
    sx: float = 1.0, sy: float = 1.0, sz: float = 1.0
) -> str:
    """Unity sahnesinde yeni bir GameObject veya Primitif (Cube, Sphere, Plane, Capsule, Cylinder) oluşturur."""
    res = unity_client.create_gameobject(
        name=name,
        primitive_type=primitive_type or None,
        parent=parent or None,
        px=px, py=py, pz=pz,
        sx=sx, sy=sy, sz=sz
    )
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return f"Başarılı: '{res.get('name')}' (ID: {res.get('id')}) sahneye eklendi."

def tool_unity_add_component(target: str, component_name: str) -> str:
    """GameObject'e yeni bir bileşen (Rigidbody, BoxCollider, PlayerController vb.) takar."""
    res = unity_client.add_component(target, component_name)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return res.get("message", "Bileşen eklendi.")

def tool_unity_set_property(
    target: str,
    component: str,
    property_name: str,
    value: str,
    is_reference: bool = False
) -> str:
    """
    GameObject bileşeninin alanını ayarlar.
    Örnek primitive: target='Player', component='CharacterController', property_name='m_Height', value='2.0'
    Örnek referans: target='Player', component='PlayerController', property_name='groundCheck', value='Player/GroundCheck', is_reference=True
    """
    res = unity_client.set_property(target, component, property_name, value, is_reference)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return res.get("message", "Property güncellendi.")

def tool_unity_create_prefab(target: str, asset_path: str = "") -> str:
    """Sahnedeki bir GameObject'i Prefab dosyası olarak diske kaydeder (örn. Assets/Prefabs/Player.prefab)."""
    res = unity_client.create_prefab(target, asset_path or None)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return f"Başarılı: Prefab kaydedildi -> {res.get('asset_path')}"

def tool_unity_instantiate_prefab(asset_path: str, parent: str = "") -> str:
    """Diskteki bir Prefab dosyasını sahneye çağırır."""
    res = unity_client.instantiate_prefab(asset_path, parent or None)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return f"Başarılı: Prefab sahneye yerleştirildi -> '{res.get('name')}' (ID: {res.get('id')})"

def tool_unity_execute_csharp(code_snippet: str) -> str:
    """Unity Editor içinde anında C# Editor kodu çalıştırır (REPL)."""
    res = unity_client.execute_csharp(code_snippet)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return f"C# Çıktısı:\n{res.get('output')}"

def tool_unity_get_logs() -> str:
    """Unity konsolundaki son hata ve logları çeker."""
    res = unity_client.get_console_logs()
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    logs = res.get("logs", [])
    if not logs:
        return "Unity konsolu temiz (Hata yok)."
    lines = ["📋 Unity Konsol Kayıtları:"]
    for l in logs[-15:]:
        emoji = "🔴" if "error" in l.get("type","").lower() or "exception" in l.get("type","").lower() else "🟡" if "warn" in l.get("type","").lower() else "⚪"
        lines.append(f"{emoji} [{l.get('time')}] [{l.get('type')}] {l.get('message')}")
    return "\n".join(lines)

def tool_unity_wait_compile(timeout: float = 30.0) -> str:
    """Unity'nin script derlemesini beklemesini sağlar ve sonuç raporu döner."""
    res = unity_client.wait_for_compilation(timeout)
    if not res.get("success"):
        if res.get("has_errors"):
            errs = "\n".join(res.get("errors", []))
            return f"❌ Unity Derleme Hatası Var:\n{errs}"
        return f"Hata: {res.get('error')}"
    return "✅ Unity C# derlemesi başarıyla tamamlandı (Hatasız)."

def tool_unity_save_scene() -> str:
    """Aktif sahneyi diske kaydeder."""
    res = unity_client.save_scene()
    return f"Sahne Kaydedildi: {res.get('scene')}" if res.get("success") else f"Hata: {res.get('error')}"

def tool_unity_delete_object(target: str) -> str:
    """Sahnedeki bir GameObject'i siler."""
    res = unity_client.delete_gameobject(target)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return f"Başarılı: '{target}' objesi sahneden silindi."

def tool_unity_set_play_mode(play: bool = True) -> str:
    """Unity Editor'de oyun modunu (Play Mode) başlatır veya durdurur."""
    res = unity_client.set_play_mode(play)
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    durum = "Başlatıldı (Çalışıyor)" if play else "Durduruldu"
    return f"🎮 Oyun Modu {durum}."

def tool_unity_capture_screenshot(prefer_game_view: bool = True) -> Dict[str, Any]:
    """Unity Editor sahnesinden veya Game kamerasından Base64 ekran görüntüsü çeker."""
    return unity_client.capture_screenshot(prefer_game_view)

def tool_unity_clear_logs() -> str:
    """Unity konsolundaki tüm geçmiş logları ve derleme hatalarını temizler."""
    res = unity_client.clear_console_logs()
    if not res.get("success"):
        return f"Hata: {res.get('error')}"
    return "🧹 Unity konsol logları ve derleme hataları temizlendi."


def _parse_unity_scene_hierarchy_offline(
    project_root: str,
    max_objects: int = 80,
    max_scenes: int = 5
) -> str:
    """Unity Editor kapalıyken Assets/**/*.unity dosyalarından hızlıca sahne GameObject hiyerarşi özetini çıkarır."""
    import json
    import os
    import re

    assets_dir = os.path.join(project_root, "Assets")
    if not os.path.isdir(assets_dir):
        return ""

    scene_files = []
    skip_dirs = {"lasefbridge", "tutorialinfo", "textmesh pro", ".git"}
    for root_d, dirs, files in os.walk(assets_dir):
        dirs[:] = sorted(d for d in dirs if d.lower() not in skip_dirs)
        for fn in sorted(files):
            if fn.lower().endswith(".unity"):
                scene_files.append(os.path.join(root_d, fn))
                if len(scene_files) >= max_scenes:
                    break
        if len(scene_files) >= max_scenes:
            break

    sections = []
    for sp in scene_files:
        rel_scene = os.path.relpath(sp, project_root).replace("\\", "/")
        objects = []
        seen_names = {}
        try:
            with open(sp, "r", encoding="utf-8", errors="ignore") as f:
                in_go = False
                lines_in_go = 0
                cur_name = None
                cur_active = "1"
                bytes_read = 0
                for line in f:
                    bytes_read += len(line)
                    if bytes_read > 524288 or len(objects) >= max_objects:
                        break
                    if line.startswith("--- !u!1 &"):
                        if in_go and cur_name:
                            objects.append((cur_name, cur_active != "0"))
                        in_go = True
                        lines_in_go = 0
                        cur_name = None
                        cur_active = "1"
                        continue
                    if in_go:
                        if line.startswith("--- !u!"):
                            if cur_name:
                                objects.append((cur_name, cur_active != "0"))
                            in_go = False
                            continue
                        lines_in_go += 1
                        if lines_in_go > 30:
                            if cur_name:
                                objects.append((cur_name, cur_active != "0"))
                            in_go = False
                            continue
                        m_name = re.match(r"^\s*m_Name:\s*(.+?)\s*$", line)
                        if m_name:
                            cur_name = m_name.group(1).strip().strip('"').strip("'")
                        m_act = re.match(r"^\s*m_IsActive:\s*(\d+)\s*$", line)
                        if m_act:
                            cur_active = m_act.group(1)
                if in_go and cur_name and len(objects) < max_objects:
                    objects.append((cur_name, cur_active != "0"))
        except Exception:
            continue

        if objects:
            formatted = []
            for name, active in objects:
                cnt = seen_names.get(name, 0) + 1
                seen_names[name] = cnt
                if cnt > 2:
                    continue
                tag = "" if active else " (pasif)"
                formatted.append(f"  • {name}{tag}")
            extra = len(objects) - len(formatted)
            body = "\n".join(formatted[:45])
            if len(formatted) > 45 or extra > 0:
                body += f"\n  ... (toplam {len(objects)}+ GameObject)"
            sections.append(f"📄 Sahne [{rel_scene}]:\n{body}")
        else:
            sections.append(f"📄 Sahne [{rel_scene}]: (Boş veya ikili/metin dışı)")

    manifest_p = os.path.join(project_root, "Packages", "manifest.json")
    if os.path.isfile(manifest_p):
        try:
            with open(manifest_p, "r", encoding="utf-8", errors="ignore") as mf:
                mdata = json.load(mf)
            deps = list((mdata.get("dependencies") or {}).keys())
            onemli = [d for d in deps if not d.startswith("com.unity.modules.")]
            if onemli:
                sections.append("📦 Aktif Unity Paketleri (manifest.json): " + ", ".join(onemli[:20]))
        except Exception:
            pass

    return "\n\n".join(sections)


def parse_unity_project_symbols(project_root: str) -> Dict[str, Any]:
    """
    Projedeki tüm Assets/**/*.cs dosyalarını (Scripts + Editor) tarayarak
    her dosyanın gerçek namespace'ini, sınıf/enum bildirimlerini ve public API imzalarını çıkarır.
    """
    import os
    import re

    assets_dir = os.path.join(project_root, "Assets") if project_root else ""
    if not assets_dir or not os.path.isdir(assets_dir):
        return {"files": {}, "namespace_split": False, "duplicate_types": {}}

    skip_dirs = {"lasefbridge", "tutorialinfo", "textmesh pro", ".git"}
    files_info: Dict[str, Dict[str, Any]] = {}
    type_locations: Dict[str, list] = {}
    namespaces_seen = set()

    for root_d, dirs, files in os.walk(assets_dir):
        dirs[:] = sorted(d for d in dirs if d.lower() not in skip_dirs)
        for fn in sorted(files):
            if not fn.endswith(".cs") or fn.startswith("LaSefDynamicRunner_"):
                continue
            fp = os.path.join(root_d, fn)
            rel_p = os.path.relpath(fp, project_root).replace("\\", "/")
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            ns_matches = re.findall(r"^\s*namespace\s+([\w\.]+)", content, flags=re.MULTILINE)
            ns_label = ns_matches[0] if ns_matches else "<global>"
            namespaces_seen.add(ns_label)

            decls = []
            members = []
            depth = 0
            ns_depth = None
            outer_class = None
            outer_class_depth = None

            for line in content.splitlines():
                s = line.strip()
                if not s or s.startswith("//") or s.startswith("/*") or s.startswith("*"):
                    continue

                if re.match(r"^namespace\s+[\w\.]+", s):
                    ns_depth = depth + (1 if "{" in s else 0)

                m_type = re.match(
                    r"^(?:public|internal)\s+(?:static\s+|abstract\s+|sealed\s+|partial\s+)?(class|struct|interface|enum)\s+(\w+)(.*)$",
                    s,
                )
                if m_type:
                    t_kind, t_name, t_rest = m_type.groups()
                    in_outer = outer_class is not None and outer_class_depth is not None and depth >= outer_class_depth
                    qualified = f"{outer_class}.{t_name}" if in_outer else t_name
                    if ns_label != "<global>":
                        full_qualified = f"{ns_label}.{qualified}"
                    else:
                        full_qualified = qualified
                    decls.append(f"{t_kind} {full_qualified}{t_rest.split('{')[0].strip()[:40]}")
                    type_locations.setdefault(qualified, []).append((rel_p, ns_label))
                    if t_kind in ("class", "struct") and not in_outer:
                        outer_class = t_name
                        outer_class_depth = depth + (1 if "{" in s else 1)
                elif any(
                    s.startswith(p)
                    for p in ("public ", "public static ", "public enum ", "public Action", "public UnityEvent", "[SerializeField]")
                ):
                    clean_sig = s.split("{")[0].strip() if ("(" in s and not s.startswith("public enum")) else s
                    if len(members) < 25:
                        members.append(clean_sig[:110])

                depth += line.count("{") - line.count("}")
                if outer_class_depth is not None and depth < outer_class_depth:
                    outer_class = None
                    outer_class_depth = None

            files_info[rel_p] = {
                "namespace": ns_label,
                "size": len(content),
                "decls": decls,
                "members": members,
            }

    duplicate_types = {t: locs for t, locs in type_locations.items() if len(locs) > 1}
    namespace_split = len(namespaces_seen) > 1
    return {
        "files": files_info,
        "namespaces_seen": sorted(namespaces_seen),
        "namespace_split": namespace_split,
        "duplicate_types": duplicate_types,
    }


def format_unity_project_symbol_index(
    project_root: str,
    exclude_file: str = "",
    max_chars: int = 9000,
) -> str:
    """Tüm Unity C# scriptlerinin namespace + sınıf + public API özetini üretir."""
    import os

    parsed = parse_unity_project_symbols(project_root)
    files_info = parsed.get("files", {})
    if not files_info:
        return ""

    exclude_base = os.path.basename(exclude_file) if exclude_file else ""
    lines = ["🗺️ [PROJE C# SEMBOL & NAMESPACE HARİTASI (Assets/Scripts + Assets/Editor)]:"]

    if parsed.get("namespace_split"):
        ns_groups: Dict[str, list] = {}
        for rp, info in files_info.items():
            ns_groups.setdefault(info["namespace"], []).append(os.path.basename(rp))
        lines.append("⚠️ KRİTİK NAMESPACE UYUMSUZLUĞU TESPİT EDİLDİ (CS0246/CS0234 Kök Nedeni!):")
        for ns_n, f_list in ns_groups.items():
            lines.append(f"  - {ns_n}: {', '.join(f_list[:15])}")
        lines.append("  -> KURAL: Projede 'namespace Global' kullanan dosyalar ile global alandaki dosyalar birbirini göremez; namespace'leri ya tamamen global alana (namespace bloğu olmadan) birleştir ya da uygun 'using <Namespace>;' / tam ad kullan!")

    dups = parsed.get("duplicate_types", {})
    if dups:
        lines.append("⚠️ ÇAKIŞAN TİP/ENUM TANIMLARI (CS0101 Kök Nedeni!):")
        for t_name, locs in list(dups.items())[:8]:
            loc_str = ", ".join(f"{rp} ({ns})" for rp, ns in locs)
            lines.append(f"  - '{t_name}' birden fazla dosyada tanımlı: {loc_str}")

    for rp, info in sorted(files_info.items()):
        if exclude_base and os.path.basename(rp) == exclude_base:
            continue
        ns_tag = f"ns={info['namespace']}"
        decl_str = " | ".join(info["decls"][:5]) if info["decls"] else "(tip bulunamadı)"
        lines.append(f"• {rp} [{ns_tag}, {info['size']}B]: {decl_str}")
        for m in info["members"][:10]:
            lines.append(f"    {m}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [Sembol haritası sınırlandırıldı]"
    return text


def collect_unity_diagnostics_summary(
    project_root: str = "",
    connected: bool = False,
    max_chars: int = 4500,
) -> str:
    """Canlı Unity konsol hataları/uyarıları ve yerel Roslyn derleme hatalarını/uyarılarını toplar."""
    sections = []

    if connected:
        try:
            st = unity_client.get_status()
            comp_errs = [
                e for e in (st.get("compile_errors") or [])
                if "LaSefDynamicRunner_" not in e and "LaSefBridge" not in e
            ]
            if comp_errs:
                sections.append("🔴 [CANLI UNITY DERLEME HATALARI]:\n" + "\n".join(f"  • {e}" for e in comp_errs[:15]))
        except Exception:
            pass

        try:
            logs_res = unity_client.get_console_logs()
            logs = logs_res.get("logs", []) if isinstance(logs_res, dict) else []
            err_counts: Dict[str, int] = {}
            err_stacks: Dict[str, str] = {}
            warn_counts: Dict[str, int] = {}
            for l in logs:
                msg = (l.get("message") or "").strip()
                ltype = (l.get("type") or "").lower()
                st_trace = (l.get("stackTrace") or "").strip()
                if not msg:
                    continue
                if "error" in ltype or "exception" in ltype or "assert" in ltype:
                    err_counts[msg] = err_counts.get(msg, 0) + 1
                    if msg not in err_stacks and st_trace:
                        err_stacks[msg] = " | ".join(st_trace.splitlines()[:3])
                elif "warn" in ltype:
                    warn_counts[msg] = warn_counts.get(msg, 0) + 1

            if err_counts:
                e_lines = [f"🔴 [CANLI UNITY KONSOL HATALARI ({sum(err_counts.values())} kayıt)]:"]
                for m, cnt in list(err_counts.items())[:12]:
                    stack_s = f"\n      Stack: {err_stacks[m]}" if m in err_stacks else ""
                    e_lines.append(f"  • (x{cnt}) {m[:260]}{stack_s}")
                sections.append("\n".join(e_lines))
            if warn_counts:
                w_lines = [f"🟡 [CANLI UNITY KONSOL UYARILARI ({sum(warn_counts.values())} kayıt)]:"]
                for m, cnt in list(warn_counts.items())[:10]:
                    w_lines.append(f"  • (x{cnt}) {m[:220]}")
                sections.append("\n".join(w_lines))
        except Exception:
            pass

    if project_root:
        try:
            local_res = unity_client.compile_project_locally_with_dotnet(project_root)
            if local_res.get("supported"):
                errs = local_res.get("errors", [])
                warns = local_res.get("warnings", [])
                if errs:
                    sections.append(
                        f"🔴 [ROSLYN (dotnet build) DERLEME HATALARI ({len(errs)} adet)]:\n"
                        + "\n".join(f"  • {e}" for e in errs[:20])
                    )
                if warns:
                    sections.append(
                        f"🟡 [ROSLYN DERLEME UYARILARI ({len(warns)} adet)]:\n"
                        + "\n".join(f"  • {w}" for w in warns[:15])
                    )
        except Exception:
            pass

    out = "\n\n".join(sections)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n... [Tanı listesi kırpıldı]"
    return out


def tool_unity_collect_hierarchy_context(project_roots: Any = None, max_chars: int = 15000) -> str:
    """
    Orkestra başlangıcında Unity durumunu, gerçek konsol/derleme hatalarını, canlı hiyerarşiyi
    ve tüm C# sınıflarının namespace/sembol haritasını bağlamın en tepesine hazırlar.
    """
    import os

    if isinstance(project_roots, str):
        roots = [project_roots]
    elif isinstance(project_roots, (list, tuple, set)):
        roots = [str(r) for r in project_roots if r]
    else:
        roots = []

    unity_roots = []
    for r in roots:
        cand = os.path.abspath(r)
        if os.path.isfile(cand):
            cand = os.path.dirname(cand)
        if os.path.isdir(os.path.join(cand, "Assets")) and cand not in unity_roots:
            unity_roots.append(cand)

    try:
        connected = unity_client.is_connected()
    except Exception:
        connected = False

    primary_root = unity_roots[0] if unity_roots else ""
    diag_blok = collect_unity_diagnostics_summary(primary_root, connected=connected, max_chars=4500)
    sym_blok = format_unity_project_symbol_index(primary_root, max_chars=5500) if primary_root else ""

    if connected:
        print("🎮 [Unity Bağlam]: Port 8088 MCP Bridge bağlı — canlı sahne hiyerarşisi, konsol logları ve sembol haritası çekiliyor...")
        durum = tool_unity_status()
        hiyerarsi = tool_unity_get_hierarchy()
        parcalar = [
            "🎮 ════════ [0. CANLI UNITY EDİTÖR DURUMU & HİYERARŞİ (PORT 8088)] ════════",
            durum,
        ]
        if diag_blok:
            parcalar.append(diag_blok)
        parcalar.append(hiyerarsi)
        if sym_blok:
            parcalar.append(sym_blok)
        blok = "\n\n".join(parcalar)
        if len(blok) > max_chars:
            blok = blok[:max_chars] + "\n... [Canlı hiyerarşi bağlam sınırına göre kırpıldı]"
        return blok

    if unity_roots:
        ozetler = []
        for ur in unity_roots[:2]:
            ozet = _parse_unity_scene_hierarchy_offline(ur)
            if ozet:
                ozetler.append(f"📁 Proje: {os.path.basename(ur)}\n{ozet}")
        parcalar = [
            "🎮 ════════ [0. UNITY SAHNE HİYERARŞİSİ & PROJE DURUMU (ÇEVRİMDIŞI)] ════════\n"
            "(Not: Unity Editor Köprüsü Port 8088 şu an bağlı değil; aşağıdaki veriler diskten ve Roslyn'den çıkarıldı.)"
        ]
        if diag_blok:
            parcalar.append(diag_blok)
        if ozetler:
            parcalar.append("\n\n".join(ozetler))
        if sym_blok:
            parcalar.append(sym_blok)
        if len(parcalar) > 1:
            print("🎮 [Unity Bağlam]: Unity Bridge çevrimdışı — .unity sahne dosyaları ve C# sembol haritası çıkarıldı.")
            blok = "\n\n".join(parcalar)
            if len(blok) > max_chars:
                blok = blok[:max_chars] + "\n... [Hiyerarşi özeti kırpıldı]"
            return blok

    return ""

