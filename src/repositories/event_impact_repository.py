"""
EventImpactRepository — Raw SQL database access for event_impact_biases table.
事件量化偏置之資料庫存取層（採用參數化原生 SQL 與多租戶隔離）。
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.domain.event_impact import EventImpact, EventScope, EventSentiment
from src.utils.logger import setup_logger

logger = setup_logger("EventImpactRepository")


class IEventImpactRepository(ABC):
    """Interface for Event Impact persistence."""

    @abstractmethod
    def insert_impact(self, impact: EventImpact) -> str:
        """Insert a newly analyzed event impact."""

    @abstractmethod
    def get_active_impacts(
        self,
        user_id: str,
        scope: Optional[EventScope] = None,
        ticker: Optional[str] = None,
    ) -> List[EventImpact]:
        """Fetch non-dismissed event impacts for a user."""

    @abstractmethod
    def dismiss_impact(self, user_id: str, impact_id: str) -> bool:
        """Mark an event impact as dismissed."""

    @abstractmethod
    def get_impact_by_id(self, user_id: str, impact_id: str) -> Optional[EventImpact]:
        """Retrieve a specific impact by ID and user_id."""


class AlchemyEventImpactRepository(BaseRepository, IEventImpactRepository):
    """PostgreSQL / SQLite implementation of EventImpactRepository using Raw SQL."""

    def __init__(self, db_path: Optional[str] = None, engine=None):
        eng = engine or get_db_engine(db_path)
        BaseRepository.__init__(self, eng)
        self._init_tables()

    def _init_tables(self) -> None:
        """Initialize table and indexes idempotently."""
        is_sqlite = "sqlite" in str(self.engine.url)

        if is_sqlite:
            queries = [
                text("""
                CREATE TABLE IF NOT EXISTS event_impact_biases (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    ticker TEXT,
                    category TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    summary TEXT,
                    sentiment TEXT NOT NULL,
                    initial_impact REAL NOT NULL,
                    half_life_hours REAL NOT NULL DEFAULT 36.0,
                    created_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    is_dismissed INTEGER NOT NULL DEFAULT 0
                );
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_event_impact_user_scope
                    ON event_impact_biases(user_id, scope, is_dismissed);
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_event_impact_user_ticker
                    ON event_impact_biases(user_id, ticker, is_dismissed);
                """),
            ]
        else:
            queries = [
                text("""
                CREATE TABLE IF NOT EXISTS event_impact_biases (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    scope VARCHAR(20) NOT NULL,
                    ticker VARCHAR(20),
                    category VARCHAR(50) NOT NULL,
                    headline TEXT NOT NULL,
                    summary TEXT,
                    sentiment VARCHAR(20) NOT NULL,
                    initial_impact NUMERIC(5, 2) NOT NULL,
                    half_life_hours NUMERIC(6, 2) NOT NULL DEFAULT 36.0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}'::jsonb,
                    is_dismissed BOOLEAN NOT NULL DEFAULT FALSE
                );
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_event_impact_user_scope
                    ON event_impact_biases(user_id, scope, is_dismissed, created_at DESC);
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_event_impact_user_ticker
                    ON event_impact_biases(user_id, ticker, is_dismissed, created_at DESC);
                """),
            ]

        for q in queries:
            try:
                with self.engine.begin() as conn:
                    conn.execute(q)
            except Exception as e:
                logger.warning(f"EventImpactRepository: table init notice: {e}")

    def insert_impact(self, impact: EventImpact) -> str:
        """Insert a newly analyzed event impact with parameterized query."""
        if not impact.id:
            impact.id = str(uuid4())

        is_sqlite = "sqlite" in str(self.engine.url)
        created_val = (
            impact.created_at.isoformat()
            if is_sqlite
            else impact.created_at
        )
        meta_json = json.dumps(impact.metadata) if isinstance(impact.metadata, dict) else "{}"

        scope_val = impact.scope.value if isinstance(impact.scope, EventScope) else str(impact.scope)
        sent_val = impact.sentiment.value if isinstance(impact.sentiment, EventSentiment) else str(impact.sentiment)
        ticker_val = impact.ticker.upper() if impact.ticker else None
        dismissed_val = 1 if is_sqlite and impact.is_dismissed else (True if impact.is_dismissed else False)
        if is_sqlite and not impact.is_dismissed:
            dismissed_val = 0

        query = text("""
            INSERT INTO event_impact_biases (
                id, user_id, scope, ticker, category, headline, summary,
                sentiment, initial_impact, half_life_hours, created_at, metadata, is_dismissed
            ) VALUES (
                :id, :user_id, :scope, :ticker, :category, :headline, :summary,
                :sentiment, :initial_impact, :half_life_hours, :created_at, :metadata, :is_dismissed
            )
        """)

        params = {
            "id": impact.id,
            "user_id": impact.user_id,
            "scope": scope_val,
            "ticker": ticker_val,
            "category": impact.category,
            "headline": impact.headline,
            "summary": impact.summary,
            "sentiment": sent_val,
            "initial_impact": float(impact.initial_impact),
            "half_life_hours": float(impact.half_life_hours),
            "created_at": created_val,
            "metadata": meta_json,
            "is_dismissed": dismissed_val,
        }

        with self.engine.begin() as conn:
            conn.execute(query, params)

        logger.info(
            f"EventImpactRepository: stored impact {impact.id} "
            f"[{impact.scope.value}] ticker={impact.ticker} initial={impact.initial_impact:+.2f}"
        )
        return impact.id

    def get_active_impacts(
        self,
        user_id: str,
        scope: Optional[EventScope] = None,
        ticker: Optional[str] = None,
    ) -> List[EventImpact]:
        """Fetch non-dismissed event impacts for a user with parameterized filters."""
        is_sqlite = "sqlite" in str(self.engine.url)
        dismissed_cond = "is_dismissed = 0" if is_sqlite else "is_dismissed = FALSE"

        clauses = ["user_id = :user_id", dismissed_cond]
        params: Dict[str, Any] = {"user_id": user_id}

        if scope:
            scope_val = scope.value if isinstance(scope, EventScope) else str(scope)
            clauses.append("scope = :scope")
            params["scope"] = scope_val

        if ticker:
            clauses.append("ticker = :ticker")
            params["ticker"] = ticker.upper()

        where_stmt = " AND ".join(clauses)
        query = text(f"""
            SELECT id, user_id, scope, ticker, category, headline, summary,
                   sentiment, initial_impact, half_life_hours, created_at, metadata, is_dismissed
            FROM event_impact_biases
            WHERE {where_stmt}
            ORDER BY created_at DESC
            LIMIT 100
        """)

        impacts: List[EventImpact] = []
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(query, params).mappings().all()
                for row in rows:
                    r = dict(row)
                    meta_raw = r.get("metadata")
                    if isinstance(meta_raw, str):
                        try:
                            r["metadata"] = json.loads(meta_raw)
                        except Exception:
                            r["metadata"] = {}
                    elif not isinstance(meta_raw, dict):
                        r["metadata"] = {}

                    # Normalize boolean
                    r["is_dismissed"] = bool(r.get("is_dismissed", False))
                    impacts.append(EventImpact.from_dict(r))
        except Exception as e:
            logger.warning(f"EventImpactRepository: get_active_impacts error for {user_id}: {e}")

        return impacts

    def dismiss_impact(self, user_id: str, impact_id: str) -> bool:
        """Soft-dismiss an impact so it no longer applies bias."""
        is_sqlite = "sqlite" in str(self.engine.url)
        dismissed_val = 1 if is_sqlite else True

        query = text("""
            UPDATE event_impact_biases
            SET is_dismissed = :dismissed
            WHERE user_id = :user_id AND id = :id
        """)
        params = {"user_id": user_id, "id": impact_id, "dismissed": dismissed_val}

        try:
            with self.engine.begin() as conn:
                res = conn.execute(query, params)
                return res.rowcount > 0
        except Exception as e:
            logger.warning(f"EventImpactRepository: dismiss_impact error for {impact_id}: {e}")
            return False

    def get_impact_by_id(self, user_id: str, impact_id: str) -> Optional[EventImpact]:
        """Fetch single impact by id and user_id."""
        query = text("""
            SELECT id, user_id, scope, ticker, category, headline, summary,
                   sentiment, initial_impact, half_life_hours, created_at, metadata, is_dismissed
            FROM event_impact_biases
            WHERE user_id = :user_id AND id = :id
        """)
        try:
            with self.engine.connect() as conn:
                row = conn.execute(query, {"user_id": user_id, "id": impact_id}).mappings().first()
                if not row:
                    return None
                r = dict(row)
                meta_raw = r.get("metadata")
                if isinstance(meta_raw, str):
                    try:
                        r["metadata"] = json.loads(meta_raw)
                    except Exception:
                        r["metadata"] = {}
                elif not isinstance(meta_raw, dict):
                    r["metadata"] = {}
                r["is_dismissed"] = bool(r.get("is_dismissed", False))
                return EventImpact.from_dict(r)
        except Exception as e:
            logger.warning(f"EventImpactRepository: get_impact_by_id error for {impact_id}: {e}")
            return None
