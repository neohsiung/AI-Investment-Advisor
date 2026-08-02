from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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

        from sqlalchemy import MetaData, Table, select, desc

        metadata = MetaData()
        
        with self.engine.connect() as conn:
            # Reflect the specific table
            table = Table(table_name, metadata, autoload_with=conn)
            
            # Dynamically build query based on column existence
            if 'user_id' in table.columns:
                stmt = select(table).where(table.c.user_id == user_id).order_by(desc(table.columns.items()[0][1])).limit(limit)
                df = pd.read_sql(stmt, conn)
            else:
                # If no user_id, show global data (safely as it is whitelisted)
                stmt = select(table).order_by(desc(table.columns.items()[0][1])).limit(limit)
                df = pd.read_sql(stmt, conn)
                
            return df

    def get_recent_event_logs(self, days: int = 7, limit: int = 50) -> Any:
        """
        Get recent event logs across the system.
        """
        from sqlalchemy import text
        with self.engine.connect() as conn:
            try:
                rows = conn.execute(text("""
                    SELECT title, content FROM event_logs
                    WHERE created_at >= CURRENT_DATE - (CAST(:days AS TEXT) || ' days')::INTERVAL
                    ORDER BY created_at DESC
                    LIMIT :limit
                """), {"days": days, "limit": limit}).fetchall()
                return rows
            except Exception as e:
                import logging; logging.warning(f'Exception in data_repository.py: {e}', exc_info=True)
                return []

    def get_recent_aggregated_reports(self, days: int = 7, limit: int = 10) -> Any:
        """
        Get recent reports aggregated across users for system analysis.
        """
        from sqlalchemy import text
        with self.engine.connect() as conn:
            try:
                rows = conn.execute(text("""
                    SELECT content FROM reports
                    WHERE created_at >= CURRENT_DATE - (CAST(:days AS TEXT) || ' days')::INTERVAL
                    ORDER BY created_at DESC
                    LIMIT :limit
                """), {"days": days, "limit": limit}).fetchall()
                return rows
            except Exception as e:
                import logging; logging.warning(f'Exception in data_repository.py: {e}', exc_info=True)
                return []

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyDataRepository
