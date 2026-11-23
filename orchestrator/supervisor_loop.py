"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF SÜPERVİZÖR DÖNGÜSÜ VE YÜRÜTÜCÜ (orchestrator/supervisor_loop.py)
═══════════════════════════════════════════════════════════════════════════════
📌 LASEF KORTEKS MANİFESTOSU — SÜPERVİZÖR MOTORU:
Bu modül, LaSef çoklu ajan orkestrasyonunun yürütme omurgasıdır (Supervisor Loop).
1. Şef'in (Gemini) planını alır.
2. Dinamik sayıda Amele Ajan (WorkerAgent) başlatır (Single Responsibility).
3. Bağımlılıkları DAG yapısında çözer, çıktılar tamamlandıkça görevleri dağıtır.
4. Ameleler WAITING_SYNC modunda beklerken Şef ve Hakem Konseyi QA denetimi yürütür.
5. Canlı Unity (UnityAutonomousPlaytester) ve Tarayıcı (WebAutonomousPlaytester)
   üzerinden bizzat Şefin Gözü (Vision Eye) ile görsel/kod doğrulaması yapar.
6. STANDART MCP İLKESİ: Projeye denenmemiş veya işe yaramayan yapay MCP kodları
   enjekte etmez; standart UPM/resmi araçları ve yerel çalışan köprüleri kullanır.
═══════════════════════════════════════════════════════════════════════════════
"""
import os
import re
import time
from typing import Dict, List, Any, Optional

from core.event_bus import (
    event_bus,
    EVENT_TASK_APPROVED,
    EVENT_REVISION_REQUESTED,
    EVENT_TERMINATE_ALL
)
from core.agent_registry import agent_registry, AgentState
from core.task_queue import TaskQueue, TaskItem, TaskStatus
from core.blackboard import SharedBlackboard, ProjectPlan
from agents.chef_supervisor import chef_supervisor
from agents.worker_agent import WorkerAgent, saf_kodu_ayikla
from infrastructure.gemini_client import gemini_service
from orchestrator.workspace_manager import kaydet_ve_raporla, sef_kod_denetimi
from orchestrator.self_healing_test import otonom_dogrula_ve_test_et
from orchestrator.visual_canvas import canli_dag_haritasini_ciz
from orchestrator.lifecycle_tracker import lifecycle_tracker
from core.team_pack_manager import TeamPackManager
from core.config_manager import load_config

class SupervisorOrchestrator:
    """
    Şef-Amele Çoklu Ajan Orkestrasyon Yürütücüsü (Supervisor Loop).
    - Şef'in planını alır.
    - Dinamik sayıda Amele Ajan (WorkerAgent) ayağa kaldırır (1 - 20+).
    - Bağımlılıkları çözer ve görevleri eşzamanlı kota sınırıyla (max 3-4) amelelere dağıtır.
    - Ameleler WAITING_SYNC modunda beklerken Şef QA denetimini yürütür.
    - Revizyon gerekirse geri gönderir, tamamsa onaylar.
    - Tüm ajanlar senkronize tamamlandığında sistemi temizce kapatır ve dosyaları yazar.
    """
    def __init__(self, sync_timeout: float = 300.0, max_concurrent_workers: int = 3):
        cfg = load_config()
        isci_cfg = cfg.get("isci", {}) if isinstance(cfg, dict) else {}
        self.sync_timeout = float(isci_cfg.get("sync_timeout", sync_timeout))
        self.max_concurrent_workers = int(isci_cfg.get("max_paralel", max_concurrent_workers))
        self.chef = chef_supervisor
        self.blackboard: Optional[SharedBlackboard] = None
        self.task_queue: TaskQueue = TaskQueue()
        self.workers: Dict[str, WorkerAgent] = {}
        self.last_plan: Optional[ProjectPlan] = None
        self.last_target_folder: str = ""
        self.last_artifacts: Dict[str, str] = {}
        self.last_architecture_contract: str = ""
        self.last_token_stats: Dict[str, int] = {}

    def execute(self, user_request: str, target_folder: str = "", source_context: str = "") -> str:
        baslangic_zamani = time.time()
        print("\n" + "═" * 65)
        print("🎭 [LaSef Orkestrası] Otonom Çoklu Ajan Süpervizör Döngüsü Başlatıldı")
        print("═" * 65)

        self.blackboard = SharedBlackboard(kaynak_dosya_baglami=source_context)
        self.task_queue.clear()
        agent_registry.clear()

        plan: ProjectPlan = self.chef.niyet_ve_gorev_plani_yap(user_request, source_context, blackboard=self.blackboard)
        self.last_plan = plan
        self.last_architecture_contract = getattr(plan, "architecture_contract", "") or ""
        lifecycle_tracker.advance_to_stage(1, f"Mimari Sözleşme kilitlendi ({len(plan.moduller)} modül hazırlandı).")

        if not target_folder:
            bulunan_klasor = None
            path_matches = re.findall(r"([A-Za-z]:\\[^\"'\n\r\(\)<>]+)", user_request)
            for p in path_matches:
                p_temiz = p.strip().rstrip("\\/.,;)")
                if os.path.exists(p_temiz) and os.path.isdir(p_temiz):
                    bulunan_klasor = p_temiz
                    break

            if bulunan_klasor:
                target_folder = os.path.abspath(bulunan_klasor)
                print(f"   📁 [Hedef Dizin Otomatik Tespit Edildi]: {target_folder}")
            else:
                target_folder = os.path.abspath(plan.proje_klasor_adi)
        else:
            target_folder = os.path.abspath(target_folder)

        for m in plan.moduller:
            task_item = TaskItem(
                task_id=m.adim,
                title=m.baslik,
                capability=getattr(m, 'capability', 'general'),
                instruction=m.gorev,
                target_file=m.dosya_adi,
                dependencies=m.bagimliliklar,
                model_id=m.model_id
            )
            self.task_queue.add_task(task_item)

        lifecycle_tracker.advance_to_stage(2, f"{len(plan.moduller)} uzman amele ajan dinamik başlatıldı.")
        print(f"\n🚀 [Amele Dağıtımı]: {len(plan.moduller)} Uzman Amele Ajan Dinamik Başlatılıyor...")
        for t in self.task_queue.get_all_tasks():
            agent_id = f"amele_{t.capability}_{t.task_id}"
            worker = WorkerAgent(
                agent_id=agent_id,
                capability=t.capability,
                blackboard=self.blackboard,
                model_id=t.model_id or None,
                sync_timeout=self.sync_timeout,
                target_folder=target_folder
            )
            worker.start()
            self.workers[agent_id] = worker

        print("\n👑 [Şef Gözetim Döngüsü]: Görev akışı ve canlı senkronizasyon izleniyor...")

        max_loop_seconds = max(3600.0, len(plan.moduller) * 600.0)
        loop_start = time.time()

        def _try_chef_rescue(task) -> bool:
            """Başarısız veya thread'i düşmüş görevi Baş Şef (Gemini) ile kurtarmayı dener."""
            if getattr(task, "_chef_rescued", False):
                return False
            task._chef_rescued = True
            print(f"\n   🚑 [Süpervizör Kurtarma]: '{task.target_file}' amelesi tamamlayamadı. Baş Şef (Gemini) doğrudan devralıyor...")
            try:
                scoped = self.blackboard.get_scoped_artifacts_for_task(task)
                baglam_txt = "\n\n".join(f"--- {fn} ---\n{code[:6000]}" for fn, code in list(scoped.items())[:6])
                kurtarma_prompt = (
                    f"Sen Baş Kod Mimarı Şefsin (Gemini). Görevi devralıyorsun.\n"
                    f"KULLANICI ANA HEDEFİ: {user_request}\n"
                    f"HEDEF DOSYA: {task.target_file}\n"
                    f"TALİMAT: {task.instruction}\n"
                    f"MEVCUT BAĞLAM DOSYALARI:\n{baglam_txt}\n\n"
                    f"Lütfen '{task.target_file}' dosyası için sıfır eksikle tam, çalışan saf kodu tek kod bloğunda üret."
                )
                raw_rescue = gemini_service.generate_with_retry(
                    prompt=kurtarma_prompt,
                    system_instruction="Sen Kıdemli Baş Kod Mimarısın. Yalnızca temiz, çalışan saf kodu üret.",
                    temperature=0.1,
                    allow_nim_fallback=False
                )
                rescued_code = saf_kodu_ayikla(raw_rescue, task.target_file)
                if len(rescued_code.strip()) > 60:
                    self.blackboard.set_artifact(task.target_file, rescued_code)
                    task.output = rescued_code
                    self.task_queue.approve_task(task.task_id)
                    print(f"   └ 🌟 [ŞEF KURTARMASI BAŞARILI]: '{task.target_file}' ({len(rescued_code)} bayt) mühürlendi.")
                    return True
            except Exception as rescue_err:
                print(f"   └ ❌ [Şef Kurtarması Başarısız]: '{task.target_file}' -> {rescue_err}")
            self.task_queue.mark_failed(task.task_id, getattr(task, "error", "Worker başarısız oldu"))
            return False

        while not self.task_queue.is_all_finished():
            if time.time() - loop_start > max_loop_seconds:
                aktif_calisan = any(w.state == AgentState.WORKING for w in self.workers.values())
                if not aktif_calisan:
                    print("⚠️ [Süpervizör Döngüsü]: Genel tavan zaman aşımına ulaşıldı. Mevcut durum finalize ediliyor.")
                    break

            aktif_calisan_sayisi = sum(1 for w in self.workers.values() if w.state == AgentState.WORKING)
            ready_tasks = self.task_queue.get_ready_tasks()
            for task in ready_tasks:
                if aktif_calisan_sayisi >= self.max_concurrent_workers:
                    break
                agent_id = f"amele_{task.capability}_{task.task_id}"
                worker = self.workers.get(agent_id)
                if worker and worker.state == AgentState.IDLE:
                    self.task_queue.mark_in_progress(task.task_id, agent_id)
                    worker.assign_task(task)
                    aktif_calisan_sayisi += 1

            for task in self.task_queue.get_all_tasks():
                agent_id = f"amele_{task.capability}_{task.task_id}"
                worker = self.workers.get(agent_id)

                thread_dead = bool(worker and getattr(worker, "worker_thread", None) and not worker.worker_thread.is_alive())
                if task.status == TaskStatus.FAILED or (thread_dead and task.status in [TaskStatus.IN_PROGRESS, TaskStatus.REVISION_NEEDED]):
                    if _try_chef_rescue(task):
                        continue

                if worker and worker.state in [AgentState.WAITING_SYNC, AgentState.SYNC_TIMED_OUT]:
                    if task.status in [TaskStatus.IN_PROGRESS, TaskStatus.REVIEW_PENDING, TaskStatus.REVISION_NEEDED]:
                        cikan_icerik = worker.latest_output or self.blackboard.get_artifact(task.target_file) or ""
                        print(f"\n🔍 [Şef QA Denetimi]: {worker.agent_id} ({task.target_file}) denetleniyor...")
                        lifecycle_tracker.advance_to_stage(3, f"{task.target_file} QA ve Hakem Konseyi denetiminde...")

                        onay, geri_bildirim = self.chef.qa_denetle_ve_onayla(
                            task=task,
                            cikan_icerik=cikan_icerik,
                            blackboard=self.blackboard,
                            use_council=True
                        )

                        if onay:
                            print(f"   └ ✅ [ŞEF ONAYI]: '{task.target_file}' başarıyla mühürlendi.")
                            self.task_queue.approve_task(task.task_id)
                            event_bus.publish(EVENT_TASK_APPROVED, "CHEF", {
                                "agent_id": worker.agent_id,
                                "task_id": task.task_id
                            })
                        else:
                            if task.revision_count >= 2:
                                print(f"   └ 👑 [ŞEF MÜDAHALESİ]: Amele 2 revizyon hakkını doldurdu. Baş Şef (Gemini) devreye girip '{task.target_file}' dosyasını doğrudan finalize ediyor...")
                                try:
                                    tamir_prompt = f"""Sen Baş Mimar Şefsin (Gemini). Amele ajanın yazdığı kod QA kontrolünden geçemedi.
QA Geri Bildirimi: {geri_bildirim}
Görev Açıklaması: {task.instruction}
Hedef Dosya: {task.target_file}

Amele Taslak Kodu:
\"\"\"
{cikan_icerik}
\"\"\"

Lütfen bu kodu eksiksiz, çalışan, tüm işlevleri tam ve QA geri bildirimindeki tüm eksikleri giderilmiş tek parça nihai kod olarak üret. Yalnızca temiz kodu markdown blokları içinde döndür."""
                                    duzeltilmis = gemini_service.generate_with_retry(
                                        prompt=tamir_prompt,
                                        system_instruction="Sen Baş Kod Mimarı Şefsin. Eksik veya hatalı kodları kusursuz tam kod olarak tamamlarsın."
                                    )
                                    nihai_tamir = saf_kodu_ayikla(duzeltilmis, task.target_file)
                                    if len(nihai_tamir.strip()) > 200:
                                        self.blackboard.set_artifact(task.target_file, nihai_tamir)
                                        task.output = nihai_tamir
                                        print(f"   └ 🌟 [ŞEF TAMİRİ BAŞARILI]: '{task.target_file}' Baş Şef tarafından kusursuz şekilde onarıldı ve mühürlendi.")
                                        self.task_queue.approve_task(task.task_id)
                                        event_bus.publish(EVENT_TASK_APPROVED, "CHEF", {
                                            "agent_id": worker.agent_id,
                                            "task_id": task.task_id
                                        })
                                        continue
                                except Exception as e_repair:
                                    print(f"   ⚠️ [Şef Tamir Hatası]: {e_repair}")

                            print(f"   └ 🔄 [ŞEF REVİZYONU (#{task.revision_count + 1})]: '{task.target_file}' -> {geri_bildirim}")
                            self.task_queue.request_revision(task.task_id, geri_bildirim)
                            event_bus.publish(EVENT_REVISION_REQUESTED, "CHEF", {
                                "agent_id": worker.agent_id,
                                "task_id": task.task_id,
                                "feedback": geri_bildirim
                            })

            time.sleep(1.0)

        for rem_task in self.task_queue.get_all_tasks():
            if rem_task.status == TaskStatus.FAILED and not getattr(rem_task, "_chef_rescued", False):
                _try_chef_rescue(rem_task)

        print("\n🏁 [Orkestrasyon Tamamlandı]: Amele ajanlar dinleme modundan çıkarılıyor...")
        event_bus.publish(EVENT_TERMINATE_ALL, "CHEF")
        for w in self.workers.values():
            w.terminate()

        uretilen_dosyalar = self.blackboard.get_all_artifacts()
        nihai_dosyalar = sef_kod_denetimi(user_request, uretilen_dosyalar)
        self.last_target_folder = target_folder
        self.last_artifacts = dict(nihai_dosyalar)
        self.last_token_stats = self.blackboard.get_token_stats() if self.blackboard else {}
        self.last_verification_passed = True
        rapor = kaydet_ve_raporla(target_folder, nihai_dosyalar, user_request, blackboard=self.blackboard)

        try:
            otonom_dogrula_ve_test_et(target_folder, nihai_dosyalar)
        except Exception as te:
            print(f"   ⚠️ [Test Denetimi]: {te}")

        if os.getenv("LASEF_ENABLE_CANVAS", "0") == "1":
            try:
                canli_dag_haritasini_ciz(plan.moduller, target_folder)
            except Exception:
                pass

        if os.getenv("LASEF_EXPORT_TEAM_PACK", "0") == "1":
            try:
                t_pack = TeamPackManager(target_folder)
                t_pack.pack_olustur(plan.proje_klasor_adi, [
                    {"adim": t.task_id, "baslik": t.title, "capability": t.capability, "model": t.model_id}
                    for t in self.task_queue.get_all_tasks()
                ])
            except Exception:
                pass

        cs_dosyalari = [f for f in nihai_dosyalar.keys() if f.lower().endswith(".cs")]
        is_unity_target = bool(target_folder and os.path.isdir(os.path.join(target_folder, "Assets")))
        if cs_dosyalari or is_unity_target:
            try:
                lifecycle_tracker.advance_to_stage(4, "Unity Editor köprüsüne bağlanıldı. Sahne hiyerarşisi taranıyor ve objeler kuruluyor...")
                from orchestrator.unity_autonomous_playtester import UnityAutonomousPlaytester
                playtester = UnityAutonomousPlaytester(target_folder)
                test_sonuclari = playtester.run_full_pipeline(user_request, nihai_dosyalar)
                if test_sonuclari.get("unity_connected"):
                    if not test_sonuclari.get("is_fully_successful", False):
                        self.last_verification_passed = False
                        rapor = rapor.replace(
                            "✅ PROJE BAŞARIYLA TAMAMLANDI!",
                            "⚠️ KODLAR ÜRETİLDİ ANCAK UNITY DERLEME / SAHNE DOĞRULAMA UYARISI MEVCUT!"
                        )
                        if not test_sonuclari.get("compilation_success", False):
                            rapor = (
                                f"🚨 UNITY C# DERLEME HATASI TESPİT EDİLDİ:\n{test_sonuclari.get('summary', '')}\n\n"
                                + rapor
                            )
                        elif not test_sonuclari.get("scene_built", True):
                            rapor = rapor.replace(
                                "Sahne ve bileşenler doğrudan canlı editöre aktarıldı.",
                                "⚠️ Sahne kurulumunda eksik tespit edildi (Kök nesne sayısı: 0). Lütfen derleme/sahne raporunu kontrol edin."
                            )
                    rapor += f"\n\n🎮 UNITY CANLI TEST & DOĞRULAMA RAPORU:\n{test_sonuclari.get('summary', '')}"
            except Exception as ue:
                print(f"   ⚠️ [Canlı Unity Otonom Test Hatası]: {ue}")

        html_dosyalari = [f for f in nihai_dosyalar.keys() if f.lower().endswith(".html")]
        if html_dosyalari:
            try:
                lifecycle_tracker.advance_to_stage(4, "Tarayıcı (Playwright) köprüsü başlatılıyor. 60 FPS render ve DOM doğrulanıyor...")
                from orchestrator.web_autonomous_playtester import WebAutonomousPlaytester
                web_tester = WebAutonomousPlaytester(target_folder)
                web_sonuclari = web_tester.run_full_pipeline(user_request, nihai_dosyalar)
                if web_sonuclari.get("browser_tested"):
                    rapor += f"\n\n🌐 CANLI TARAYICI DOĞRULAMA RAPORU:\n{web_sonuclari.get('summary', '')}"
            except Exception as we:
                print(f"   ⚠️ [Canlı Web Otonom Test Hatası]: {we}")

        py_blender = [
            f for f, kod in nihai_dosyalar.items()
            if f.lower().endswith(".py") and isinstance(kod, str) and "import bpy" in kod
        ]
        if py_blender:
            try:
                lifecycle_tracker.advance_to_stage(4, "Blender MCP köprüsü / Headless CLI doğrulaması başlatılıyor...")
                from orchestrator.blender_autonomous_runner import BlenderAutonomousRunner
                b_runner = BlenderAutonomousRunner(target_folder)
                b_res = b_runner.run_full_pipeline(user_request, nihai_dosyalar)
                if b_res.get("blender_tested"):
                    rapor += f"\n\n🎨 BLENDER MCP & DOĞRULAMA RAPORU:\n{b_res.get('summary', '')}"
            except Exception as be:
                print(f"   ⚠️ [Blender Otonom Test Hatası]: {be}")

        lifecycle_tracker.advance_to_stage(6, "Tüm üretim, QA ve doğrulama süreçleri başarıyla mühürlendi.")
        toplam_sure = time.time() - baslangic_zamani
        print(f"\n⏱️ Toplam Süreç Tamamlanma Süresi: {toplam_sure:.2f} saniye.")
        return rapor
