import logging
from typing import Dict, Optional, List
from sqlalchemy import text
from datetime import datetime
from src.data.database import get_db_engine

logger = logging.getLogger(__name__)

class SentinelRepository:
    """
    Manages dynamic thresholds for SentinelService.
    Allows Agents to review, optimize, and persist parameters.
    """

    def __init__(self):
        self.engine = get_db_engine()

    def get_all_thresholds(self) -> Dict[str, float]:
        """
        Fetch all thresholds from DB.
        """
        query = "SELECT key, value FROM sentinel_thresholds"
        thresholds = {}
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                for row in result:
                    thresholds[row[0]] = row[1]
        except Exception as e:
            logger.error(f"Failed to fetch sentinel thresholds: {e}")
        return thresholds

    def update_threshold(self, key: str, value: float, reviewer: str, rationale: str = ""):
        """
        Update or Insert a threshold.
        """
        query = """
            INSERT INTO sentinel_thresholds (key, value, last_optimized_by, roi_hint, updated_at)
            VALUES (:key, :value, :reviewer, :rationale, :updated_at)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                last_optimized_by = excluded.last_optimized_by,
                roi_hint = excluded.roi_hint,
                updated_at = excluded.updated_at
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query), {
                    "key": key,
                    "value": value,
                    "reviewer": reviewer,
                    "rationale": rationale,
                    "updated_at": datetime.now().isoformat()
                })
                conn.commit()
                logger.info(f"SentinelRepository: Updated {key} to {value} by {reviewer}")
        except Exception as e:
            logger.error(f"Failed to update sentinel threshold {key}: {e}")

    def seed_defaults(self, defaults: Dict[str, float]):
        """
        Seed initial values if table is empty.
        """
        existing = self.get_all_thresholds()
        for key, value in defaults.items():
            if key not in existing:
                self.update_threshold(key, value, "System", "Initial Seed")

    def is_duplicate_alert(self, title: str, content: str, hours: int = 24) -> bool:
        """
        Check if an identical alert exists in event_logs within the last N hours.
        """
        import hashlib
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        # Check explicit content hash (if we stored it) OR title match + distinct content check
        # For simplicity in 'event_logs', we look for title match and recent timestamp
        # Ideally event_logs should store hash, but we can compare title and fuzzy content
        
        query = """
            SELECT COUNT(*) FROM event_logs 
            WHERE title = :title 
            AND source = 'Sentinel'
            AND timestamp >= datetime('now', :modifier)
        """
        # SQLite 'now', '-24 hours'
        modifier = f"-{hours} hours"
        
        try:
            with self.engine.connect() as conn:
                # Note: This is an approximate check by title. 
                # If content varies slightly (e.g. valid timestamps), it might not match.
                # For strictly identical alerts (same VIX level etc), title comparison might fail if title contains values.
                # Let's rely on Title for now if it's specific enough, or update implementation to hash.
                
                # Better approach: The user complaint showed specific values in content.
                # "1 個風險訊號偵測到" as title is generic.
                # We need to check the CONTENT. "event_logs" has a content column.
                
                # Let's try to match content roughly or use a hash if we decided to store it.
                # Since we haven't migrated event_logs to have a hash column, we will query by intent.
                
                # Refined Query: Check for similar log in recent time
                # We will check if the Exact Content matches.
                query_exact = """
                    SELECT COUNT(*) FROM event_logs 
                    WHERE source = 'Sentinel'
                    AND title = :title
                    AND content = :content
                    AND timestamp >= datetime('now', :modifier)
                """
                
                # Compatibility for Postgres vs SQLite time
                if 'sqlite' not in str(self.engine.url):
                    query_exact = """
                        SELECT COUNT(*) FROM event_logs 
                        WHERE source = 'Sentinel'
                        AND title = :title
                        AND content = :content
                        AND timestamp >= NOW() - INTERVAL :hours_pg
                    """
                    count = conn.execute(text(query_exact), {"title": title, "content": content, "hours_pg": f"{hours} hours"}).scalar()
                else:
                    count = conn.execute(text(query_exact), {"title": title, "content": content, "modifier": modifier}).scalar()
                
                return count > 0
        except Exception as e:
            logger.error(f"Failed to check duplicate alert: {e}")
            return False

    def log_alert(self, title: str, content: str, metadata: Dict = None):
        """
        Log an alert to event_logs for history tracking.
        """
        import json
        query = """
            INSERT INTO event_logs (id, timestamp, source, level, title, content, metadata, processed_by)
            VALUES (:id, :timestamp, 'Sentinel', 'WARNING', :title, :content, :metadata, 'SentinelService')
        """
        import uuid
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query), {
                    "id": str(uuid.uuid4()),
                    "timestamp": datetime.now().isoformat(),
                    "title": title,
                    "content": content,
                    "metadata": json.dumps(metadata or {}),
                })
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log alert: {e}")
