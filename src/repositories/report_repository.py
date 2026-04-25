from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import pandas as pd
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine, AsyncBaseRepository, get_async_db_engine
from sqlalchemy.ext.asyncio import AsyncSession

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

    @abstractmethod
    def get_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific report by its ID.
        根據 ID 取得特定報告。
        """
        pass

class IAsyncReportRepository(ABC):
    """
    Async interface for Report Repository.
    """
    @abstractmethod
    async def get_latest_reports(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Returns reports as a list of dicts for async handling.
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

    def get_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific report by its ID.
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT title as summary, content, user_id, report_type 
                FROM reports 
                WHERE id = :id
            """)
            result = conn.execute(query, {"id": report_id}).first()
            if result:
                return dict(result._mapping)
            return None

    def save(self, user_id: str, report_type: str, summary: str, content: str, title: Optional[str] = None) -> bool:
        """
        Save a report to the database.
        將報告存入資料庫。
        """
        from datetime import datetime
        target_title = title or summary
        
        # v11.1: Generate UUID for the report if not provided
        import uuid
        report_id = str(uuid.uuid4())
        
        with self.engine.connect() as conn:
            query = text("""
                INSERT INTO reports (id, user_id, report_type, summary, content, title, created_at)
                VALUES (:id, :uid, :type, :summary, :content, :title, :created_at)
            """)
            conn.execute(query, {
                "id": report_id,
                "uid": user_id,
                "type": report_type,
                "summary": summary,
                "content": content,
                "title": target_title,
                "created_at": datetime.now()
            })
            conn.commit()
            return report_id

class AsyncAlchemyReportRepository(AsyncBaseRepository, IAsyncReportRepository):
    """
    Async SQLAlchemy implementation of IReportRepository.
    v8.0: High-performance non-blocking implementation.
    """
    def __init__(self, engine: Any = None):
        AsyncBaseRepository.__init__(self, engine or get_async_db_engine())

    async def get_latest_reports(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get latest reports as a list of dictionaries.
        """
        async with await self.get_session() as session:
            query = text("""
                SELECT created_at as date, title as summary, content 
                FROM reports 
                WHERE user_id = :uid 
                ORDER BY created_at DESC 
                LIMIT :limit
            """)
            result = await session.execute(query, {"uid": user_id, "limit": limit})
            rows = result.fetchall()
            return [dict(r._mapping) for r in rows]

    async def save_report(self, user_id: str, report_type: str, summary: str, content: str, title: Optional[str] = None) -> bool:
        from datetime import datetime
        target_title = title or summary
        
        async with await self.get_session() as session:
            query = text("""
                INSERT INTO reports (id, user_id, report_type, title, content, created_at)
                VALUES (:id, :uid, :type, :title, :content, :created_at)
            """)
            # v8.0: Use UUID for ID
            import uuid
            await session.execute(query, {
                "id": str(uuid.uuid4()),
                "uid": user_id,
                "type": report_type,
                "title": target_title,
                "content": content,
                "created_at": datetime.now()
            })
            await session.commit()
            return True

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyReportRepository
