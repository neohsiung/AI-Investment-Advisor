from typing import List
from sqlalchemy import text
from src.data.database import get_db_connection
from src.services.memory_service import IMemoryRepository, ReportMemoryItem
import json

class SqliteMemoryRepository(IMemoryRepository):
    def get_recent_reports(self, user_id: str, report_type: str, limit: int) -> List[ReportMemoryItem]:
        query = text("""
            SELECT report_date, full_content, compressed_summary, key_findings
            FROM report_memory
            WHERE user_id = :uid AND report_type = :rt
            ORDER BY report_date DESC
            LIMIT :lim
        """)
        items = []
        with get_db_connection() as conn:
            result = conn.execute(query, {"uid": user_id, "rt": report_type, "lim": limit})
            for row in result.mappings():
                items.append(ReportMemoryItem(
                    user_id=user_id,
                    report_type=report_type,
                    report_date=row['report_date'],
                    full_content=row['full_content'],
                    compressed_summary=row['compressed_summary'],
                    key_findings=json.loads(row['key_findings']) if row['key_findings'] else None
                ))
        return items

    def save_report(self, item: ReportMemoryItem) -> None:
        query = text("""
            INSERT INTO report_memory (user_id, report_type, report_date, full_content, compressed_summary, key_findings)
            VALUES (:uid, :rt, :rd, :fc, :cs, :kf)
            ON CONFLICT(user_id, report_type, report_date) DO UPDATE SET
            full_content=excluded.full_content,
            compressed_summary=excluded.compressed_summary
        """)
        with get_db_connection() as conn:
            conn.execute(query, {
                "uid": item.user_id,
                "rt": item.report_type,
                "rd": item.report_date,
                "fc": item.full_content,
                "cs": item.compressed_summary,
                "kf": json.dumps(item.key_findings) if item.key_findings else None
            })
            conn.commit()
