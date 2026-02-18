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
        
        Args:
            agent_id (str): Unique ID for the execution context. (執行上下文的唯一 ID)
            
        Returns:
            Optional[Tuple[str, str]]: (last_input_hash, last_output) or None. (最後輸入雜湊與最後輸出，或 None)
        """
        pass
        
    @abstractmethod
    def save_state(self, agent_id: str, agent_name: str, input_hash: str, output: str) -> None:
        """
        Save the current state of an agent execution.
        儲存代理人執行的當前狀態。
        
        Args:
            agent_id (str): Unique ID for the execution context. (執行上下文的唯一 ID)
            agent_name (str): Name of the agent. (代理人名稱)
            input_hash (str): Hash of the current input. (當前輸入的雜湊)
            output (str): The execution output to cache. (要快取的執行輸出)
        """
        pass

class AlchemyAgentStateRepository(BaseRepository, IAgentStateRepository):
    """
    Implementation of IAgentStateRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IAgentStateRepository。
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
        Save the current state of an agent execution.
        儲存代理人執行的當前狀態。
        """
        with self.engine.begin() as conn:
            ts = datetime.now().isoformat()
            # Note: INSERT OR REPLACE is SQLite specific. For Postgres we'd use ON CONFLICT.
            # BaseRepository.is_sqlite can be used to branch.
            if self.is_sqlite:
                query = text("""
                    INSERT OR REPLACE INTO agent_states (id, agent_name, last_input_hash, last_run_time, last_output) 
                    VALUES (:id, :name, :hash, :ts, :output)
                """)
            else:
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

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyAgentStateRepository
