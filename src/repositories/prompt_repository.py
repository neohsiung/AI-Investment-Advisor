from abc import ABC, abstractmethod
from typing import Any
from sqlalchemy import text
from datetime import datetime
from src.data.database import BaseRepository, get_db_engine
import uuid

class IPromptRepository(ABC):
    """
    Interface for Prompt Repository.
    提示詞儲存庫介面。
    """
    @abstractmethod
    def log_change(self, agent_name: str, reason: str, old_prompt: str, new_prompt: str, diff: str) -> None:
        """
        Log a change to an agent's prompt.
        記錄代理人提示詞的變更。
        """
        pass

class PromptRepositoryImpl(BaseRepository, IPromptRepository):
    """
    Implementation of IPromptRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IPromptRepository。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def log_change(self, agent_name: str, reason: str, old_prompt: str, new_prompt: str, diff: str) -> None:
        """
        Log a change to an agent's prompt.
        記錄代理人提示詞的變更。
        """
        with self.engine.begin() as conn:
            log_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            query = text('''
                INSERT INTO prompt_history (id, timestamp, target_agent, reason, original_prompt, new_prompt, diff_content)
                VALUES (:id, :timestamp, :target_agent, :reason, :original_prompt, :new_prompt, :diff_content)
            ''')
            conn.execute(query, {
                "id": log_id,
                "timestamp": timestamp,
                "target_agent": agent_name,
                "reason": reason,
                "original_prompt": old_prompt,
                "new_prompt": new_prompt,
                "diff_content": diff
            })

# Legacy alias
# @deprecated: Use PromptRepositoryImpl
SqlitePromptRepository = PromptRepositoryImpl
