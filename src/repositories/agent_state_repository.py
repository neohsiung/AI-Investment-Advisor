from abc import ABC, abstractmethod
from typing import Optional, Tuple, Any
from sqlalchemy import text
from datetime import datetime
from src.data.database import BaseRepository, get_db_engine

class IAgentStateRepository(ABC):
    """
    Interface for Agent State Repository.
    代理人狀態儲存庫介面。
    """
    @abstractmethod
    def get_state(self, agent_id: str) -> Optional[Tuple[str, str]]:
        """
        Get the last known state for an agent execution context.
        取得代理人執行上下文的最後已知狀態。
        """
        pass
        
    @abstractmethod
    def save_state(self, agent_id: str, agent_name: str, input_hash: str, output: str) -> None:
        """
        Save the current state of an agent execution.
        儲存代理人執行的當前狀態。
        """
        pass

    @abstractmethod
    def close_session(self) -> None:
        """
        Close the database session.
        關閉資料庫工作階段。
        """
        pass

class AlchemyAgentStateRepository(BaseRepository, IAgentStateRepository):
    """
    Implementation of IAgentStateRepository using SQLAlchemy (PostgreSQL Optimized).
    使用 SQLAlchemy 實作的 IAgentStateRepository (PostgreSQL 優化)。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def get_state(self, agent_id: str) -> Optional[Tuple[str, str]]:
        """
        Get the last known state for an agent execution context.
        取得代理人執行上下文的最後已知狀態。
        """
        with self.engine.connect() as conn:
            query = text("SELECT last_input_hash, last_output FROM agent_states WHERE id = :id")
            row = conn.execute(query, {"id": agent_id}).fetchone()
            if row:
                return row[0], row[1]
            return None

    def save_state(self, agent_id: str, agent_name: str, input_hash: str, output: str) -> None:
        """
        Save the current state of an agent execution using ON CONFLICT (Upsert).
        """
        with self.engine.begin() as conn:
            ts = datetime.now().isoformat()
            query = text("""
                INSERT INTO agent_states (id, agent_name, last_input_hash, last_run_time, last_output) 
                VALUES (:id, :name, :hash, :ts, :output)
                ON CONFLICT (id) DO UPDATE SET
                    agent_name = EXCLUDED.agent_name,
                    last_input_hash = EXCLUDED.last_input_hash,
                    last_run_time = EXCLUDED.last_run_time,
                    last_output = EXCLUDED.last_output
            """)
                
            conn.execute(query, {
                "id": agent_id,
                "name": agent_name,
                "hash": input_hash,
                "ts": ts,
                "output": output
            })
