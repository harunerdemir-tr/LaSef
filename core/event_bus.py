"""
═══════════════════════════════════════════════════════════════════════════════
👑 LASEF OLAY VERİYOLU VE SENKRONİZASYON MERKEZİ (core/event_bus.py)
═══════════════════════════════════════════════════════════════════════════════
"""
import threading
import time
from typing import Callable, Dict, List, Any

EVENT_AGENT_REGISTERED = "AGENT_REGISTERED"
EVENT_TASK_DISPATCHED = "TASK_DISPATCHED"
EVENT_TASK_STARTED = "TASK_STARTED"
EVENT_INTERMEDIATE_DATA = "INTERMEDIATE_DATA"
EVENT_DATA_REQUEST = "DATA_REQUEST"
EVENT_WAITING_SYNC = "WAITING_SYNC"
EVENT_REVISION_REQUESTED = "REVISION_REQUESTED"
EVENT_TASK_APPROVED = "TASK_APPROVED"
EVENT_SYNC_TIMED_OUT = "SYNC_TIMED_OUT"
EVENT_PEER_CONSULTATION = "PEER_CONSULTATION"
EVENT_TERMINATE_ALL = "TERMINATE_ALL"
EVENT_TIMELINE_STAGE = "TIMELINE_STAGE"
EVENT_SCAN_PROGRESS = "SCAN_PROGRESS"

class Event:
    def __init__(self, event_type: str, sender_id: str, data: Any = None):
        self.event_type = event_type
        self.sender_id = sender_id
        self.data = data or {}
        self.timestamp = time.time()

    def __repr__(self):
        return f"<Event {self.event_type} from {self.sender_id}>"

class EventBus:
    """
    Ajanlar arası Olay Veriyolu (In-Memory Pub/Sub Event Bus).
    Thread-safe çalışır; senkron veya asenkron olay dinlemeyi destekler.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._global_listeners: List[Callable[[Event], None]] = []
        self._history: List[Event] = []
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, callback: Callable[[Event], None]):
        """Belirli bir olay türüne abone olur."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def subscribe_all(self, callback: Callable[[Event], None]):
        """Tüm olayları dinleyen global dinleyici ekler."""
        with self._lock:
            self._global_listeners.append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Event], None]):
        with self._lock:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def publish(self, event_type: str, sender_id: str, data: Any = None):
        """Bir olay fırlatır ve abonelere iletir."""
        event = Event(event_type, sender_id, data)
        with self._lock:
            self._history.append(event)
            listeners = list(self._subscribers.get(event_type, []))
            globals_ = list(self._global_listeners)

        for cb in listeners:
            try:
                cb(event)
            except Exception as e:
                print(f"⚠️ [EventBus Hatası ({event_type})]: {e}")

        for cb in globals_:
            try:
                cb(event)
            except Exception as e:
                print(f"⚠️ [EventBus Global Dinleyici Hatası]: {e}")

    def get_history(self, event_type: str = None) -> List[Event]:
        with self._lock:
            if event_type:
                return [e for e in self._history if e.event_type == event_type]
            return list(self._history)

    def clear(self):
        with self._lock:
            self._history.clear()

event_bus = EventBus()
