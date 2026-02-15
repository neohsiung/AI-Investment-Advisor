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
