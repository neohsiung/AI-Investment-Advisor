"""
EventQueueRepository — Database access for event_queue table.

Handles CRUD and batch operations for the tiered event aggregation system.
Uses raw SQL for performance (no ORM overhead for bulk operations).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.data.models import EventQueue

logger = logging.getLogger(__name__)


class EventQueueRepository(BaseRepository):
    """Repository for event_queue table with raw SQL batch operations."""

    def __init__(self, engine=None):
        engine = engine or get_db_engine()
        super().__init__(engine)

    def insert_event(
        self,
        user_id: str,
        event_type: str,
        content: dict,
        tier: str = EventQueue.TIER_P2,
        priority: int = 0,
    ) -> str:
        """Insert a new pending event into the queue."""
        event_id = str(uuid4())
        now = datetime.now(timezone.utc)
        with self.session as sess:
            sess.execute(
                text("""
                INSERT INTO event_queue (id, user_id, event_type, content, tier, priority, status, created_at)
                VALUES (:id, :user_id, :event_type, CAST(:content AS jsonb), :tier, :priority, 'pending', :created_at)
                """),
                {
                    "id": event_id,
                    "user_id": user_id,
                    "event_type": event_type,
                    "content": json.dumps(content),
                    "tier": tier,
                    "priority": priority,
                    "created_at": now,
                },
            )
            sess.commit()
        logger.debug(f"EventQueue: inserted {event_id} [{tier}] {event_type}")
        return event_id

    def mark_processed(self, event_ids: List[str], batch_id: Optional[str] = None):
        """Mark events as analyzed."""
        if not event_ids:
            return
        now = datetime.now(timezone.utc)
        with self.session as sess:
            sess.execute(
                text("""
                UPDATE event_queue
                SET status = 'analyzed', processed_at = :now,
                    batch_id = COALESCE(:batch_id, batch_id)
                WHERE id = ANY(:ids)
                """),
                {"ids": event_ids, "batch_id": batch_id, "now": now},
            )
            sess.commit()

    def pull_batch(
        self,
        user_id: str,
        tier: str = EventQueue.TIER_P0,
        limit: int = 10,
        batch_mode: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Pull pending events for a given tier. If batch_mode=True, marks them
        as 'processing' and assigns a batch_id atomically.
        """
        batch_id = str(uuid4()) if batch_mode else None

        with self.session as sess:
            rows = sess.execute(
                text("""
                UPDATE event_queue
                SET status = 'processing',
                    batch_id = COALESCE(:batch_id, batch_id)
                WHERE id IN (
                    SELECT id FROM event_queue
                    WHERE user_id = :user_id
                      AND tier = :tier
                      AND status = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, event_type, content, tier, priority, created_at
                """),
                {
                    "user_id": user_id,
                    "tier": tier,
                    "limit": limit,
                    "batch_id": batch_id,
                },
            )
            # Materialize the RETURNING rows BEFORE commit (2026-07-12):
            # commit() invalidates the cursor, and under NullPool (Celery
            # workers) iterating afterwards raises psycopg2.InterfaceError
            # "cursor already closed" — this silently broke every digest run.
            # 先取回 RETURNING 結果再 commit,否則 NullPool 下游標已關閉。
            fetched = rows.fetchall()
            sess.commit()
            results = [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "content": row.content,
                    "tier": row.tier,
                    "priority": row.priority,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "batch_id": batch_id,
                }
                for row in fetched
            ]

        logger.info(f"EventQueue: pulled {len(results)} events [{tier}] batch={batch_id}")
        return results

    def get_pending_counts(self, user_id: str) -> Dict[str, int]:
        """Get pending event counts per tier (for agent scheduling decisions)."""
        with self.session as sess:
            rows = sess.execute(
                text("""
                SELECT tier, COUNT(*) as cnt
                FROM event_queue
                WHERE user_id = :user_id AND status = 'pending'
                GROUP BY tier
                ORDER BY tier
                """),
                {"user_id": user_id},
            ).fetchall()

        counts = {row.tier: row.cnt for row in rows}
        # Ensure all tiers are represented
        for t in [EventQueue.TIER_P0, EventQueue.TIER_P1, EventQueue.TIER_P2, EventQueue.TIER_P3]:
            counts.setdefault(t, 0)
        return counts

    def release_batch(self, event_ids: List[str]):
        """Release processing events back to pending."""
        if not event_ids:
            return
        with self.session as sess:
            sess.execute(
                text("""
                UPDATE event_queue
                SET status = 'pending', batch_id = NULL
                WHERE id = ANY(:ids)
                """),
                {"ids": event_ids},
            )
            sess.commit()
        logger.info(f"EventQueue: released {len(event_ids)} events back to pending")

    def archive_old_events(self, older_than_hours: int = 72):
        """Archive events older than N hours (called by housekeeping cron)."""
        with self.session as sess:
            result = sess.execute(
                text("""
                UPDATE event_queue
                SET status = 'archived'
                WHERE status IN ('analyzed', 'pending', 'processing')
                  AND created_at < NOW() - INTERVAL '1 hour' * :hours
                """),
                {"hours": older_than_hours},
            )
            sess.commit()
            count = result.rowcount
        if count:
            logger.info(f"EventQueue: archived {count} events older than {older_than_hours}h")
        return count