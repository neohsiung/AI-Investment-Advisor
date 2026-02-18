from typing import List, Any
import pandas as pd
from sqlalchemy import text
import uuid
from src.data.database import BaseRepository, get_db_engine
from src.services.memory_service import IMemoryRepository, ReportMemoryItem

class AlchemyMemoryRepository(BaseRepository, IMemoryRepository):
    """
    Implementation of IMemoryRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IMemoryRepository。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def get_recent_reports(self, user_id: str, report_type: str, limit: int) -> List[ReportMemoryItem]:
        """
        Get recent reports for a specific user and report type.
        取得特定使用者與報告類型的近期報告。
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT id, user_id, date, content, summary, report_type 
                FROM reports 
                WHERE user_id = :uid AND report_type = :rtype 
                ORDER BY date DESC 
                LIMIT :limit
            """)
            rows = conn.execute(query, {"uid": user_id, "rtype": report_type, "limit": limit}).fetchall()
            
            items = []
            for row in rows:
                item = ReportMemoryItem(
                    user_id=row.user_id,
                    report_type=row.report_type if row.report_type else report_type,
                    report_date=row.date,
                    full_content=row.content,
                    compressed_summary=row.summary
                )
                items.append(item)
            return items

    def save_report(self, item: ReportMemoryItem) -> None:
        """
        Save a report memory item.
        儲存報告記憶項目。
        """
        with self.engine.begin() as conn:
            new_id = str(uuid.uuid4())
            query = text("""
                INSERT INTO reports (id, user_id, date, content, summary, report_type) 
                VALUES (:id, :uid, :date, :content, :summary, :rtype)
            """)
            conn.execute(query, {
                "id": new_id,
                "uid": item.user_id,
                "date": item.report_date,
                "content": item.full_content,
                "summary": item.compressed_summary,
                "rtype": item.report_type
            })

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyMemoryRepository
