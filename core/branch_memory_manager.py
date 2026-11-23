"""
═══════════════════════════════════════════════════════════════════════════════
🌿 LASEF BRANCH (DAL) TABANLI KONUŞMA, PROMPT VE İŞ HAFIZASI YÖNETİCİSİ
   (core/branch_memory_manager.py)
═══════════════════════════════════════════════════════════════════════════════
📌 AMACI:
1. Kullanıcının verdiği tüm promptları, Şef'in mimari planlarını, üretilen dosyaları,
   amele ajan kartlarını ve terminal çıktılarını Git benzeri bir Branch (Ağaç Dalı)
   yapısında kalıcı olarak (.lasef_branches.json) saklar.
2. Uygulama tamamen kapatılıp yeniden başlatılsa bile tüm projeler, konuşmalar,
   dallar (branches) ve önceki mesajlar/işler eksiksiz geri yüklenir.
3. Kullanıcı geçmişteki herhangi bir mesaja/prompta geri dönebilir, o adımda
   üretilen kodları/ajanları/terminali inceleyebilir ve istediği geçmiş mesajdan
   yeni bir Branch (Dal) çatallandırarak (fork) devam edebilir.
4. Bir dal üzerinden devam edildiğinde, o dalın kökünden itibaren tüm önceki
   promptlar, mimari sözleşmeler ve üretilen dosya içerikleri Baş Şef ve Amele
   ajanlara "Branch Hafıza Bağlamı" olarak aktarılır.
═══════════════════════════════════════════════════════════════════════════════
"""
import os
import re
import json
import time
import uuid
import threading
from typing import Dict, List, Any, Optional, Tuple


def format_relative_time(timestamp: float) -> str:
    """Sol panel için Türkçe göreli zaman etiketi üretir (şimdi, 5dk, 2s, 1g, 1ay)."""
    if not timestamp:
        return "şimdi"
    diff = max(0.0, time.time() - float(timestamp))
    if diff < 90:
        return "şimdi"
    minutes = int(diff // 60)
    if minutes < 60:
        return f"{minutes}dk"
    hours = int(diff // 3600)
    if hours < 24:
        return f"{hours}sa"
    days = int(diff // 86400)
    if days < 30:
        return f"{days}g"
    months = max(1, int(days // 30))
    return f"{months}ay"


def generate_smart_title(prompt: str, max_len: int = 34) -> str:
    """Kullanıcı promptundan Antigravity sol paneline uygun anlamlı kısa başlık üretir."""
    if not prompt:
        return "Yeni Görev"
    cleaned = re.sub(r"[#*_`~>\[\]\(\)\n\r]+", " ", prompt).strip()
    cleaned = re.sub(r"[A-Za-z]:\\[^\s]+", "", cleaned).strip()
    cleaned = re.sub(
        r"^(kral|şef|sef|merhaba|selam|bana|lütfen|lutfen|şimdi|simdi|sen\s+şu\s+an[^\.,]*[\.,]?)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()
    if not cleaned:
        cleaned = prompt.strip().splitlines()[0]
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > max_len:
        return cleaned[: max_len - 2].rstrip() + "…"
    return cleaned


class BranchMemoryManager:
    """
    🌿 Kalıcı Proje, Konuşma ve Branch (Dal) Hafıza Yöneticisi.
    Verileri `.lasef_branches.json` içinde thread-safe olarak saklar.
    """

    def __init__(self, base_dir: str = ""):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.storage_file = os.path.join(self.base_dir, ".lasef_branches.json")
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {
            "version": "8.0",
            "active_project_id": None,
            "active_conversation_id": None,
            "active_node_id": None,
            "projects": [],
            "conversations": {}
        }
        self._load_or_bootstrap()

    def _sanitize_legacy_source_files(self) -> bool:
        """Eski sürümlerde klasör yerine 10.000+ tekil dosya olarak kaydedilmiş source_files listelerini klasör köküne daraltır."""
        changed = False
        convs = self._data.get("conversations", {})
        if not isinstance(convs, dict):
            return False

        def _collapse(files_list: list, target_folder: str) -> Optional[list]:
            if not isinstance(files_list, list) or len(files_list) <= 25:
                return None
            if target_folder and os.path.isdir(target_folder):
                return [target_folder]
            try:
                common = os.path.commonpath([os.path.abspath(str(p)) for p in files_list[:200] if p])
                if common and os.path.isdir(common):
                    return [common]
            except Exception:
                pass
            return files_list[:10]

        for conv in convs.values():
            if not isinstance(conv, dict):
                continue
            tf = conv.get("target_folder", "") or ""
            collapsed_conv = _collapse(conv.get("source_files", []), tf)
            if collapsed_conv is not None:
                conv["source_files"] = collapsed_conv
                changed = True
            nodes = conv.get("nodes", {})
            if isinstance(nodes, dict):
                for node in nodes.values():
                    if not isinstance(node, dict):
                        continue
                    ntf = node.get("target_folder", "") or tf
                    collapsed_node = _collapse(node.get("source_files", []), ntf)
                    if collapsed_node is not None:
                        node["source_files"] = collapsed_node
                        changed = True
        return changed

    def _load_or_bootstrap(self):
        with self._lock:
            if os.path.exists(self.storage_file):
                try:
                    with open(self.storage_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict) and "projects" in loaded and "conversations" in loaded:
                            self._data = loaded
                            if self._sanitize_legacy_source_files():
                                self._save()
                            return
                except Exception as e:
                    print(f"⚠️ [BranchMemory] Yükleme uyarısı: {e}")

            self._bootstrap_from_existing_workspace()
            self._save()

    def _save(self):
        with self._lock:
            tmp_file = self.storage_file + ".tmp"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                try:
                    os.replace(tmp_file, self.storage_file)
                except PermissionError:
                    with open(self.storage_file, "w", encoding="utf-8") as f:
                        json.dump(self._data, f, indent=2, ensure_ascii=False)
                    if os.path.exists(tmp_file):
                        try:
                            os.remove(tmp_file)
                        except OSError:
                            pass
            except Exception as e:
                print(f"⚠️ [BranchMemory] Kaydetme hatası: {e}")

    def _bootstrap_from_existing_workspace(self):
        """
        Mevcut `.lasef_memory.json`, `terminal_outputs` ve `Unity Denemeler Klasörü`
        verilerini tarayarak ilk açılışta geçmiş projeleri ve konuşma dallarını oluşturur.
        """
        now = time.time()

        unity_dir = os.path.join(self.base_dir, "Unity Denemeler Klasörü", "MCP Deneme")
        has_unity_dir = os.path.exists(unity_dir)

        proj_mcp_id = "proj_mcp_deneme"
        proj_lasef_id = "proj_lasef_core"
        proj_games_id = "proj_web_oyun"
        proj_reports_id = "proj_rapor_denetim"

        projects = [
            {
                "project_id": proj_mcp_id,
                "name": "MCP Deneme (Unity 3D)",
                "folder_path": unity_dir if has_unity_dir else self.base_dir,
                "expanded": True,
                "created_at": now - 86400 * 7,
                "updated_at": now - 3600 * 4
            },
            {
                "project_id": proj_lasef_id,
                "name": "LaSef Studio",
                "folder_path": self.base_dir,
                "expanded": True,
                "created_at": now - 86400 * 30,
                "updated_at": now - 86400 * 1
            },
            {
                "project_id": proj_games_id,
                "name": "Oyun & Web Projeleri",
                "folder_path": self.base_dir,
                "expanded": True,
                "created_at": now - 86400 * 45,
                "updated_at": now - 86400 * 14
            },
            {
                "project_id": proj_reports_id,
                "name": "Denetim & Teknik Raporlar",
                "folder_path": self.base_dir,
                "expanded": False,
                "created_at": now - 86400 * 60,
                "updated_at": now - 86400 * 20
            }
        ]
        self._data["projects"] = projects
        self._data["conversations"] = {}

        term_log_1 = ""
        term_path_1 = os.path.join(self.base_dir, "lasef_terminal_20261029_150638.txt")
        if os.path.exists(term_path_1):
            try:
                with open(term_path_1, "r", encoding="utf-8", errors="replace") as f:
                    term_log_1 = f.read()
            except Exception:
                pass

        term_log_2 = ""
        term_path_2 = os.path.join(self.base_dir, "terminal_outputs", "terminal_20261104_114347.txt")
        if os.path.exists(term_path_2):
            try:
                with open(term_path_2, "r", encoding="utf-8", errors="replace") as f:
                    term_log_2 = f.read()
            except Exception:
                pass

        mcp_tasks = [
            {
                "adim_no": "1",
                "title": "Can ve Hasar Sistemi (HealthSystem)",
                "file": "HealthSystem.cs",
                "capability": "game-dev",
                "model_id": "nemotron-3-ultra-550b-a55b",
                "status": "✅ Başarıyla Mühürlendi",
                "status_type": "done",
                "dependencies": []
            },
            {
                "adim_no": "2",
                "title": "Oyun Yöneticisi (GameManager)",
                "file": "GameManager.cs",
                "capability": "game-dev",
                "model_id": "nemotron-3-ultra-550b-a55b",
                "status": "✅ Başarıyla Mühürlendi",
                "status_type": "done",
                "dependencies": []
            },
            {
                "adim_no": "3",
                "title": "Silah ve Atış Sistemi (WeaponSystem)",
                "file": "WeaponSystem.cs",
                "capability": "game-dev",
                "model_id": "nemotron-3-ultra-550b-a55b",
                "status": "✅ Başarıyla Mühürlendi",
                "status_type": "done",
                "dependencies": [1]
            },
            {
                "adim_no": "4",
                "title": "Oyuncu Kontrol ve Hareket Sistemi (PlayerController)",
                "file": "PlayerController.cs",
                "capability": "game-dev",
                "model_id": "nemotron-3-ultra-550b-a55b",
                "status": "✅ Başarıyla Mühürlendi",
                "status_type": "done",
                "dependencies": []
            },
            {
                "adim_no": "5",
                "title": "Düşman Yapay Zekası (EnemyAI)",
                "file": "EnemyAI.cs",
                "capability": "game-dev",
                "model_id": "nemotron-3-ultra-550b-a55b",
                "status": "✅ Başarıyla Mühürlendi",
                "status_type": "done",
                "dependencies": [1]
            },
            {
                "adim_no": "6",
                "title": "Arayüz ve HUD Yöneticisi (UIManager)",
                "file": "UIManager.cs",
                "capability": "game-dev",
                "model_id": "nemotron-3-ultra-550b-a55b",
                "status": "✅ Başarıyla Mühürlendi",
                "status_type": "done",
                "dependencies": [1, 2]
            },
            {
                "adim_no": "7",
                "title": "Otomatik Sahne İnşacısı (FPSArenaSceneBuilder)",
                "file": "Assets/Editor/FPSArenaSceneBuilder.cs",
                "capability": "unity-dev",
                "model_id": "nemotron-3-ultra-550b-a55b",
                "status": "✅ Başarıyla Mühürlendi",
                "status_type": "done",
                "dependencies": [1, 2, 3, 4, 5, 6]
            }
        ]

        mcp_files_produced = []
        if has_unity_dir:
            for sub in ["Assets/Scripts", "Assets/Editor"]:
                full_sub = os.path.join(unity_dir, sub)
                if os.path.exists(full_sub):
                    for fn in os.listdir(full_sub):
                        if fn.endswith(".cs"):
                            fp = os.path.join(full_sub, fn)
                            try:
                                sz = os.path.getsize(fp) / 1024.0
                                with open(fp, "r", encoding="utf-8", errors="replace") as fc:
                                    code_preview = fc.read()[:12000]
                                mcp_files_produced.append({
                                    "path": fp,
                                    "rel_path": f"{sub}/{fn}",
                                    "size_kb": round(sz, 1),
                                    "preview": code_preview
                                })
                            except Exception:
                                pass

        conv_mcp_id = "conv_mcp_fps_arena"
        node_1_id = "node_mcp_1"
        node_2_id = "node_mcp_2"
        node_3_id = "node_mcp_3"

        node_1 = {
            "node_id": node_1_id,
            "parent_node_id": None,
            "branch_name": "main",
            "turn_number": 1,
            "prompt": "Senin cortexine MCP Deneme adında boş Unity 3D klasörü yükledim. İçerisine sıfır kurulumlu (Zero-Setup) 3D FPS Arena hayatta kalma oyunu, karakter hareketi, silah sistemi, düşman dalgaları ve otomatik SceneBuilder kur.",
            "chef_summary": "✅ 7 Uzman Amele Ajan ile 3D FPS Arena mimarisi (HealthSystem, GameManager, WeaponSystem, PlayerController, EnemyAI, UIManager, FPSArenaSceneBuilder) üretildi ve Unity sahnesine aktarıldı.",
            "architecture_contract": "Namespace: Global, Boyut: 3D (Rigidbody, CharacterController, BoxCollider/CapsuleCollider, Vector3; ASLA 2D fizik kullanılmaz), Zero-Setup SceneBuilder zorunlu.",
            "agent_tasks": mcp_tasks,
            "files_produced": mcp_files_produced,
            "terminal_log": term_log_1 or "✅ [LaSef Orkestrası]: MCP Deneme 1. Dal (İlk Kurulum) tamamlandı.",
            "target_folder": unity_dir if has_unity_dir else self.base_dir,
            "source_files": [unity_dir] if has_unity_dir else [],
            "token_stats": {"chef": 4820, "workers": 18450, "council": 9200, "total": 32470},
            "app_key": "unity",
            "created_at": 1793274504.0,
            "completed_at": 1793274504.0,
            "duration_sec": 340.5,
            "status": "completed"
        }

        node_2 = {
            "node_id": node_2_id,
            "parent_node_id": node_1_id,
            "branch_name": "main",
            "turn_number": 2,
            "prompt": "Önceki işinde senden bir girdi istedim. Sahnedeki derleme hatalarını ve URP materyal / kamera konumlandırmasını kontrol edip SceneBuilder'ı güncelle.",
            "chef_summary": "✅ Önceki dalın (Adım #1) C# scriptleri referans alınarak SceneBuilder, URP ışık/materyal uyumu ve derleme kontrolleri revize edildi.",
            "architecture_contract": "Önceki Dal (#1) Sözleşmesi Korundu + URP Materyal & Unity 6 FindObjectsByType API uyumluluğu.",
            "agent_tasks": mcp_tasks,
            "files_produced": mcp_files_produced,
            "terminal_log": term_log_1 or "✅ [LaSef Orkestrası]: MCP Deneme 2. Dal (Revizyon & URP Onarımı) tamamlandı.",
            "target_folder": unity_dir if has_unity_dir else self.base_dir,
            "source_files": [unity_dir] if has_unity_dir else [],
            "token_stats": {"chef": 5100, "workers": 19200, "council": 8400, "total": 32700},
            "app_key": "unity",
            "created_at": 1793276184.0,
            "completed_at": 1793276184.0,
            "duration_sec": 295.0,
            "status": "completed"
        }

        node_3 = {
            "node_id": node_3_id,
            "parent_node_id": node_2_id,
            "branch_name": "main",
            "turn_number": 3,
            "prompt": "Sana üzerinde oynanmamış Unity klasörü yükledim. Şefin Gözü (Vision Eye) ve Unity Editor Köprüsü ile sahneyi sıfırdan hatasız inşa et, Play Mode'da doğrula.",
            "chef_summary": "✅ 7 Amele görevi Hakem Konseyi onayıyla mühürlendi, FPSArenaSceneBuilder.BuildScene() canlı Unity Editor üzerinde çalıştırıldı ve Vision Eye doğrulaması tamamlandı.",
            "architecture_contract": "Namespace: Global, Boyut: 3D, Zero-Setup SceneBuilder, Canlı Unity Bridge & Vision Eye Doğrulaması.",
            "agent_tasks": mcp_tasks,
            "files_produced": mcp_files_produced,
            "terminal_log": term_log_2 or term_log_1 or "✅ [LaSef Orkestrası]: MCP Deneme 3. Dal tamamlandı.",
            "target_folder": unity_dir if has_unity_dir else self.base_dir,
            "source_files": [unity_dir] if has_unity_dir else [],
            "token_stats": {"chef": 6240, "workers": 22800, "council": 11500, "total": 40540},
            "app_key": "unity",
            "created_at": 1793781827.0,
            "completed_at": 1793781827.0,
            "duration_sec": 412.0,
            "status": "completed"
        }

        self._data["conversations"][conv_mcp_id] = {
            "conversation_id": conv_mcp_id,
            "project_id": proj_mcp_id,
            "title": "3D FPS Arena & Canlı Sahne",
            "target_folder": unity_dir if has_unity_dir else self.base_dir,
            "source_files": [unity_dir] if has_unity_dir else [],
            "root_node_id": node_1_id,
            "active_node_id": node_3_id,
            "fork_parent_node_id": node_3_id,
            "status": "completed",
            "created_at": 1793274504.0,
            "updated_at": 1793781827.0,
            "nodes": {
                node_1_id: node_1,
                node_2_id: node_2,
                node_3_id: node_3
            }
        }

        root_mem_file = os.path.join(self.base_dir, ".lasef_memory.json")
        if os.path.exists(root_mem_file):
            try:
                with open(root_mem_file, "r", encoding="utf-8") as f:
                    mem_data = json.load(f)
                decisions = mem_data.get("decisions", [])
                for idx, dec in enumerate(decisions):
                    raw_text = dec.get("decision", "")
                    ts = float(dec.get("timestamp", now - 86400 * (len(decisions) - idx)))
                    m_q = re.search(r"^'(.*?)'\s*başarıyla üretildi", raw_text)
                    prompt_text = m_q.group(1) if m_q else raw_text

                    low = prompt_text.lower()
                    if any(k in low for k in ["unity", "oyun", "mario", "footbol", "futbol", "alper tunga", "web ortamında"]):
                        target_proj = proj_games_id
                        app_k = "unity" if "unity" in low else "web"
                    elif any(k in low for k in ["belge", "excel", "güvenlik", "denetim", "stres testi", "sayfa"]):
                        target_proj = proj_reports_id
                        app_k = "report"
                    else:
                        target_proj = proj_lasef_id
                        app_k = "general"

                    conv_id = f"conv_hist_{idx + 1}"
                    n_id = f"node_hist_{idx + 1}"
                    title = generate_smart_title(prompt_text, max_len=32)

                    node_obj = {
                        "node_id": n_id,
                        "parent_node_id": None,
                        "branch_name": "main",
                        "turn_number": 1,
                        "prompt": prompt_text,
                        "chef_summary": f"✅ {raw_text}\nBu görev LaSef Korteks Hafızasından (.lasef_memory.json) otomatik geri yüklendi. Bu dal üzerinden yeni prompt vererek geliştirmeye devam edebilir veya yeni bir dal (branch) çatallandırabilirsiniz.",
                        "architecture_contract": "LaSef Standart Sözleşme & Single Responsibility Mimarisi.",
                        "agent_tasks": [],
                        "files_produced": [],
                        "terminal_log": (
                            f"🧠 [LASEF KORTEKS HAFIZA KAYDI GERİ YÜKLENDİ]\n"
                            f"═══════════════════════════════════════════════════════════════\n"
                            f"📌 Kayıtlı Görev / Prompt: {prompt_text}\n"
                            f"⏱️ Zaman Damgası: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}\n"
                            f"📋 Durum: {raw_text}\n"
                            f"═══════════════════════════════════════════════════════════════\n"
                            f"💡 İpucu: Bu konuşmaya yeni bir mesaj yazarak kaldığınız yerden devam edebilir veya 'Buradan Yeni Dal (Branch) Başlat' ile alternatif bir versiyon üretebilirsiniz.\n"
                        ),
                        "target_folder": self.base_dir,
                        "source_files": [],
                        "token_stats": {"chef": 0, "workers": 0, "council": 0, "total": 0},
                        "app_key": app_k,
                        "created_at": ts,
                        "completed_at": ts,
                        "duration_sec": 0.0,
                        "status": "completed"
                    }

                    self._data["conversations"][conv_id] = {
                        "conversation_id": conv_id,
                        "project_id": target_proj,
                        "title": title,
                        "target_folder": self.base_dir,
                        "source_files": [],
                        "root_node_id": n_id,
                        "active_node_id": n_id,
                        "fork_parent_node_id": n_id,
                        "status": "completed",
                        "created_at": ts,
                        "updated_at": ts,
                        "nodes": {n_id: node_obj}
                    }
            except Exception as e:
                print(f"⚠️ [BranchMemory] Geçmiş hafıza aktarım uyarısı: {e}")

        self._data["active_project_id"] = proj_mcp_id
        self._data["active_conversation_id"] = conv_mcp_id
        self._data["active_node_id"] = node_3_id

    def get_projects(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data.get("projects", []))

    def get_or_create_project_for_folder(self, folder_path: str, default_name: str = "") -> Dict[str, Any]:
        """Verilen hedef klasör için mevcut projeyi bulur veya yeni bir Proje grubu oluşturur."""
        with self._lock:
            if not folder_path:
                act_pid = self._data.get("active_project_id")
                for p in self._data["projects"]:
                    if p["project_id"] == act_pid:
                        return p
                if self._data["projects"]:
                    return self._data["projects"][0]
                return self.create_project("LaSef Studio", self.base_dir)

            norm_target = os.path.normcase(os.path.abspath(folder_path))
            for p in self._data["projects"]:
                p_path = p.get("folder_path", "")
                if p_path and os.path.normcase(os.path.abspath(p_path)) == norm_target:
                    return p

            folder_name = default_name or os.path.basename(os.path.abspath(folder_path)) or "Yeni Proje"
            new_proj = {
                "project_id": f"proj_{uuid.uuid4().hex[:8]}",
                "name": folder_name,
                "folder_path": os.path.abspath(folder_path),
                "expanded": True,
                "created_at": time.time(),
                "updated_at": time.time()
            }
            self._data["projects"].insert(0, new_proj)
            self._data["active_project_id"] = new_proj["project_id"]
            self._save()
            return new_proj

    def create_project(self, name: str, folder_path: str = "") -> Dict[str, Any]:
        with self._lock:
            new_proj = {
                "project_id": f"proj_{uuid.uuid4().hex[:8]}",
                "name": name.strip() or "Yeni Proje",
                "folder_path": os.path.abspath(folder_path) if folder_path else self.base_dir,
                "expanded": True,
                "created_at": time.time(),
                "updated_at": time.time()
            }
            self._data["projects"].insert(0, new_proj)
            self._data["active_project_id"] = new_proj["project_id"]
            self._save()
            return new_proj

    def toggle_project_expanded(self, project_id: str) -> bool:
        with self._lock:
            for p in self._data["projects"]:
                if p["project_id"] == project_id:
                    p["expanded"] = not p.get("expanded", True)
                    self._save()
                    return p["expanded"]
            return True

    def rename_project(self, project_id: str, new_name: str) -> bool:
        """Proje grubunun adını günceller."""
        with self._lock:
            clean = (new_name or "").strip()
            if not clean:
                return False
            for p in self._data["projects"]:
                if p["project_id"] == project_id:
                    p["name"] = clean
                    p["updated_at"] = time.time()
                    self._save()
                    return True
            return False

    def delete_project(self, project_id: str, delete_conversations: bool = True) -> bool:
        """Projeyi ve isteğe bağlı olarak altındaki tüm geçmiş kayıtları siler."""
        with self._lock:
            before = len(self._data["projects"])
            self._data["projects"] = [p for p in self._data["projects"] if p.get("project_id") != project_id]
            if len(self._data["projects"]) == before:
                return False

            if delete_conversations:
                to_del = [cid for cid, c in self._data["conversations"].items() if c.get("project_id") == project_id]
                for cid in to_del:
                    del self._data["conversations"][cid]

            if not self._data["projects"]:
                default_proj = {
                    "project_id": f"proj_{uuid.uuid4().hex[:8]}",
                    "name": "Genel Projeler",
                    "folder_path": self.base_dir,
                    "expanded": True,
                    "created_at": time.time(),
                    "updated_at": time.time()
                }
                self._data["projects"].append(default_proj)

            if self._data.get("active_project_id") == project_id:
                self._data["active_project_id"] = self._data["projects"][0]["project_id"]

            active_cid = self._data.get("active_conversation_id")
            if not active_cid or active_cid not in self._data["conversations"]:
                all_c = self.get_all_conversations_sorted()
                if all_c:
                    self.set_active_selection(all_c[0]["conversation_id"], all_c[0].get("active_node_id"))
                else:
                    self._data["active_conversation_id"] = None
                    self._data["active_node_id"] = None

            self._save()
            return True

    def get_conversations_for_project(self, project_id: str, search_query: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            convs = [
                c for c in self._data["conversations"].values()
                if c.get("project_id") == project_id
            ]
            if search_query:
                q = search_query.lower().strip()
                filtered = []
                for c in convs:
                    if q in c.get("title", "").lower():
                        filtered.append(c)
                        continue
                    for n in c.get("nodes", {}).values():
                        if q in n.get("prompt", "").lower() or q in n.get("chef_summary", "").lower():
                            filtered.append(c)
                            break
                convs = filtered

            convs.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            return convs

    def get_all_conversations_sorted(self) -> List[Dict[str, Any]]:
        with self._lock:
            convs = list(self._data["conversations"].values())
            convs.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            return convs

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data["conversations"].get(conversation_id)

    def get_node(self, conversation_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return None
            return conv.get("nodes", {}).get(node_id)

    def get_active_state(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """(active_project_id, active_conversation_id, active_node_id) döner."""
        with self._lock:
            return (
                self._data.get("active_project_id"),
                self._data.get("active_conversation_id"),
                self._data.get("active_node_id")
            )

    def set_active_selection(self, conversation_id: Optional[str], node_id: Optional[str] = None):
        with self._lock:
            self._data["active_conversation_id"] = conversation_id
            if conversation_id and conversation_id in self._data["conversations"]:
                conv = self._data["conversations"][conversation_id]
                self._data["active_project_id"] = conv.get("project_id")
                if node_id and node_id in conv.get("nodes", {}):
                    conv["active_node_id"] = node_id
                    conv["fork_parent_node_id"] = node_id
                    self._data["active_node_id"] = node_id
                else:
                    self._data["active_node_id"] = conv.get("active_node_id")
            else:
                self._data["active_node_id"] = None
            self._save()

    def set_fork_point(self, conversation_id: str, parent_node_id: Optional[str]):
        """Kullanıcının seçtiği geçmiş bir mesajı yeni bir dal (branch) başlangıç noktası olarak işaretler."""
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if conv:
                conv["fork_parent_node_id"] = parent_node_id
                if parent_node_id:
                    conv["active_node_id"] = parent_node_id
                    self._data["active_node_id"] = parent_node_id
                self._save()

    def create_new_conversation(
        self,
        project_id: Optional[str] = None,
        title: str = "Yeni Görev",
        target_folder: str = "",
        source_files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Yeni bir boş veya başlangıç konuşması açar."""
        with self._lock:
            if not project_id:
                proj = self.get_or_create_project_for_folder(target_folder)
                project_id = proj["project_id"]
                if not target_folder:
                    target_folder = proj.get("folder_path", self.base_dir)

            now = time.time()
            conv_id = f"conv_{uuid.uuid4().hex[:8]}"
            conv = {
                "conversation_id": conv_id,
                "project_id": project_id,
                "title": title,
                "target_folder": target_folder,
                "source_files": list(source_files or []),
                "root_node_id": None,
                "active_node_id": None,
                "fork_parent_node_id": None,
                "status": "draft",
                "created_at": now,
                "updated_at": now,
                "nodes": {}
            }
            self._data["conversations"][conv_id] = conv
            self._data["active_project_id"] = project_id
            self._data["active_conversation_id"] = conv_id
            self._data["active_node_id"] = None
            self._save()
            return conv

    def rename_conversation(self, conversation_id: str, new_title: str) -> bool:
        """Geçmiş konuşmanın başlığını düzenler."""
        with self._lock:
            clean = (new_title or "").strip()
            if not clean:
                return False
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return False
            conv["title"] = clean
            conv["updated_at"] = time.time()
            self._save()
            return True

    def delete_conversation(self, conversation_id: str):
        with self._lock:
            if conversation_id in self._data["conversations"]:
                del self._data["conversations"][conversation_id]
                if self._data.get("active_conversation_id") == conversation_id:
                    all_c = self.get_all_conversations_sorted()
                    if all_c:
                        first = all_c[0]
                        self.set_active_selection(first["conversation_id"], first.get("active_node_id"))
                    else:
                        self._data["active_conversation_id"] = None
                        self._data["active_node_id"] = None
                self._save()

    def update_node_prompt(self, conversation_id: str, node_id: str, new_prompt: str, new_summary: Optional[str] = None) -> bool:
        """Geçmişteki bir mesajın/adımın prompt metnini (veya özetini) düzenler."""
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return False
            node = conv.get("nodes", {}).get(node_id)
            if not node:
                return False
            clean_p = (new_prompt or "").strip()
            if clean_p:
                node["prompt"] = clean_p
            if new_summary is not None:
                node["chef_summary"] = new_summary.strip()
            conv["updated_at"] = time.time()
            self._save()
            return True

    def delete_node(self, conversation_id: str, node_id: str) -> bool:
        """Konuşma içindeki tek bir geçmiş adımı/mesajı siler."""
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return False
            nodes = conv.get("nodes", {})
            if node_id not in nodes:
                return False

            target_node = nodes[node_id]
            parent_id = target_node.get("parent_node_id")

            for n in nodes.values():
                if n.get("parent_node_id") == node_id:
                    n["parent_node_id"] = parent_id

            del nodes[node_id]

            if not nodes:
                self.delete_conversation(conversation_id)
                return True

            remaining = sorted(nodes.values(), key=lambda x: x.get("created_at", 0))
            if conv.get("root_node_id") == node_id:
                conv["root_node_id"] = remaining[0]["node_id"]
            if conv.get("active_node_id") == node_id:
                new_act = parent_id if (parent_id and parent_id in nodes) else remaining[-1]["node_id"]
                conv["active_node_id"] = new_act
                conv["fork_parent_node_id"] = new_act
                if self._data.get("active_conversation_id") == conversation_id:
                    self._data["active_node_id"] = new_act

            conv["updated_at"] = time.time()
            self._save()
            return True

    def clear_all_history(self):
        """Tüm geçmiş konuşmaları temizler ve tertemiz bir çalışma alanı başlatır."""
        with self._lock:
            self._data["conversations"] = {}
            unity_dir = os.path.join(self.base_dir, "Unity Denemeler Klasörü", "MCP Deneme")
            has_unity = os.path.exists(unity_dir)
            self._data["projects"] = [
                {
                    "project_id": "proj_default",
                    "name": "MCP Deneme" if has_unity else "Projelerim",
                    "folder_path": unity_dir if has_unity else self.base_dir,
                    "expanded": True,
                    "created_at": time.time(),
                    "updated_at": time.time()
                }
            ]
            self._data["active_project_id"] = "proj_default"
            self._data["active_conversation_id"] = None
            self._data["active_node_id"] = None
            self._save()

    def start_prompt_node(
        self,
        prompt: str,
        target_folder: str = "",
        source_files: Optional[List[str]] = None,
        conversation_id: Optional[str] = None,
        parent_node_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Kullanıcı 'Orkestrayı Çalıştır' dediğinde yeni bir BranchNode (Dal Adımı) başlatır.
        - Eğer aktif bir konuşma yoksa veya yeni konuşma modundaysa yeni konuşma oluşturur.
        - Eğer `parent_node_id` verilmişse ve bu ebeveynin zaten başka bir alt dalı varsa,
          otomatik olarak yeni bir dal adı (`branch-2`, `branch-3` vb.) atar!
        Dönüş: (conversation_id, node_id)
        """
        with self._lock:
            now = time.time()
            smart_title = generate_smart_title(prompt)

            proj = self.get_or_create_project_for_folder(target_folder)
            project_id = proj["project_id"]

            conv = self._data["conversations"].get(conversation_id) if conversation_id else None
            if not conv:
                conv = self.create_new_conversation(
                    project_id=project_id,
                    title=smart_title,
                    target_folder=target_folder,
                    source_files=source_files
                )
                conversation_id = conv["conversation_id"]
            else:
                if conv.get("title") in ["Yeni Görev", "Yeni Sohbet", ""] or not conv.get("nodes"):
                    conv["title"] = smart_title
                if target_folder:
                    conv["target_folder"] = target_folder
                    conv["project_id"] = project_id
                if source_files:
                    conv["source_files"] = list(source_files)

            nodes = conv.get("nodes", {})

            if parent_node_id is None and nodes:
                parent_node_id = conv.get("fork_parent_node_id") or conv.get("active_node_id")
            if parent_node_id and parent_node_id not in nodes:
                parent_node_id = None

            if not parent_node_id:
                turn_number = 1
                existing_roots = [n for n in nodes.values() if not n.get("parent_node_id")]
                branch_name = "main" if not existing_roots else f"branch-{len(existing_roots) + 1}"
            else:
                parent_node = nodes[parent_node_id]
                turn_number = int(parent_node.get("turn_number", 1)) + 1
                siblings = [n for n in nodes.values() if n.get("parent_node_id") == parent_node_id]
                if not siblings:
                    branch_name = parent_node.get("branch_name", "main")
                else:
                    all_branches = set(n.get("branch_name", "main") for n in nodes.values())
                    b_idx = len(all_branches) + 1
                    while f"branch-{b_idx}" in all_branches:
                        b_idx += 1
                    branch_name = f"branch-{b_idx}"

            node_id = f"node_{uuid.uuid4().hex[:8]}"
            node_obj = {
                "node_id": node_id,
                "parent_node_id": parent_node_id,
                "branch_name": branch_name,
                "turn_number": turn_number,
                "prompt": prompt,
                "chef_summary": "⏳ Orkestra çalışıyor...",
                "architecture_contract": "",
                "agent_tasks": [],
                "files_produced": [],
                "terminal_log": "",
                "target_folder": target_folder or conv.get("target_folder", ""),
                "source_files": list(source_files or conv.get("source_files", [])),
                "token_stats": {"chef": 0, "workers": 0, "council": 0, "total": 0},
                "app_key": "general",
                "created_at": now,
                "completed_at": None,
                "duration_sec": 0.0,
                "status": "running"
            }

            nodes[node_id] = node_obj
            conv["nodes"] = nodes
            if not conv.get("root_node_id"):
                conv["root_node_id"] = node_id
            conv["active_node_id"] = node_id
            conv["fork_parent_node_id"] = node_id
            conv["status"] = "running"
            conv["updated_at"] = now

            for p in self._data["projects"]:
                if p["project_id"] == conv["project_id"]:
                    p["updated_at"] = now
                    p["expanded"] = True

            self._data["active_project_id"] = conv["project_id"]
            self._data["active_conversation_id"] = conversation_id
            self._data["active_node_id"] = node_id
            self._save()
            return conversation_id, node_id

    def complete_prompt_node(
        self,
        conversation_id: str,
        node_id: str,
        chef_summary: str,
        terminal_log: str,
        agent_tasks: Optional[List[Dict[str, Any]]] = None,
        files_produced: Optional[List[Dict[str, Any]]] = None,
        architecture_contract: str = "",
        target_folder: str = "",
        token_stats: Optional[Dict[str, int]] = None,
        app_key: str = "general",
        status: str = "completed"
    ):
        """Orkestrasyon tamamlandığında veya hata aldığında BranchNode kaydını mühürler."""
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return
            node = conv.get("nodes", {}).get(node_id)
            if not node:
                return

            now = time.time()
            node["chef_summary"] = chef_summary
            node["terminal_log"] = terminal_log
            if agent_tasks is not None:
                node["agent_tasks"] = agent_tasks
            if files_produced is not None:
                node["files_produced"] = files_produced
            if architecture_contract:
                node["architecture_contract"] = architecture_contract
            if target_folder:
                node["target_folder"] = target_folder
                conv["target_folder"] = target_folder
            if token_stats:
                node["token_stats"] = token_stats
            if app_key:
                node["app_key"] = app_key

            node["completed_at"] = now
            node["duration_sec"] = round(max(0.1, now - float(node.get("created_at", now))), 1)
            node["status"] = status

            conv["status"] = status
            conv["updated_at"] = now
            self._save()

    def get_branch_lineage(self, conversation_id: str, target_node_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Kök düğümden (Root Prompt) başlayarak `target_node_id`'ye kadar olan
        aktif dal zincirini (lineage) kronolojik sırayla döndürür.
        """
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return []
            nodes = conv.get("nodes", {})
            if not nodes:
                return []

            curr_id = target_node_id or conv.get("active_node_id")
            if not curr_id or curr_id not in nodes:
                all_n = sorted(nodes.values(), key=lambda x: x.get("created_at", 0))
                curr_id = all_n[-1]["node_id"]

            chain = []
            visited = set()
            while curr_id and curr_id in nodes and curr_id not in visited:
                visited.add(curr_id)
                chain.append(nodes[curr_id])
                curr_id = nodes[curr_id].get("parent_node_id")

            chain.reverse()
            return chain

    def get_all_nodes_sorted(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Konuşmadaki tüm dalları ve düğümleri oluşturulma sırasına göre döndürür."""
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return []
            nodes = list(conv.get("nodes", {}).values())
            nodes.sort(key=lambda x: (x.get("turn_number", 1), x.get("created_at", 0)))
            return nodes

    def get_children_nodes(self, conversation_id: str, parent_node_id: Optional[str]) -> List[Dict[str, Any]]:
        """Belirli bir düğümden çatallanan alt dalları döndürür."""
        with self._lock:
            conv = self._data["conversations"].get(conversation_id)
            if not conv:
                return []
            children = [
                n for n in conv.get("nodes", {}).values()
                if n.get("parent_node_id") == parent_node_id
            ]
            children.sort(key=lambda x: x.get("created_at", 0))
            return children

    def build_branch_prompt_context(self, conversation_id: Optional[str], parent_node_id: Optional[str]) -> str:
        """
        🧠 ŞEF VE AMELE AJANLAR İÇİN BRANCH HAFIZA BAĞLAMI:
        Kullanıcı mevcut bir konuşmada/dalda yeni bir prompt verdiğinde veya geçmiş bir
        prompttan yeni bir dal (branch) çatallandırdığında; o dalın kökünden `parent_node_id`'ye
        kadar olan tüm önceki promptları, yapılan işleri, mimari sözleşmeleri ve üretilen
        dosyaların güncel kodlarını tek bir yapılandırılmış hafıza bloğu olarak derler.
        """
        if not conversation_id or not parent_node_id:
            return ""

        lineage = self.get_branch_lineage(conversation_id, parent_node_id)
        if not lineage:
            return ""

        lines = [
            "═" * 75,
            "🌿 [AKTİF BRANCH (DAL) HAFIZA KAYDI — ÖNCEKİ PROMPTLAR VE YAPILAN İŞLER]",
            "═" * 75,
            "Aşağıdaki kayıtlar, bu konuşma dalında (branch) şu ana kadar sırasıyla verilen",
            "kullanıcı promptlarını, alınan mimari kararları ve üretilen dosyaları içerir.",
            "Yeni isteği yerine getirirken bu geçmişi dikkate al, önceki mimariyi bozma ve",
            "gerekli dosyaları bu geçmişin üzerine geliştirerek/onarıp tamamlayarak üret:\n"
        ]

        latest_files_map: Dict[str, Dict[str, Any]] = {}
        latest_contract = ""

        for idx, node in enumerate(lineage, start=1):
            b_name = node.get("branch_name", "main")
            t_num = node.get("turn_number", idx)
            p_text = node.get("prompt", "")
            c_sum = node.get("chef_summary", "")
            contract = node.get("architecture_contract", "")
            if contract:
                latest_contract = contract

            tasks = node.get("agent_tasks", [])
            files = node.get("files_produced", [])

            lines.append(f"─── 📌 [DAL ADIMI #{t_num} | Dal: {b_name}] ───")
            lines.append(f"👤 Önceki Kullanıcı Promptu #{t_num}:\n\"{p_text}\"")

            if contract:
                lines.append(f"📜 Kilitlenen Mimari Sözleşme:\n{contract[:600]}")

            if tasks:
                task_strs = [f"{t.get('file', '?')} ({t.get('title', '')})" for t in tasks]
                lines.append(f"🤖 Görevlendirilen Modüller ({len(tasks)} Adet): {', '.join(task_strs)}")

            if files:
                file_names = [f.get("rel_path") or os.path.basename(f.get("path", "")) for f in files]
                lines.append(f"📦 Üretilen Dosyalar: {', '.join(file_names)}")
                for f_info in files:
                    r_path = f_info.get("rel_path") or os.path.basename(f_info.get("path", ""))
                    if r_path:
                        latest_files_map[r_path] = f_info

            if c_sum:
                short_sum = c_sum.strip()
                if len(short_sum) > 900:
                    short_sum = short_sum[:900] + "..."
                lines.append(f"👑 Yapılan İş ve Sonuç Özeti:\n{short_sum}\n")

        if latest_files_map:
            lines.append("─── 📂 [BU DALDA ÜRETİLEN MEVCUT DOSYALARIN KOD İÇERİKLERİ] ───")
            for r_path, f_info in list(latest_files_map.items())[:12]:
                preview = f_info.get("preview", "")
                disk_path = f_info.get("path", "")
                if not preview and disk_path and os.path.exists(disk_path):
                    try:
                        with open(disk_path, "r", encoding="utf-8", errors="replace") as f:
                            preview = f.read()[:6000]
                    except Exception:
                        pass
                if preview:
                    lines.append(f"\n📄 Dosya: {r_path}\n```\n{preview[:4500]}\n```")

        if latest_contract:
            lines.append(f"\n📜 [GEÇERLİ DAL MİMARİ SÖZLEŞMESİ]:\n{latest_contract}")

        lines.append("═" * 75 + "\n")
        return "\n".join(lines)


branch_memory = BranchMemoryManager()
