import threading
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

class AgentState(str, Enum):
    REGISTERED = "REGISTERED"
    IDLE = "IDLE"
    WORKING = "WORKING"
    WAITING_SYNC = "WAITING_SYNC"
    APPROVED = "APPROVED"
    SYNC_TIMED_OUT = "SYNC_TIMED_OUT"
    TERMINATED = "TERMINATED"

@dataclass
class AgentInfo:
    agent_id: str
    capability: str
    model_id: str
    state: AgentState = AgentState.REGISTERED
    current_task_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    intermediate_data: Dict[str, Any] = field(default_factory=dict)
    final_output: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "capability": self.capability,
            "model_id": self.model_id,
            "state": self.state.value,
            "current_task_id": self.current_task_id,
            "last_heartbeat": self.last_heartbeat,
            "has_output": bool(self.final_output)
        }

class AgentRegistry:
    """
    Canlı Amele Ajan Kayıt Defteri (Agent Registry).
    Tüm ajanların sicilini, durumunu, modelini ve son nabzını tutar.
    """
    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._lock = threading.RLock()

    def register(self, agent_id: str, capability: str, model_id: str, metadata: Optional[dict] = None) -> AgentInfo:
        with self._lock:
            info = AgentInfo(
                agent_id=agent_id,
                capability=capability,
                model_id=model_id,
                state=AgentState.REGISTERED,
                metadata=metadata or {}
            )
            self._agents[agent_id] = info
            return info

    def get(self, agent_id: str) -> Optional[AgentInfo]:
        with self._lock:
            return self._agents.get(agent_id)

    def update_state(self, agent_id: str, state: AgentState, **kwargs):
        with self._lock:
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                agent.state = state
                agent.last_heartbeat = time.time()
                for k, v in kwargs.items():
                    if hasattr(agent, k):
                        setattr(agent, k, v)

    def update_heartbeat(self, agent_id: str):
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].last_heartbeat = time.time()

    def get_by_state(self, state: AgentState) -> List[AgentInfo]:
        with self._lock:
            return [a for a in self._agents.values() if a.state == state]

    def get_active_agents(self) -> List[AgentInfo]:
        with self._lock:
            return [a for a in self._agents.values() if a.state != AgentState.TERMINATED]

    def get_all(self) -> List[AgentInfo]:
        with self._lock:
            return list(self._agents.values())

    def clear(self):
        with self._lock:
            self._agents.clear()

agent_registry = AgentRegistry()
