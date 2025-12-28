from abc import ABC, abstractmethod
from typing import Optional, Tuple
from sqlalchemy import text
from datetime import datetime
from src.data.database import get_db_connection

class IAgentStateRepository(ABC):
    @abstractmethod
    def get_state(self, agent_id: str) -> Optional[Tuple[str, str]]:
        """
        Get the last known state for an agent execution context.
        Returns: (last_input_hash, last_output) or None
        """
        pass
        
    @abstractmethod
    def save_state(self, agent_id: str, agent_name: str, input_hash: str, output: str):
        """
        Save the current state of an agent execution.
        """
        pass

class SqliteAgentStateRepository(IAgentStateRepository):
    def get_state(self, agent_id: str) -> Optional[Tuple[str, str]]:
        with get_db_connection() as conn:
            row = conn.execute(text("SELECT last_input_hash, last_output FROM agent_states WHERE id = :id"), {"id": agent_id}).fetchone()
            if row:
                return row[0], row[1]
            return None

    def save_state(self, agent_id: str, agent_name: str, input_hash: str, output: str):
         with get_db_connection() as conn:
            ts = datetime.now().isoformat()
            conn.execute(text("""
                INSERT OR REPLACE INTO agent_states (id, agent_name, last_input_hash, last_run_time, last_output) 
                VALUES (:id, :name, :hash, :ts, :output)
            """), {
                "id": agent_id,
                "name": agent_name,
                "hash": input_hash,
                "ts": ts,
                "output": output
            })
            conn.commit()
