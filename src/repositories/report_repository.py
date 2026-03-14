from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import pandas as pd
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

class IReportRepository(ABC):
    """
    Interface for Report Repository.
    報告儲存庫介面。
    """
    @abstractmethod
    def get_latest_reports(self, user_id: str, limit: int = 100) -> pd.DataFrame:
        """
        Get latest reports for a specific user as a DataFrame.
        取得特定使用者的最新報告。
        """
        pass

class AlchemyReportRepository(BaseRepository, IReportRepository):
    """
    Implementation of IReportRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IReportRepository。
    """
    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))

    def get_latest_reports(self, user_id: str, limit: int = 100) -> pd.DataFrame:
        """
        Get latest reports as a DataFrame.
        取得最新報告的資料表。
        """
        target_uid = user_id
        target_uid = user_id

        with self.engine.connect() as conn:
            # v4.1.2 Patch: Enforce user-specific filtering and TIMESTAMPTZ support
            query = text("""
                SELECT created_at as date, title as summary, content 
                FROM reports 
                WHERE user_id = :uid 
                ORDER BY created_at DESC 
                LIMIT :limit
            """)
            return pd.read_sql(query, conn, params={"uid": target_uid, "limit": limit})

    def save(self, user_id: str, report_type: str, summary: str, content: str, title: Optional[str] = None) -> bool:
        """
        Save a report to the database.
        將報告存入資料庫。
        """
        from datetime import datetime
        target_title = title or summary
        
        with self.engine.connect() as conn:
            query = text("""
                INSERT INTO reports (user_id, report_type, summary, content, title, created_at)
                VALUES (:uid, :type, :summary, :content, :title, :created_at)
            """)
            conn.execute(query, {
                "uid": user_id,
                "type": report_type,
                "summary": summary,
                "content": content,
                "title": target_title,
                "created_at": datetime.now()
            })
            conn.commit()
            return True

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyReportRepository
