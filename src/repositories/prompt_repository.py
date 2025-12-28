from abc import ABC, abstractmethod
from sqlalchemy import text
from datetime import datetime
from src.data.database import get_db_connection
import uuid

class IPromptRepository(ABC):
    @abstractmethod
    def log_change(self, agent_name: str, reason: str, old_prompt: str, new_prompt: str, diff: str):
        pass

class SqlitePromptRepository(IPromptRepository):
    def log_change(self, agent_name: str, reason: str, old_prompt: str, new_prompt: str, diff: str):
        with get_db_connection() as conn:
            try:
                log_id = str(uuid.uuid4())
                timestamp = datetime.now().isoformat()
                conn.execute(text('''
                    INSERT INTO prompt_history (id, timestamp, target_agent, reason, original_prompt, new_prompt, diff_content)
                    VALUES (:id, :timestamp, :target_agent, :reason, :original_prompt, :new_prompt, :diff_content)
                '''), {
                    "id": log_id,
                    "timestamp": timestamp,
                    "target_agent": agent_name,
                    "reason": reason,
                    "original_prompt": old_prompt,
                    "new_prompt": new_prompt,
                    "diff_content": diff
                })
                conn.commit()
            except Exception as e:
                # We can log here if logger passed, or just re-raise/print
                print(f"Error logging prompt change: {e}")
