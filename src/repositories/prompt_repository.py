from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
    def log_change(self, agent_name: str, reason: str, old_prompt: str, new_prompt: str, diff: str, user_id: str) -> None:
        """
        Log a change to an agent's prompt.
        記錄代理人提示詞的變更。
        """
        pass

    @abstractmethod
    def get_history(self, user_id: str, limit: int = 50) -> Any:
        """
        Get the prompt optimization history.
        取得提示詞優化歷史記錄。
        """
        pass

class AlchemyPromptRepository(BaseRepository, IPromptRepository):
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

    def log_change(self, agent_name: str, reason: str, old_prompt: str, new_prompt: str, diff: str, user_id: str) -> None:
        """
        Log a change to an agent's prompt.
        記錄代理人提示詞的變更。
        """
        try:
            with self.engine.begin() as conn:
                log_id = str(uuid.uuid4())
                timestamp = datetime.now().isoformat()
                query = text('''
                    INSERT INTO prompt_history (id, timestamp, target_agent, reason, original_prompt, new_prompt, diff_content, user_id)
                    VALUES (:id, :timestamp, :target_agent, :reason, :original_prompt, :new_prompt, :diff_content, :user_id)
                ''')
                conn.execute(query, {
                    "id": log_id,
                    "timestamp": timestamp,
                    "target_agent": agent_name,
                    "reason": reason,
                    "original_prompt": old_prompt,
                    "new_prompt": new_prompt,
                    "diff_content": diff,
                    "user_id": user_id
                })
        except Exception as e:
            # We don't want to fail the whole agent run if logging prompt fails
            print(f"Error logging prompt change: {e}")

    def get_history(self, user_id: str, limit: int = 50) -> Any:
        """
        Retrieves the history of prompt optimizations for a user.
        檢索使用者的提示詞優化歷史記錄。
        """
        try:
            import pandas as pd
            from sqlalchemy import text
            query = text("SELECT timestamp, target_agent, reason, diff_content FROM prompt_history WHERE user_id = :uid ORDER BY timestamp DESC LIMIT :limit")
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={"uid": user_id, "limit": limit})
                return df
        except Exception as e:
            import logging; logging.warning(f'Exception in prompt_repository.py: {e}', exc_info=True)
            import pandas as pd
            return pd.DataFrame()

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyPromptRepository
