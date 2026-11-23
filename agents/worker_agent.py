import os
import re
import time
import queue
import threading
from typing import Optional, Dict, Any, List

from core.agent_registry import agent_registry, AgentState, AgentInfo
from core.event_bus import (
    event_bus,
    Event,
    EVENT_TASK_STARTED,
    EVENT_INTERMEDIATE_DATA,
    EVENT_DATA_REQUEST,
    EVENT_WAITING_SYNC,
    EVENT_REVISION_REQUESTED,
    EVENT_TASK_APPROVED,
    EVENT_SYNC_TIMED_OUT,
    EVENT_PEER_CONSULTATION,
    EVENT_TERMINATE_ALL
)
from core.blackboard import SharedBlackboard
from core.task_queue import TaskItem, TaskStatus
from capabilities.registry import capability_registry, CapabilityDefinition
from infrastructure.nim_client import nim_service
from infrastructure.gemini_client import gemini_service
from agents.shadow_auditor import golge_ajan_denetle
from tools import execute_tool_call, extract_tool_call, resolve_tool_paths


WORKER_READONLY_TOOLS = {
    "list_directory", "read_file", "grep_search", "check_syntax",
    "inspect_image", "search_assets",
    "unity_status", "unity_ping", "unity_get_hierarchy",
    "unity_inspect_object", "unity_get_logs",
    "blender_ping", "blender_status", "mcp_blender_ping",
    "blender_get_scene", "mcp_blender_get_scene",
}


def _sanitize_unity_csharp(kod: str) -> str:
    """Unity 6 C# kodlarında sık yapılan deterministik API hatalarını (RectTransform çift ekleme, fake-null ??, FindFirstObjectByType CS1503, URP Shader, Arial.ttf vb.) temizler."""
    if not kod:
        return kod

    kod = re.sub(
        r"\b(FindFirstObjectByType|FindAnyObjectByType)\s*<([^>]+)>\s*\(\s*FindObjectsSortMode\.\w+\s*\)",
        r"\1<\2>()",
        kod,
    )

    def _replace_standard_shader(match: re.Match) -> str:
        prefix = match.group(1) or ""
        if "Universal Render Pipeline/Lit" in prefix or "??" in prefix:
            return match.group(0)
        return f'{prefix}(Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard"))'

    kod = re.sub(
        r'([^\n;]*?)Shader\.Find\(\s*"Standard"\s*\)',
        _replace_standard_shader,
        kod,
    )

    kod = re.sub(
        r"((?:[A-Za-z_]\w*\.)?GetComponent(?:InChildren|InParent)?\s*<([A-Za-z_][\w\.]*)>\s*\(\s*\))\s*\?\?\s*((?:[A-Za-z_]\w*\.)?AddComponent\s*<\2>\s*\(\s*\))",
        r"(\1 != null ? \1 : \3)",
        kod,
    )

    ui_tipleri = (
        "CanvasScaler", "GraphicRaycaster", "RawImage", "Image", "Button",
        "Slider", "HorizontalLayoutGroup", "VerticalLayoutGroup", "GridLayoutGroup", "ScrollRect"
    )
    if any(re.search(rf"\b{t}\b", kod) for t in ui_tipleri) and "using UnityEngine.UI;" not in kod:
        if kod.lstrip().startswith("#if UNITY_EDITOR"):
            kod = re.sub(r"^(\s*#if\s+UNITY_EDITOR\s*\n)", r"\1using UnityEngine.UI;\n", kod, count=1)
        else:
            kod = "using UnityEngine.UI;\n" + kod

    def _replace_rect_add(match: re.Match) -> str:
        prefix = match.group(1) or ""
        obj = match.group(2)
        if "GetComponent<RectTransform>()" in prefix:
            return match.group(0)
        return (
            f"{prefix}({obj}.GetComponent<RectTransform>() != null "
            f"? {obj}.GetComponent<RectTransform>() : {obj}.AddComponent<RectTransform>())"
        )

    kod = re.sub(
        r"([^\n;]*?)\b([A-Za-z_]\w*)\.AddComponent<RectTransform>\(\)",
        _replace_rect_add,
        kod,
    )
    if '"Arial.ttf"' in kod:
        kod = kod.replace('"Arial.ttf"', '"LegacyRuntime.ttf"')

    kod = re.sub(r'\.CompareTag\(\s*"Enemy"\s*\)', '.name.Contains("Enemy")', kod)
    kod = re.sub(r'\b[A-Za-z_]\w*\.tag\s*=\s*"Enemy"\s*;', '', kod)

    kod = re.sub(r'\bpublic\s+(static\s+)?event\s+(System\.)?Action\b', r'public \1\2Action', kod)
    return kod


def _extract_csharp_public_api(kod: str) -> str:
    """C# dosyasının tüm public sınıf, enum, özellik, olay ve metot imzalarını özetler."""
    if not kod:
        return ""
    imzalar: List[str] = []
    for line in kod.splitlines():
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("*"):
            continue
        if any(s.startswith(p) for p in ("public class ", "public static class ", "public enum ", "public interface ", "public struct ", "public ")):
            clean_sig = s.split("{")[0].strip() if ("(" in s and not s.startswith("public enum")) else s
            imzalar.append("  " + clean_sig[:140])
    return "\n".join(imzalar[:45])


def saf_kodu_ayikla(ham_metin: str, dosya_adi: str = "") -> str:
    if not ham_metin:
        return ""
    metin = re.sub(r"<think>.*?</think>", "", ham_metin, flags=re.DOTALL).strip()
    
    if dosya_adi.lower().endswith((".md", ".txt", ".markdown", ".json")):
        match = re.match(r"^```(?:markdown|md|json|text)?\s*\n(.*)\n```$", metin, re.DOTALL)
        if match:
            return match.group(1).strip()
        return metin

    tum_bloklar = re.findall(r"```([a-zA-Z0-9_\-#]*)\s*\n(.*?)\n\s*```", metin, re.DOTALL)
    md_bloklar = [icerik for dil, icerik in tum_bloklar if dil.strip().lower() != "tool"]
    if md_bloklar:
        sinif_adi = os.path.splitext(os.path.basename(dosya_adi))[0] if dosya_adi else ""
        secilen = md_bloklar[-1].strip()
        if sinif_adi:
            for b in reversed(md_bloklar):
                if f"class {sinif_adi}" in b or f"struct {sinif_adi}" in b or f"enum {sinif_adi}" in b:
                    secilen = b.strip()
                    break
        return _sanitize_unity_csharp(secilen) if dosya_adi.lower().endswith(".cs") else secilen
    else:
        if "```" in metin:
            parcalar = metin.split("```")
            if len(parcalar) >= 2:
                olasi = parcalar[1]
                temiz_olasi = re.sub(r"^[a-zA-Z0-9_\-#]+\s*\n", "", olasi).strip()
                return _sanitize_unity_csharp(temiz_olasi) if dosya_adi.lower().endswith(".cs") else temiz_olasi
        metin = re.sub(r"^```[a-zA-Z0-9_\-]*\s*\n?", "", metin)
        metin = re.sub(r"\n?```\s*$", "", metin)
    sonuc = metin.strip()
    return _sanitize_unity_csharp(sonuc) if dosya_adi.lower().endswith(".cs") else sonuc

class WorkerAgent:
    """
    Kalıcı ve Otonom Amele Ajan (Worker / Specialist Agent).
    - NVIDIA NIM üzerinden çalışır.
    - Görevini tamamladığında HEMEN KAPANMAZ; diğer ajanlarla veri paylaşımı ve
      Şef onayı için WAITING_SYNC modunda dinlemede kalır.
    - Zaman aşımı (sync_timeout) ile deadlock koruması içerir.
    - Şef revizyon isterse görevi günceller; Şef onay verince sonlanır.
    """
    def __init__(
        self,
        agent_id: str,
        capability: str,
        blackboard: SharedBlackboard,
        model_id: Optional[str] = None,
        sync_timeout: float = 120.0,
        target_folder: str = ""
    ):
        self.agent_id = agent_id
        self.capability_name = capability
        self.blackboard = blackboard
        self.sync_timeout = sync_timeout
        self.target_folder = target_folder

        self.cap_def: CapabilityDefinition = capability_registry.get(capability)
        self.model_id = model_id or nim_service.get_best_model_for_capability(capability)

        self.state = AgentState.REGISTERED
        self.inbox = queue.Queue()
        self._stop_event = threading.Event()
        self.current_task: Optional[TaskItem] = None
        self.latest_output: Optional[str] = None
        self.worker_thread: Optional[threading.Thread] = None

        agent_registry.register(self.agent_id, self.capability_name, self.model_id)

        event_bus.subscribe(EVENT_TERMINATE_ALL, self._on_terminate_all)
        event_bus.subscribe(EVENT_REVISION_REQUESTED, self._on_event)
        event_bus.subscribe(EVENT_TASK_APPROVED, self._on_event)

    def start(self):
        """Ajanın persistent arka plan döngüsünü başlatır."""
        self.state = AgentState.IDLE
        agent_registry.update_state(self.agent_id, AgentState.IDLE)
        self.worker_thread = threading.Thread(target=self._run_loop, name=f"Worker-{self.agent_id}", daemon=True)
        self.worker_thread.start()

    def assign_task(self, task: TaskItem):
        """Ajanın gelen kutusuna yeni görev bırakır."""
        self.inbox.put({"type": "ASSIGN_TASK", "task": task})

    def _on_event(self, event: Event):
        target_agent = event.data.get("agent_id")
        task_id = event.data.get("task_id")
        if target_agent == self.agent_id or (self.current_task and task_id == self.current_task.task_id):
            self.inbox.put({"type": event.event_type, "event": event})

    def _on_terminate_all(self, event: Event):
        self._stop_event.set()

    def _run_loop(self):
        """Ajanın ana döngüsü."""
        while not self._stop_event.is_set():
            try:
                msg = self.inbox.get(timeout=1.0)
            except queue.Empty:
                agent_registry.update_heartbeat(self.agent_id)
                continue

            m_type = msg.get("type")
            if m_type == "ASSIGN_TASK":
                task = msg["task"]
                self._handle_task(task)
            elif m_type == EVENT_TERMINATE_ALL:
                break

        self.state = AgentState.TERMINATED
        agent_registry.update_state(self.agent_id, AgentState.TERMINATED)

    def _run_model_with_tools(
        self,
        use_gemini: bool,
        sistem: str,
        kullanici: str,
        max_tool_steps: int = 3
    ) -> str:
        """
        Hem Gemini hem NVIDIA NIM amele çağrılarında modelin nihai kodu üretmeden önce
        araç (read_file, inspect_image, search_assets, unity_inspect_object vb.) çağırmasına izin verir.
        """
        aktif_kullanici = kullanici
        for step in range(max_tool_steps + 1):
            if use_gemini:
                yanit = gemini_service.generate_with_retry(
                    prompt=aktif_kullanici,
                    system_instruction=sistem,
                    temperature=0.15
                )
                if self.blackboard:
                    self.blackboard.record_token_usage("chef", int(len(yanit) / 3.5))
            else:
                messages = [
                    {"role": "system", "content": sistem},
                    {"role": "user", "content": aktif_kullanici}
                ]
                yanit = nim_service.complete_with_retry(
                    model_id=self.model_id,
                    messages=messages,
                    temperature=0.15,
                    max_tokens=8000,
                    max_retries=2,
                    timeout=45.0,
                    disable_thinking=True
                )
                if self.blackboard:
                    self.blackboard.record_token_usage("workers", int(len(yanit) / 3.5))

            parsed = extract_tool_call(yanit)
            if not parsed:
                return yanit
            if step == max_tool_steps:
                hedef_dosya = self.current_task.target_file if self.current_task else "ilgili"
                son_istem = (
                    aktif_kullanici
                    + f"\n\n🚨 KRİTİK KURAL: Araç çağırma hakkın bitti! ASLA ```tool bloğu veya JSON araç çağrısı döndürme! "
                    f"Şimdi doğrudan '{hedef_dosya}' dosyasının tam, eksiksiz ve derlenebilir saf kodunu üret."
                )
                if use_gemini:
                    son_yanit = gemini_service.generate_with_retry(
                        prompt=son_istem,
                        system_instruction=sistem,
                        temperature=0.15
                    )
                    if self.blackboard:
                        self.blackboard.record_token_usage("chef", int(len(son_yanit) / 3.5))
                    return son_yanit
                else:
                    son_yanit = nim_service.complete_with_retry(
                        model_id=self.model_id,
                        messages=[{"role": "system", "content": sistem}, {"role": "user", "content": son_istem}],
                        temperature=0.15,
                        max_tokens=8000,
                        max_retries=2,
                        timeout=45.0,
                        disable_thinking=True
                    )
                    if self.blackboard:
                        self.blackboard.record_token_usage("workers", int(len(son_yanit) / 3.5))
                    return son_yanit

            t_name, t_args = parsed
            if t_name not in WORKER_READONLY_TOOLS:
                hedef_dosya = self.current_task.target_file if self.current_task else "ilgili"
                aktif_kullanici += (
                    f"\n\n--- ARAÇ KISITI ({t_name}) ---\n"
                    f"Paralel işçi aşamasında yalnızca salt-okunur inceleme araçları ({sorted(WORKER_READONLY_TOOLS)}) kullanılabilir. "
                    f"Dosya yazma ve sahne değiştirme işlemleri Şef denetiminden sonra yapılır. "
                    f"Şimdi doğrudan '{hedef_dosya}' dosyasının tam ve eksiksiz saf kodunu üret."
                )
                continue
            if self.target_folder:
                t_args = resolve_tool_paths(t_args, self.target_folder)
            print(f"   ⚡ [{self.agent_id} Tool Çağrısı ({step + 1}/{max_tool_steps})]: {t_name}({list(t_args.keys())})")
            try:
                t_res = execute_tool_call(t_name, t_args)
            except Exception as te:
                t_res = f"Araç hatası ({t_name}): {te}"
            print(f"      └ 🟢 Gözlem: {str(t_res)[:100]}...")
            aktif_kullanici += (
                f"\n\n--- ARAÇ ÇAĞRISI ({t_name}) SONUCU ---\n{t_res}\n"
                "Şimdi başka araca ihtiyacın yoksa doğrudan hedef dosyanın tam, eksiksiz ve çalışan saf kodunu üret."
            )
        return ""

    def _handle_task(self, task: TaskItem):
        self.current_task = task
        self.state = AgentState.WORKING
        agent_registry.update_state(self.agent_id, AgentState.WORKING, current_task_id=str(task.task_id))
        event_bus.publish(EVENT_TASK_STARTED, self.agent_id, {"task_id": task.task_id, "file": task.target_file})

        kisa_m = self.model_id.split('/')[-1]
        print(f"\n   ⚙️ [{self.agent_id} | {self.capability_name}] '{task.title}' ({task.target_file}) görevine başladı... ({kisa_m})")

        try:
            output = self._execute_generation(task)
        except Exception as err:
            err_msg = str(err)
            print(f"   ❌ [{self.agent_id}] '{task.target_file}' üretiminde kritik hata: {err_msg}")
            task.status = TaskStatus.FAILED
            task.error = err_msg
            self.state = AgentState.TERMINATED
            agent_registry.update_state(self.agent_id, AgentState.TERMINATED, current_task_id=str(task.task_id))
            event_bus.publish("EVENT_TASK_FAILED", self.agent_id, {
                "task_id": task.task_id,
                "target_file": task.target_file,
                "error": err_msg
            })
            self._stop_event.set()
            return

        self.latest_output = output
        task.output = output

        self.blackboard.set_artifact(task.target_file, output)
        self.blackboard.set_intermediate(self.agent_id, "latest_file", task.target_file)
        self.blackboard.set_intermediate(self.agent_id, "summary", f"{task.title} üretildi ({len(output)} bayt)")
        self.blackboard.cikti_yaz(task.task_id, output, task.target_file)

        event_bus.publish(EVENT_INTERMEDIATE_DATA, self.agent_id, {
            "task_id": task.task_id,
            "target_file": task.target_file,
            "length": len(output)
        })

        self._enter_waiting_sync(task)

    def _execute_generation(self, task: TaskItem, revision_note: str = "") -> str:
        """Kodu/metni NIM ile üretir, gerekirse araçları çağırır ve denetler."""
        diger_veriler = self.blackboard.get_all_intermediates()
        baglam_parcalari = []
        for aj_id, v in diger_veriler.items():
            if aj_id != self.agent_id:
                baglam_parcalari.append(f"- [{aj_id}]: {v.get('summary', '')} (Dosya: {v.get('latest_file', '')})")

        ara_durum_metni = "\n".join(baglam_parcalari) if baglam_parcalari else "Henüz diğer ajanlardan ara veri yok."

        is_integrator = (
            any(k in task.target_file.lower() for k in [".html", "report", "rapor", "main", "bootstrapper", "scenebuilder", "builder", "editor", "assembler"])
            or "entegrasyon" in task.title.lower()
        )
        scoped_artifacts = self.blackboard.get_scoped_artifacts_for_task(
            dependencies=task.dependencies,
            current_file=task.target_file,
            is_integrator=is_integrator
        )

        bagimli_kodlar = []
        for art_name, art_content in scoped_artifacts.items():
            if isinstance(art_content, str) and not art_content.startswith("[BINARY_MEDIA_FILE:"):
                api_header = ""
                if art_name.lower().endswith(".cs"):
                    pub_api = _extract_csharp_public_api(art_content)
                    if pub_api:
                        api_header = f"// [KESİN PUBLIC API SÖZLEŞMESİ — YALNIZCA BU METOT VE ÖZELLİK İSİMLERİNİ KULLAN]:\n{pub_api}\n\n"
                bagimli_kodlar.append(
                    f"=== [DOĞRUDAN BAĞIMLI KÖK BİLEŞENİ: {art_name}] ===\n"
                    f"{api_header}{art_content[:16000]}\n=============================="
                )

        bagimli_kod_metni = "\n\n".join(bagimli_kodlar) if bagimli_kodlar else ""

        uzanti = os.path.splitext(task.target_file)[1].lower()
        if self.capability_name == "image-generation" or uzanti in [".png", ".jpg", ".jpeg", ".webp"]:
            from infrastructure.media_client import media_service
            temp_yol = os.path.abspath(os.path.join("temp_media", task.target_file))
            basarili, yol, boyut = media_service.generate_image(task.instruction, temp_yol)
            if basarili:
                return f"[BINARY_MEDIA_FILE:{yol}]"
            raise RuntimeError(f"Görsel oluşturulamadı: {task.target_file}")

        elif self.capability_name == "video-generation" or uzanti in [".mp4", ".gif"]:
            from infrastructure.media_client import media_service
            temp_yol = os.path.abspath(os.path.join("temp_media", task.target_file))
            basarili, yol, boyut = media_service.generate_video(task.instruction, temp_yol, duration_sec=5)
            if basarili:
                return f"[BINARY_MEDIA_FILE:{yol}]"
            raise RuntimeError(f"Video oluşturulamadı: {task.target_file}")

        akran_katkilari = []
        alt_soru = ""
        instr_low = (task.instruction or "").lower()
        target_name = os.path.basename(task.target_file)
        if any(w in instr_low for w in ["ses", "sound", "audio", "müzik", "music", "synth", "sfx"]) and any(k in uzanti for k in [".html", ".js", ".ts"]):
            alt_soru = (
                f"'{target_name}' modülü için şu göreve birebir uygun, sıfır harici bağımlılıklı Web Audio API ses sentezleyici kodu yaz:\n"
                f"Görev özeti: {task.instruction[:450]}\n"
                f"Sadece görevde istenen mekaniklere uygun temiz JS kodu üret."
            )
        elif any(w in instr_low for w in ["çarpışma", "collision", "hareket", "movement", "fizik", "physics", "grid", "yapay zeka", "ai"]):
            alt_soru = (
                f"'{target_name}' dosyası için şu göreve tam uyumlu çekirdek mantık/algoritma taslağını yaz:\n"
                f"Görev özeti: {task.instruction[:450]}\n"
                f"Görevde istenmeyen (örn. alakasız platformer/yerçekimi) mekanikler ekleme; sadece tarif edilen mantığı eksiksiz kur."
            )
        elif uzanti == ".py" and any(w in instr_low for w in ["bpy", "blender", "mesh", "shader", "cycles", "eevee", "render"]):
            alt_soru = (
                f"'{target_name}' Blender 4.x/5.x bpy betiği için Principled BSDF soket isimleri ('Specular IOR Level') ve güvenli bmesh/collection kullanımıyla çekirdek yardımcı fonksiyonları yaz:\n"
                f"Görev özeti: {task.instruction[:450]}"
            )

            if alt_soru:
                akran_cozum = self.consult_peer_agent(alt_soru, target_capability="reason")
                if akran_cozum:
                    akran_katkilari.append(f"=== [AKRAN UZMAN AI AJANIN ÇÖZÜMÜ / ÖNERİSİ] ===\n{akran_cozum}\n=============================================")

        akran_metni = "\n\n".join(akran_katkilari) if akran_katkilari else ""

        kok_bilgisi = f"Beslendiğin Kök Dosyalar: {list(scoped_artifacts.keys())}" if scoped_artifacts else "Kök Dal (Bağımsız başlangıç)"
        sozlesme = self.blackboard.get_architecture_contract() if self.blackboard else ""
        sozlesme_bloku = f"\n📜 KÜRESEL ŞEF MİMARİ SÖZLEŞMESİ (BU KANUNLARA KESİNLİKLE %100 UYACAKSIN):\n{sozlesme}\n" if sozlesme else ""

        unity_ek_kurallar = ""
        if uzanti == ".cs":
            unity_ek_kurallar = """
🎮 UNITY 6 C# DERLEME VE ÇALIŞMA ZAMANI GÜVENLİĞİ KURALLARI (ZORUNLU):
- ASLA `namespace Global { ... }` bloğu AÇMA! Tüm sınıfları/enumları dosya kökünde (gerçek global alanda, namespace bloğu olmadan) veya mevcut proje namespace'ine uyumlu tanımla.
- ASLA `GetComponent<T>() ?? AddComponent<T>()` yazma (Unity'de sahte-null yüzünden MissingComponentException fırlatır)! Daima `var c = GetComponent<T>(); if (c == null) c = ...AddComponent<T>();` yaz.
- CanvasScaler, GraphicRaycaster, RawImage, Image, Text, Button, Slider kullanıyorsan dosyanın en başına MUTLAKA `using UnityEngine.UI;` ekle!
- Image, Text, RawImage, Button veya Slider eklenen bir GameObject otomatik olarak `RectTransform` alır; üzerine tekrar `AddComponent<RectTransform>()` ÇAĞIRMA (`GetComponent<RectTransform>()` kullan)!
- `Assets/Scripts/` altındaki runtime scriptlerinde ASLA `#if UNITY_EDITOR` dışında `using UnityEditor;` veya `UnityEditor.*` kullanma!
- `GameObject` sınıfının `.mesh` özelliği YOKTUR (`go.mesh` YASAKTIR)! Mesh için `GameObject.CreatePrimitive(...)` veya `GetComponent<MeshFilter>().sharedMesh` kullan.
- `Collider` soyut (abstract) sınıftır; ASLA `AddComponent<Collider>()` yazma! Bunun yerine `AddComponent<BoxCollider>()` veya `AddComponent<CapsuleCollider>()` kullan.
- Obsolete `FindObjectsOfType<T>()` yerine `UnityEngine.Object.FindObjectsByType<T>(FindObjectsSortMode.None)` ve `FindObjectOfType<T>()` yerine `UnityEngine.Object.FindFirstObjectByType<T>()` kullan.
- Mevcut bir Unity dosyasını güncelliyorsan var olan `public` sınıf/enum/metot/özellik imzalarını SİLME; yalnızca bozuk/eksik kısmı düzelterek mevcut işlevselliği koru!
- Boş iskelet (skeleton) sınıf yazma; tüm metotları, null kontrollerini ve oyun mekaniklerini tam ve eksiksiz doldur!
"""

        sistem = self.cap_def.system_prompt_template + f"""
{sozlesme_bloku}{unity_ek_kurallar}
🌳 WORKTREE AĞAÇ DALI İZOLASYON KURALLARI (KESİN UYULACAK):
1. SEN BİR AĞAÇ DALISIN: SADECE VE SADECE '{task.target_file}' dosyasının tam, eksiksiz, çalışan saf içeriğini üret!
2. DAL KESİŞME ENGELİ: Kendi dosyan dışındaki hiçbir dosyanın görevine veya içeriğine karışma. Diğer dalların alanına asla müdahale etme.
3. ORTAK KÖKTEN BESLENME: {kok_bilgisi}. Yalnızca sana sunulan bu kök bileşenleriyle %100 uyumlu ol.
4. İSTEĞE BAĞLI ARAÇ ÇAĞRISI: Kodu üretmeden önce projedeki bir ikonu/görseli (`inspect_image`, `search_assets`), dosyayı (`read_file`) veya canlı Unity sahnesini (`unity_get_hierarchy`, `unity_inspect_object`) incelemen şartsa önce tek bir ```tool {{"tool": "...", "args": {{...}}}} ``` bloğu verebilirsin; araç çıktısını aldıktan sonra doğrudan nihai saf kodu üret.
5. ÇIKTI KURALI: Nihai adımda açıklama veya gevezelik yapma, doğrudan saf kod/metin çıktısı ver.
"""
        kullanici = f"GÖREV:\n{task.instruction}\n\nHEDEF DOSYA: {task.target_file}"
        if bagimli_kod_metni:
            kullanici += f"\n\n🔗 BESLENDİĞİN KÖK BİLEŞENLER (Bununla entegre çalış):\n{bagimli_kod_metni}"
        if akran_metni:
            kullanici += f"\n\n🤝 DİĞER UZMAN AI AJANINDAN ALINAN DANIŞMA ÇÖZÜMÜ (Bunu koda eksiksiz entegre et):\n{akran_metni}"
        if revision_note:
            kullanici += f"\n\n🚨 ŞEFİN REVİZYON GERİ BİLDİRİMİ:\n{revision_note}\nBu uyarıları dikkate alarak kodu eksiksiz düzelt!"

        if uzanti == ".cs" and self.target_folder and os.path.isdir(os.path.join(self.target_folder, "Assets")):
            base_tf = os.path.basename(task.target_file)
            aday_yollar = [
                os.path.join(self.target_folder, task.target_file.replace("/", os.sep)),
                os.path.join(self.target_folder, "Assets", "Scripts", base_tf),
                os.path.join(self.target_folder, "Assets", "Editor", base_tf),
            ]
            mevcut_disk_yol = next((p for p in aday_yollar if os.path.isfile(p)), "")
            if mevcut_disk_yol:
                try:
                    with open(mevcut_disk_yol, "r", encoding="utf-8", errors="ignore") as rf:
                        disk_icerik = rf.read()
                    if disk_icerik.strip():
                        rel_disk = os.path.relpath(mevcut_disk_yol, self.target_folder).replace("\\", "/")
                        kullanici += (
                            f"\n\n📄 [MEVCUT DİSKTEKİ DOSYA ({rel_disk}) — ÇALIŞAN METOTLARI VE PUBLIC API'Yİ KORUYARAK GÜNCELLE]:\n"
                            f"```csharp\n{disk_icerik[:18000]}\n```"
                        )
                except Exception:
                    pass
            try:
                from tools.unity_tools import format_unity_project_symbol_index
                sym_ozet = format_unity_project_symbol_index(self.target_folder, exclude_file=task.target_file, max_chars=5500)
                if sym_ozet:
                    kullanici += f"\n\n{sym_ozet}"
            except Exception:
                pass

        kaynak_baglami = self.blackboard.get_kaynak_baglami() if self.blackboard else ""
        if kaynak_baglami:
            guncel_artefakt_adlari = {
                os.path.basename(k).lower()
                for k in (self.blackboard.get_all_artifacts() or {}).keys()
            }
            guncel_artefakt_adlari.add(os.path.basename(task.target_file).lower())
            filtrelenmis_baglam = kaynak_baglami
            for b_name in guncel_artefakt_adlari:
                if b_name:
                    filtrelenmis_baglam = re.sub(
                        rf"--- DOSYA: [^\n]*{re.escape(b_name)} ---\n.*?(?=\n--- DOSYA: |\Z)",
                        "",
                        filtrelenmis_baglam,
                        flags=re.IGNORECASE | re.DOTALL
                    )
            if filtrelenmis_baglam.strip():
                kullanici += f"\n\n📂 REFERANS KAYNAK DOSYALAR, BELGELER VE GÖRSEL ANALİZLERİ:\n{filtrelenmis_baglam[:25000]}"

        self.blackboard.register_task_step(task.task_id, task.target_file)

        is_unity_editor_script = uzanti == ".cs" and (
            "editor" in task.target_file.lower()
            or "scenebuilder" in task.target_file.lower()
            or "builder" in task.target_file.lower()
        )

        if not nim_service._is_healthy or not nim_service.verified_models or is_unity_editor_script:
            sebep_msg = "Kritik Unity Editor/SceneBuilder görevi" if is_unity_editor_script else "Canlı NIM modeli yok"
            print(f"   👑 [{self.agent_id}]: {sebep_msg} -> Doğrudan Baş Mimar (Gemini) Motoru ile üretiliyor...")
            res = self._run_model_with_tools(use_gemini=True, sistem=sistem, kullanici=kullanici)
            temiz = saf_kodu_ayikla(res, task.target_file)
            dom = self.blackboard.dom_haritasini_al()
            onay, sebep, nihai = golge_ajan_denetle(task.task_id, temiz, task.target_file, dom, task.instruction)
            return saf_kodu_ayikla(nihai, task.target_file)

        messages = [
            {"role": "system", "content": sistem},
            {"role": "user", "content": kullanici}
        ]

        try:
            raw = self._run_model_with_tools(use_gemini=False, sistem=sistem, kullanici=kullanici)
            temiz = saf_kodu_ayikla(raw, task.target_file)

            sinif_adi = os.path.splitext(os.path.basename(task.target_file))[0]
            if uzanti == ".cs":
                has_unity_api_bug = (
                    "AddComponent<Collider>()" in temiz
                    or (any(u in temiz for u in ["CanvasScaler", "GraphicRaycaster", "RawImage"]) and "using UnityEngine.UI" not in temiz)
                    or bool(re.search(r'\b\w+\.mesh\b', temiz) and "MeshFilter" not in temiz)
                )
                is_skeleton_cs = len(temiz) < 1200 or f"class {sinif_adi}" not in temiz
                if is_skeleton_cs or has_unity_api_bug:
                    print(f"   ⚠️ [{self.agent_id}]: NIM C# taslağı zayıf/iskelet ({len(temiz)} bayt) veya API hatası içeriyor. Baş Mimar (Gemini) ile zenginleştiriliyor...")
                    res_gem = gemini_service.generate_with_retry(
                        prompt=kullanici,
                        system_instruction=sistem,
                        temperature=0.15
                    )
                    self.blackboard.record_token_usage("chef", int(len(res_gem) / 3.5))
                    temiz = saf_kodu_ayikla(res_gem, task.target_file)

            if uzanti in [".html", ".js", ".py"] and len(temiz) < 2000 and "game" in task.instruction.lower():
                print(f"   🤝 [{self.agent_id}]: Taslak kod ({len(temiz)} bayt) akran model desteğiyle genişletiliyor...")
                genisletme = self.consult_peer_agent(
                    f"'{task.target_file}' için üretilen şu taslak kod kısa ({len(temiz)} bayt). Lütfen oyun döngüsünü, seviyeleri, canvas render ve kontrolleri eksiksiz ekleyerek tam çalışan tek dosya kod olarak üret:\n\n{temiz[:3000]}",
                    target_capability="code"
                )
                temiz_gen = saf_kodu_ayikla(genisletme, task.target_file)
                if len(temiz_gen) > len(temiz):
                    temiz = temiz_gen
                    print(f"   💡 [{self.agent_id}]: Kod akran model tarafından {len(temiz)} bayta zenginleştirildi.")

            dom = self.blackboard.dom_haritasini_al()
            onay, sebep, nihai = golge_ajan_denetle(task.task_id, temiz, task.target_file, dom, task.instruction)
            if onay:
                return saf_kodu_ayikla(nihai, task.target_file)
            else:
                print(f"   ⚠️ [{self.agent_id}] Gölge Denetçi uyarısı: {sebep}. Otomatik düzeltiliyor...")
                try:
                    onarim_prompt = (
                        f"GÖREV: {task.instruction}\nHEDEF DOSYA: {task.target_file}\n"
                        f"GÖLGE DENETÇİ TESPİTİ: {sebep}\n"
                        f"MEVCUT KOD:\n```\n{temiz}\n```\n\n"
                        f"Lütfen bu hatayı düzelterek sadece eksiksiz, çalışan saf kodu üret."
                    )
                    tamir_kodu = gemini_service.generate_with_retry(
                        prompt=onarim_prompt,
                        system_instruction="Sen kıdemli bir kod onarım uzmanısın. Hataları düzelt ve sadece saf kodu üret."
                    )
                    if tamir_kodu and len(tamir_kodu.strip()) > 100:
                        return saf_kodu_ayikla(tamir_kodu, task.target_file)
                except Exception as ex_repair:
                    print(f"   ⚠️ [{self.agent_id}] Otomatik düzeltme hatası: {ex_repair}")
                return saf_kodu_ayikla(nihai, task.target_file)

        except Exception as e:
            print(f"   ⚠️ [{self.agent_id}] Birincil NIM modeli hatası ({e}). Hızlı alternatif NIM & Gemini kurtarması deneniyor...")

            alt_m = nim_service.get_best_model_for_capability("fast", exclude={self.model_id})
            if alt_m and alt_m != self.model_id and nim_service._is_model_available(alt_m):
                try:
                    print(f"   🔄 [{self.agent_id}] Hızlı NIM alternatifi deneniyor: {alt_m.split('/')[-1]}")
                    raw_alt = nim_service.complete_with_retry(
                        model_id=alt_m,
                        messages=messages,
                        temperature=0.15,
                        max_tokens=8192,
                        max_retries=2,
                        timeout=55.0,
                        disable_thinking=True
                    )
                    temiz_alt = saf_kodu_ayikla(raw_alt, task.target_file)
                    if len(temiz_alt) > 80:
                        return temiz_alt
                except Exception as ex_alt:
                    print(f"   ⚠️ [{self.agent_id}] Alternatif NIM modeli de yanıt vermedi ({ex_alt}).")

            try:
                print(f"   🔄 [{self.agent_id}] Kurtarma için Gemini (doğrudan) devreye alınıyor...")
                res = gemini_service.generate_with_retry(
                    prompt=kullanici,
                    system_instruction=sistem,
                    temperature=0.1,
                    allow_nim_fallback=False
                )
                temiz_gemini = saf_kodu_ayikla(res, task.target_file)
                if len(temiz_gemini) > 80:
                    return temiz_gemini
            except Exception as ge:
                print(f"   ❌ [{self.agent_id}] Tüm model havuzu tükendi: {ge}")

            if task.target_file.endswith(".md"):
                return f"# {task.title}\n\n## 1. Genel Bakış ve Kapsam\n{task.instruction}\n\n## 2. Sistem Mimarisi ve Bileşenler\nProje modülleri otonom Şef-Amele döngüsü içinde koordine edilmiş ve modüler yapı kurulmuştur.\n\n## 3. Çalıştırma Yönergeleri\nÜretilen kod dosyalarını tarayıcıda veya uygun derleyicide çalıştırabilirsiniz."

            raise RuntimeError(f"Amele [{self.agent_id}] '{task.target_file}' dosyasını üretemedi. Modeller yanıt vermedi.")

    def _enter_waiting_sync(self, task: TaskItem):
        """Amele ajan işi bitince WAITING_SYNC modunda dinlemeye geçer."""
        self.state = AgentState.WAITING_SYNC
        task.status = TaskStatus.REVIEW_PENDING
        agent_registry.update_state(self.agent_id, AgentState.WAITING_SYNC, final_output=self.latest_output)
        event_bus.publish(EVENT_WAITING_SYNC, self.agent_id, {
            "task_id": task.task_id,
            "target_file": task.target_file
        })

        print(f"   ⏳ [{self.agent_id}] İş bitti -> 'WAITING_SYNC' modunda dinliyor (Zaman aşımı: {self.sync_timeout:.0f}s)...")
        baslangic = time.time()

        while not self._stop_event.is_set():
            gecen = time.time() - baslangic
            kalan = self.sync_timeout - gecen
            if kalan <= 0 and self.state != AgentState.SYNC_TIMED_OUT:
                print(f"   ⏱️ [{self.agent_id}] WAITING_SYNC süresi doldu ({self.sync_timeout:.0f}s); Şef QA onayı beklenmeye devam ediliyor (Mühürlenmedi)...")
                self.state = AgentState.SYNC_TIMED_OUT
                task.status = TaskStatus.REVIEW_PENDING
                agent_registry.update_state(self.agent_id, AgentState.SYNC_TIMED_OUT)
                event_bus.publish(EVENT_SYNC_TIMED_OUT, self.agent_id, {"task_id": task.task_id})

            try:
                msg = self.inbox.get(timeout=1.5)
            except queue.Empty:
                agent_registry.update_heartbeat(self.agent_id)
                continue

            m_type = msg.get("type")

            if m_type == EVENT_TASK_APPROVED:
                self.state = AgentState.APPROVED
                task.status = TaskStatus.APPROVED
                agent_registry.update_state(self.agent_id, AgentState.APPROVED)
                print(f"   ✅ [{self.agent_id}] Şef onayı alındı! Görev mühürlendi.")
                break

            elif m_type == EVENT_REVISION_REQUESTED:
                feedback = msg["event"].data.get("feedback", "Kodu gözden geçir ve eksikleri gider.")
                print(f"   🔄 [{self.agent_id}] Şef revizyon istedi: '{feedback[:60]}...'. Yeniden üretiliyor...")
                self.state = AgentState.WORKING
                task.status = TaskStatus.IN_PROGRESS
                agent_registry.update_state(self.agent_id, AgentState.WORKING)
                try:
                    yeni_kod = self._execute_generation(task, revision_note=feedback)
                except Exception as rev_err:
                    print(f"   ❌ [{self.agent_id}] Revizyon üretim hatası: {rev_err}")
                    task.status = TaskStatus.FAILED
                    task.error = str(rev_err)
                    self.state = AgentState.TERMINATED
                    agent_registry.update_state(self.agent_id, AgentState.TERMINATED)
                    self._stop_event.set()
                    break
                self.latest_output = yeni_kod
                task.output = yeni_kod
                self.blackboard.set_artifact(task.target_file, yeni_kod)
                self.blackboard.cikti_yaz(task.task_id, yeni_kod, task.target_file)
                self.state = AgentState.WAITING_SYNC
                task.status = TaskStatus.REVIEW_PENDING
                agent_registry.update_state(self.agent_id, AgentState.WAITING_SYNC, final_output=yeni_kod)
                baslangic = time.time()

            elif m_type == EVENT_TERMINATE_ALL:
                break

    def consult_peer_agent(self, specific_question: str, target_capability: str = "general") -> str:
        """
        🤝 AKRAN AJAN DANIŞMA MEKANİZMASI (Peer-to-Peer Inter-Agent Consultation):
        Bir amele ajan, kod yazarken karmaşık bir alt problemde havuzdaki diğer uzman
        bir AI ajanından yardım ister.
        """
        if not nim_service.client or not nim_service.has_healthy_fast_model():
            return ""
        peer_model = nim_service.get_best_model_for_capability("fast" if target_capability == "general" else target_capability, exclude={self.model_id})
        kisa_m = peer_model.split('/')[-1]
        print(f"   🤝 [{self.agent_id} -> Akran Ajan ({kisa_m})]: '{specific_question[:50]}...' danışılıyor...")
        event_bus.publish(EVENT_PEER_CONSULTATION, self.agent_id, {
            "question": specific_question,
            "peer_model": peer_model,
            "capability": target_capability
        })
        try:
            yanit = nim_service.complete_with_retry(
                model_id=peer_model,
                messages=[
                    {"role": "system", "content": f"Sen {target_capability} alanında dünya standartlarında uzman bir yardımcı yapay zeka ajanısın. Diğer amele ajanın sorusuna doğrudan saf, optimize ve eksiksiz çözüm üret. Asla lafı uzatma, sadece saf kod/veri üret."},
                    {"role": "user", "content": specific_question}
                ],
                temperature=0.1,
                max_tokens=3000,
                max_retries=1,
                timeout=30.0,
                disable_thinking=True
            )
            print(f"   💡 [{self.agent_id}]: Akran modelden ({kisa_m}) uzman çözüm alındı ({len(yanit)} bayt).")
            return yanit.strip()
        except Exception as e:
            print(f"   ⚠️ Akran danışma uyarısı: {e}")
            return ""

    def terminate(self):
        """Ajanı kapatır."""
        self._stop_event.set()
        self.state = AgentState.TERMINATED
        agent_registry.update_state(self.agent_id, AgentState.TERMINATED)

def isci_ajani_calistir(model_id: str, sistem_rolu: str, gorev_talimati: str, adim_no: int, dosya_adi: str = "", dom_haritasi: dict = None, hedef_klasor: str = "") -> str:
    from infrastructure.nim_client import nim_service
    messages = [
        {"role": "system", "content": sistem_rolu},
        {"role": "user", "content": gorev_talimati}
    ]
    try:
        raw = nim_service.complete_with_retry(model_id=model_id, messages=messages, temperature=0.15, max_tokens=8000)
        return saf_kodu_ayikla(raw, dosya_adi)
    except Exception:
        res = gemini_service.generate_with_retry(prompt=gorev_talimati, system_instruction=sistem_rolu, temperature=0.1)
        return saf_kodu_ayikla(res, dosya_adi)
