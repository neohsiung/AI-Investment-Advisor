from typing import List
import pandas as pd
from sqlalchemy import text
import uuid
from src.data.database import get_db_connection
from src.services.memory_service import IMemoryRepository, ReportMemoryItem

class SqliteMemoryRepository(IMemoryRepository):
    def get_recent_reports(self, user_id: str, report_type: str, limit: int) -> List[ReportMemoryItem]:
        conn = get_db_connection()
        try:
            # We filter by user_id and report_type
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
                # row keys: 0=id, 1=user_id, 2=date, 3=content, 4=summary, 5=report_type
                # Depending on driver, row might be accessible by name or index. 
                # Safe access via index or mapping.
                
                # Check if report_type matches (it should)
                
                item = ReportMemoryItem(
                    user_id=row[1],
                    report_type=row[5] if row[5] else report_type,
                    report_date=row[2],
                    full_content=row[3],
                    compressed_summary=row[4]
                )
                items.append(item)
            return items
        except Exception as e:
            # Fallback or simple error logging
            print(f"Error fetching memory reports: {e}")
            return []
        finally:
            conn.close()

    def save_report(self, item: ReportMemoryItem) -> None:
        conn = get_db_connection()
        try:
            # Check if exists (idempotency based on date/type/user?)
            # Or just insert new. reports table has ID primary key.
            # We generate a new ID if not provided, but here we are creating a new record mostly.
            
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
            conn.commit()
        except Exception as e:
            print(f"Error saving memory report: {e}")
        finally:
            conn.close()
