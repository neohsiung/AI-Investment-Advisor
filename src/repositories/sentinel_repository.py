import logging
import json
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

logger = logging.getLogger(__name__)

class ISentinelRepository(ABC):
    """
    Interface for Sentinel Repository.
    Sentinel 儲存庫介面。
    """
    @abstractmethod
    def get_all_thresholds(self) -> Dict[str, float]:
        """Fetch all thresholds from DB."""
        pass

    @abstractmethod
    def update_threshold(self, key: str, value: float, reviewer: str, rationale: str = "") -> None:
        """Update or Insert a threshold."""
        pass

    @abstractmethod
    def seed_defaults(self, defaults: Dict[str, float]) -> None:
        """Seed initial values if table is empty."""
        pass

    @abstractmethod
    def is_duplicate_alert(self, title: str, content: str, hours: int = 24, signal_id: str = None) -> bool:
        """Check if an identical alert exists in event_logs."""
        pass

    @abstractmethod
    def get_last_signal_value(self, signal_id: str) -> float:
        """Retrieve the last recorded numeric value for a signal_id."""
        pass

    @abstractmethod
    def log_alert(self, title: str, content: str, metadata: Dict = None) -> None:
        """Log an alert to event_logs."""
        pass

    @abstractmethod
    def close_session(self) -> None:
        """Close the database session."""
        pass

class AlchemySentinelRepository(BaseRepository, ISentinelRepository):
    """
    Implementation of ISentinelRepository handling dynamic thresholds and alerts (PostgreSQL Strictly).
    實作 ISentinelRepository，處理動態閾值與警報 (PostgreSQL 專用)。
    """

    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))

    def get_all_thresholds(self) -> Dict[str, float]:
        """
        Fetch all thresholds (Core SQL for performance).
        從資料庫獲取所有閾值。
        """
        query = text("SELECT key, value FROM sentinel_thresholds")
        thresholds = {}
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query)
                for row in result:
                    thresholds[row.key] = float(row.value)
        except Exception as e:
            logger.error(f"Failed to fetch sentinel thresholds: {e}")
        return thresholds

    def update_threshold(self, key: str, value: float, reviewer: str, rationale: str = "") -> None:
        """
        Update or Insert a threshold (Upsert).
        更新或插入閾值。
        """
        query = text("""
            INSERT INTO sentinel_thresholds (key, value, last_optimized_by, roi_hint, updated_at)
            VALUES (:key, :value, :reviewer, :rationale, :updated_at)
            ON CONFLICT(key) DO UPDATE SET
                value = EXCLUDED.value,
                last_optimized_by = EXCLUDED.last_optimized_by,
                roi_hint = EXCLUDED.roi_hint,
                updated_at = EXCLUDED.updated_at
        """)
        try:
            with self.engine.begin() as conn:
                conn.execute(query, {
                    "key": key,
                    "value": value,
                    "reviewer": reviewer,
                    "rationale": rationale,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"SentinelRepository: Updated {key} to {value} by {reviewer}")
        except Exception as e:
            logger.error(f"Failed to update sentinel threshold {key}: {e}")

    def seed_defaults(self, defaults: Dict[str, float]) -> None:
        """
        Seed initial values if table is empty.
        若表為空則插入預設值。
        """
        existing = self.get_all_thresholds()
        for key, value in defaults.items():
            if key not in existing:
                self.update_threshold(key, value, "System", "Initial Seed")

    def is_duplicate_alert(self, title: str, content: str, hours: int = 24, signal_id: str = None) -> bool:
        """
        Check for duplicate alerts within a timeframe (PostgreSQL JSONB optimized).
        檢查在特定時間範圍內是否有重複警報。
        """
        try:
            with self.engine.connect() as conn:
                if signal_id:
                    query = text("""
                        SELECT COUNT(*) FROM event_logs 
                        WHERE source = 'Sentinel'
                        AND metadata @> CAST(:signal_json AS JSONB)
                        AND timestamp >= NOW() - CAST(:hours || ' hours' AS INTERVAL)
                    """)
                    signal_json = json.dumps({"signal_id": signal_id})
                    count = conn.execute(query, {"signal_json": signal_json, "hours": str(hours)}).scalar()
                    
                    if count > 0:
                        return True

                query_exact = text("""
                    SELECT COUNT(*) FROM event_logs 
                    WHERE source = 'Sentinel'
                    AND title = :title
                    AND content = :content
                    AND timestamp >= NOW() - CAST(:hours || ' hours' AS INTERVAL)
                """)
                count = conn.execute(query_exact, {"title": title, "content": content, "hours": str(hours)}).scalar()
                
                return count > 0
        except Exception as e:
            logger.error(f"SentinelRepository: Failed to check duplicate alert: {e}")
            return False

    def get_last_signal_value(self, signal_id: str) -> float:
        """
        Retrieve the last recorded numeric value for a signal (PostgreSQL JSONB optimized).
        獲取訊號的最後記錄值。
        """
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT (metadata->>'value')::float FROM event_logs 
                    WHERE source = 'Sentinel' 
                    AND metadata @> CAST(:signal_json AS JSONB)
                    ORDER BY timestamp DESC LIMIT 1
                """)
                signal_json = json.dumps({"signal_id": signal_id})
                val = conn.execute(query, {"signal_json": signal_json}).scalar()
                
                return float(val) if val is not None else 0.0
        except Exception as e:
            logger.error(f"SentinelRepository: Failed to get last signal value for {signal_id}: {e}")
            return 0.0

    def log_alert(self, title: str, content: str, metadata: Dict = None) -> None:
        """
        Log an alert to event_logs.
        將警報記錄至 event_logs。
        """
        query = text("""
            INSERT INTO event_logs (id, timestamp, source, level, title, content, metadata, processed_by)
            VALUES (:id, :timestamp, 'Sentinel', 'WARNING', :title, :content, :metadata, 'SentinelService')
        """)
        try:
            with self.engine.begin() as conn:
                current_time = datetime.now(timezone.utc)
                conn.execute(query, {
                    "id": str(uuid.uuid4()),
                    "timestamp": current_time,
                    "title": title,
                    "content": content,
                    "metadata": json.dumps(metadata or {}),
                })
                logger.debug(f"SentinelRepository: Logged alert '{title}' at {current_time}")
        except Exception as e:
            logger.error(f"SentinelRepository: Failed to log alert: {e}")
