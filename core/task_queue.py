import threading
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW_PENDING = "REVIEW_PENDING"
    REVISION_NEEDED = "REVISION_NEEDED"
    APPROVED = "APPROVED"
    FAILED = "FAILED"

@dataclass
class TaskItem:
    task_id: int
    title: str
    capability: str
    instruction: str
    target_file: str
    dependencies: List[int] = field(default_factory=list)
    model_id: str = ""
    assigned_agent_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    output: Optional[str] = None
    revision_feedback: Optional[str] = None
    revision_count: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "capability": self.capability,
            "target_file": self.target_file,
            "dependencies": self.dependencies,
            "model_id": self.model_id,
            "assigned_agent_id": self.assigned_agent_id,
            "status": self.status.value,
            "has_output": bool(self.output)
        }

class TaskQueue:
    """
    Şef ve Ameleler Arası Bağımlılık Duyarlı Görev Kuyruğu (Task Queue).
    Bağımlılıkları tamamlanan görevlerin amelelere dağıtılmasını sağlar.
    """
    def __init__(self):
        self._tasks: Dict[int, TaskItem] = {}
        self._lock = threading.RLock()

    def add_task(self, task: TaskItem):
        with self._lock:
            self._tasks[task.task_id] = task

    def get_task(self, task_id: int) -> Optional[TaskItem]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[TaskItem]:
        with self._lock:
            return list(self._tasks.values())

    def _resolve_dep_id(self, dep: Any) -> Optional[int]:
        """Bağımlılık referansını (int adım no veya string dosya adı) task_id'ye çözer."""
        if isinstance(dep, int) and dep in self._tasks:
            return dep
        if isinstance(dep, str):
            dep_str = dep.strip()
            if dep_str.isdigit() and int(dep_str) in self._tasks:
                return int(dep_str)
            dep_low = dep_str.lower().replace("\\", "/")
            for tid, t_obj in self._tasks.items():
                tf = (t_obj.target_file or "").lower().replace("\\", "/")
                if tf == dep_low or tf.endswith("/" + dep_low) or dep_low.endswith("/" + tf):
                    return tid
        return None

    def get_ready_tasks(self) -> List[TaskItem]:
        """
        Bağımlılıkları 'APPROVED' olan ve yürütülmeye hazır (PENDING veya REVISION_NEEDED) görevleri döndürür.
        Eğer bir görevin bağımlı olduğu üst kök FAILED olmuşsa, deadlock'u önlemek için görevi de FAILED olarak işaretler.
        """
        with self._lock:
            ready = []
            for t in self._tasks.values():
                if t.status in [TaskStatus.PENDING, TaskStatus.REVISION_NEEDED]:
                    resolved_deps = []
                    for raw_dep in t.dependencies:
                        r_id = self._resolve_dep_id(raw_dep)
                        if r_id is not None and r_id != t.task_id:
                            resolved_deps.append(r_id)

                    has_failed_dep = any(
                        self._tasks[dep_id].status == TaskStatus.FAILED
                        for dep_id in resolved_deps
                    )
                    if has_failed_dep:
                        t.status = TaskStatus.FAILED
                        t.revision_feedback = "Kök bağımlılık başarısız olduğu için dal sonlandırıldı."
                        continue

                    deps_met = all(
                        self._tasks[dep_id].status == TaskStatus.APPROVED
                        for dep_id in resolved_deps
                    )
                    if deps_met:
                        ready.append(t)
            return ready

    def mark_in_progress(self, task_id: int, agent_id: str):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.IN_PROGRESS
                self._tasks[task_id].assigned_agent_id = agent_id

    def submit_for_review(self, task_id: int, output: str):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.REVIEW_PENDING
                self._tasks[task_id].output = output

    def request_revision(self, task_id: int, feedback: str):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.REVISION_NEEDED
                self._tasks[task_id].revision_feedback = feedback
                self._tasks[task_id].revision_count += 1

    def approve_task(self, task_id: int):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.APPROVED
                self._tasks[task_id].completed_at = time.time()

    def mark_failed(self, task_id: int, error_msg: str = ""):
        """Görevi kalıcı olarak başarısız işaretler."""
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.FAILED
                self._tasks[task_id].revision_feedback = error_msg
                self._tasks[task_id].completed_at = time.time()

    def is_all_approved(self) -> bool:
        with self._lock:
            if not self._tasks:
                return False
            return all(t.status == TaskStatus.APPROVED for t in self._tasks.values())

    def is_all_finished(self) -> bool:
        """Tüm görevler nihai duruma (APPROVED veya FAILED) ulaştı mı?"""
        with self._lock:
            if not self._tasks:
                return False
            return all(t.status in [TaskStatus.APPROVED, TaskStatus.FAILED] for t in self._tasks.values())

    def clear(self):
        with self._lock:
            self._tasks.clear()

task_queue = TaskQueue()
