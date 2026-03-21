"""
Three-Tier Memory Architecture — Domain Interfaces + Infrastructure Adapters.
三層記憶體架構 — 領域介面 + 基礎設施轉接器。

Tier 1: Working Memory (in-process, ephemeral per turn)
  - Holds current message history, tool results, scratchpad
  
Tier 2: Session Storage (persisted per session, WAL checkpoint)
  - STATE.md / Agent state across context flushes

Tier 3: Long-Term Memory (persisted across sessions, vector-backed)
  - pgvector semantic search, council minutes, experience replay

遵循規範:
  - 規範一 (Clean Architecture): 介面在 Domain 層
  - 規範四 (模組化設計): 各層獨立可測試
  - 規範九 (Hybrid Strategy): Raw SQL for vector search
  - 規範十 (Safe-SQL-Only): Parameterized queries
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Domain Interfaces (Layer 0 — Pure Abstractions)
# ═══════════════════════════════════════════════════════

class IWorkingMemory(ABC):
    """
    Tier 1: In-process ephemeral memory for a single agent turn.
    第一層：單一 Agent 回合的進程內暫時記憶。
    """

    @abstractmethod
    def get_messages(self) -> List[Dict[str, str]]:
        """Get current message history."""
        ...

    @abstractmethod
    def add_message(self, role: str, content: str) -> None:
        """Append a message to history."""
        ...

    @abstractmethod
    def get_scratchpad(self) -> Dict[str, Any]:
        """Get ephemeral scratchpad data."""
        ...

    @abstractmethod
    def set_scratchpad(self, key: str, value: Any) -> None:
        """Set scratchpad key-value."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all working memory."""
        ...

    @abstractmethod
    def estimate_tokens(self) -> int:
        """Estimate total token count in working memory."""
        ...


class ISessionStorage(ABC):
    """
    Tier 2: Session-scoped persistent storage (survives context flush).
    第二層：Session 範圍的持久儲存（存活於上下文刷新之後）。
    """

    @abstractmethod
    def save_checkpoint(self, session_id: str, state: Dict[str, Any]) -> None:
        """Persist session checkpoint."""
        ...

    @abstractmethod
    def load_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session checkpoint."""
        ...

    @abstractmethod
    def save_wal(self, agent_name: str, wal_state: str) -> None:
        """Write WAL state to persistent storage."""
        ...

    @abstractmethod
    def load_wal(self, agent_name: str) -> Optional[str]:
        """Load WAL state from persistent storage."""
        ...


class ILongTermMemory(ABC):
    """
    Tier 3: Long-term persistent memory (cross-session, vector-backed).
    第三層：跨 Session 的持久記憶（向量支援）。
    """

    @abstractmethod
    def store(self, user_id: str, content: str, embedding: List[float] = None, metadata: Dict = None) -> str:
        """Store a memory entry. Returns memory_id."""
        ...

    @abstractmethod
    def search(self, query_text: str = None, query_vector: List[float] = None, user_id: str = None, limit: int = 5) -> List[Dict]:
        """Search memories by text or vector similarity."""
        ...


# ═══════════════════════════════════════════════════════
# Infrastructure Adapters (Concrete Implementations)
# ═══════════════════════════════════════════════════════

class InMemoryWorkingMemory(IWorkingMemory):
    """
    Tier 1 Adapter: In-process list-based working memory.
    """

    def __init__(self):
        self._messages: List[Dict[str, str]] = []
        self._scratchpad: Dict[str, Any] = {}

    def get_messages(self) -> List[Dict[str, str]]:
        return self._messages

    def add_message(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})

    def get_scratchpad(self) -> Dict[str, Any]:
        return self._scratchpad.copy()

    def set_scratchpad(self, key: str, value: Any) -> None:
        self._scratchpad[key] = value

    def clear(self) -> None:
        self._messages.clear()
        self._scratchpad.clear()

    def estimate_tokens(self) -> int:
        return sum(len(m.get("content", "")) // 4 for m in self._messages)

    def truncate_to_checkpoint(self, system_msg: Dict[str, str], wal_content: str) -> None:
        """
        Replace messages with system prompt + WAL restoration.
        用系統提示 + WAL 還原替換訊息。
        """
        self._messages.clear()
        self._messages.append(system_msg)
        self._messages.append({
            "role": "user",
            "content": f"Session Restored from Checkpoint:\n\n{wal_content}\n\nPlease continue where you left off."
        })


class FileSessionStorage(ISessionStorage):
    """
    Tier 2 Adapter: File-based session storage (STATE.md).
    """

    def __init__(self, workspace_path: str = ""):
        self._workspace_path = workspace_path

    def save_checkpoint(self, session_id: str, state: Dict[str, Any]) -> None:
        path = os.path.join(self._workspace_path, f"CHECKPOINT_{session_id}.json")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **state
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"SessionStorage: Saved checkpoint {session_id}")

    def load_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self._workspace_path, f"CHECKPOINT_{session_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_wal(self, agent_name: str, wal_state: str) -> None:
        state_path = os.path.join(self._workspace_path, "STATE.md")
        os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            f.write(
                f"# Session Checkpoint: {datetime.now().isoformat()}\n\n"
                f"{wal_state}"
            )
        logger.info(f"SessionStorage: WAL saved for {agent_name}")

    def load_wal(self, agent_name: str) -> Optional[str]:
        state_path = os.path.join(self._workspace_path, "STATE.md")
        if not os.path.exists(state_path):
            return None
        with open(state_path, "r", encoding="utf-8") as f:
            return f.read()


class HybridMemoryAdapter(ILongTermMemory):
    """
    Tier 3 Adapter: Wraps existing HybridMemory as ILongTermMemory.
    第三層轉接器：封裝既有 HybridMemory 為 ILongTermMemory 介面。
    
    This adapter allows the legacy HybridMemory to participate
    in the new 3-tier architecture without rewriting its internals.
    """

    def __init__(self, hybrid_memory=None):
        if hybrid_memory is None:
            from src.infrastructure.memory.memory_manager import HybridMemory
            hybrid_memory = HybridMemory()
        self._inner = hybrid_memory

    def store(self, user_id: str, content: str, embedding: List[float] = None, metadata: Dict = None) -> str:
        return self._inner.add_memory(
            user_id=user_id,
            content=content,
            embedding=embedding or [],
            metadata=metadata or {}
        )

    def search(self, query_text: str = None, query_vector: List[float] = None, user_id: str = None, limit: int = 5) -> List[Dict]:
        return self._inner.search(
            query_text=query_text,
            query_vector=query_vector,
            user_id=user_id,
            limit=limit
        )

    @property
    def inner(self):
        """Access the underlying HybridMemory for legacy compatibility."""
        return self._inner


# ═══════════════════════════════════════════════════════
# Composite: Three-Tier Memory Manager
# ═══════════════════════════════════════════════════════

class ThreeTierMemory:
    """
    Facade that composes the three memory tiers.
    組合三層記憶體的門面物件。

    Usage:
        mem = ThreeTierMemory(workspace_path="workspace/agent")
        mem.working.add_message("user", "Hello")
        mem.session.save_wal("Agent", "state...")
        mem.longterm.store("user1", "AAPL analysis result")
    """

    def __init__(
        self,
        working: Optional[IWorkingMemory] = None,
        session: Optional[ISessionStorage] = None,
        longterm: Optional[ILongTermMemory] = None,
        workspace_path: str = "",
    ):
        self.working: IWorkingMemory = working or InMemoryWorkingMemory()
        self.session: ISessionStorage = session or FileSessionStorage(workspace_path)
        self.longterm: ILongTermMemory = longterm or HybridMemoryAdapter()

    def flush_working_to_session(self, agent_name: str, wal_state: str) -> None:
        """
        Transfer working memory state to session checkpoint via WAL.
        透過 WAL 將工作記憶狀態轉移至 Session 檢查點。
        """
        self.session.save_wal(agent_name, wal_state)

    def restore_from_session(self, agent_name: str, system_msg: Dict[str, str]) -> bool:
        """
        Restore working memory from session WAL if available.
        若系統可用，從 session WAL 還原工作記憶。

        Returns True if restoration occurred.
        """
        wal = self.session.load_wal(agent_name)
        if wal and isinstance(self.working, InMemoryWorkingMemory):
            self.working.truncate_to_checkpoint(system_msg, wal)
            return True
        return False
