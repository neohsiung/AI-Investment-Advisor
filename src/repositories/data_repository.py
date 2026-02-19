from abc import ABC, abstractmethod
from typing import Any
import pandas as pd
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

class IDataRepository(ABC):
    """
    Interface for Data Repository.
    資料儲存庫介面。
    """
    @abstractmethod
    def get_table_preview(self, table_name: str, user_id: str, limit: int = 100) -> pd.DataFrame:
        """
        Get a preview of a specific table for a user.
        取得特定使用者的資料表預覽。
        
        Args:
            table_name (str): Name of the table to preview. (要預覽的資料表名稱)
            user_id (str): ID of the user. (使用者 ID)
            limit (int): Maximum number of rows to return. (回傳的最大行數)
            
        Returns:
            pd.DataFrame: Preview data. (預覽資料)
        """
        pass

class AlchemyDataRepository(BaseRepository, IDataRepository):
    """
    Implementation of IDataRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IDataRepository。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def get_table_preview(self, table_name: str, user_id: str, limit: int = 100) -> pd.DataFrame:
        """
        Get a preview of a specific table for a user.
        取得特定使用者的資料表預覽。
        """
        # Whitelist validation
        allowed_tables = ["transactions", "daily_snapshots", "cash_flows", "positions", "reports", "settings", "prompt_history"]
        if table_name not in allowed_tables:
            raise ValueError("Invalid table name")

        with self.engine.connect() as conn:
            # Using f-string safely because of whitelist above
            query = text(f"SELECT * FROM {table_name} WHERE user_id = :uid ORDER BY 1 DESC LIMIT :limit")  # nosec B608
            df = pd.read_sql(query, conn, params={"uid": user_id, "limit": limit})
            return df

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyDataRepository
