"""
Ticker Universe Repository
User-specific persistent ticker pool, research reports, target allocations, and audit logs.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.utils.logger import setup_logger

logger = setup_logger("TickerUniverseRepository")


class TickerUniverseRepository(BaseRepository):
    """Manages ticker_universe, ticker_research, target_allocations, ticker_universe_logs tables."""

    def __init__(self, db_path: str = None, engine=None):
        BaseRepository.__init__(self, engine or get_db_engine(db_path))
        self._init_tables()

    def _init_tables(self) -> None:
        """Create all 4 tables if not exist."""
        queries = [
            text("""
            CREATE TABLE IF NOT EXISTS ticker_universe (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id         UUID NOT NULL,
                ticker          VARCHAR(10) NOT NULL,
                company_name    TEXT,
                sector          VARCHAR(50),
                industry        VARCHAR(50),
                status          VARCHAR(20) DEFAULT 'active',
                added_at        TIMESTAMPTZ DEFAULT NOW(),
                removed_at      TIMESTAMPTZ,
                removal_reason  TEXT,
                last_reviewed_at TIMESTAMPTZ,
                UNIQUE(user_id, ticker)
            );
            """),
            text("""
            CREATE INDEX IF NOT EXISTS idx_ticker_universe_active
                ON ticker_universe(user_id, status)
                WHERE status = 'active';
            """),
            text("""
            CREATE TABLE IF NOT EXISTS ticker_research (
                id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id           UUID NOT NULL,
                ticker            VARCHAR(10) NOT NULL,
                agent_name        VARCHAR(50) NOT NULL,
                research_type     VARCHAR(30) NOT NULL,
                confidence_score  NUMERIC(5,4),
                target_weight     NUMERIC(5,4),
                expected_return   NUMERIC(8,6),
                risk_score        NUMERIC(5,4),
                thesis            TEXT,
                risks             TEXT[],
                data_sources      JSONB,
                raw_analysis      JSONB,
                created_at        TIMESTAMPTZ DEFAULT NOW()
            );
            """),
            text("""
            CREATE INDEX IF NOT EXISTS idx_ticker_research_latest
                ON ticker_research(user_id, ticker, created_at DESC);
            """),
            text("""
            CREATE TABLE IF NOT EXISTS target_allocations (
                id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id             UUID NOT NULL,
                ticker              VARCHAR(10) NOT NULL,
                target_weight       NUMERIC(5,4),
                confidence_score    NUMERIC(5,4),
                expected_return     NUMERIC(8,6),
                risk_adjusted_return NUMERIC(8,6),
                min_weight          NUMERIC(5,4),
                max_weight          NUMERIC(5,4),
                last_optimized_at   TIMESTAMPTZ,
                UNIQUE(user_id, ticker)
            );
            """),
            text("""
            CREATE TABLE IF NOT EXISTS ticker_universe_logs (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id     UUID NOT NULL,
                ticker      VARCHAR(10),
                action      VARCHAR(20) NOT NULL,
                agent_name  VARCHAR(50),
                reasoning   TEXT,
                old_status  VARCHAR(20),
                new_status  VARCHAR(20),
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
            """),
            text("""
            CREATE INDEX IF NOT EXISTS idx_ticker_logs_user
                ON ticker_universe_logs(user_id, created_at DESC);
            """),
        ]
        for q in queries:
            try:
                with self.engine.begin() as conn:
                    conn.execute(q)
            except Exception as e:
                logger.warning(f"Table init warning (likely already exists): {e}")

    # ── Ticker Universe CRUD ──

    def get_all(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get tickers from universe, optionally filtered by status."""
        if status:
            query = text("""
                SELECT * FROM ticker_universe
                WHERE user_id = :uid AND status = :status
                ORDER BY added_at DESC
            """)
            params = {"uid": user_id, "status": status}
        else:
            query = text("""
                SELECT * FROM ticker_universe
                WHERE user_id = :uid
                ORDER BY status, added_at DESC
            """)
            params = {"uid": user_id}
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(query, params).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_all failed: {e}")
            return []

    def get_by_ticker(self, user_id: str, ticker: str) -> Optional[Dict[str, Any]]:
        """Get a single ticker from universe."""
        query = text("SELECT * FROM ticker_universe WHERE user_id = :uid AND ticker = :ticker")
        try:
            with self.engine.connect() as conn:
                row = conn.execute(query, {"uid": user_id, "ticker": ticker.upper()}).mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_by_ticker({ticker}) failed: {e}")
            return None

    def upsert(self, user_id: str, ticker: str, **kwargs) -> bool:
        """Insert or update a ticker in the universe."""
        import re
        # Validate kwargs keys to prevent SQL injection
        for k in kwargs:
            if not re.match(r"^[a-zA-Z0-9_]+$", k):
                raise ValueError(f"Invalid field name: {k}")

        existing = self.get_by_ticker(user_id, ticker)
        now = datetime.now(timezone.utc)
        if existing:
            fields = ", ".join(f"{k} = :{k}" for k in kwargs)
            params = {k: v for k, v in kwargs.items()}
            params["uid"] = user_id
            params["ticker"] = ticker.upper()
            query = text(f"""
                UPDATE ticker_universe SET {fields}, last_reviewed_at = :now
                WHERE user_id = :uid AND ticker = :ticker
            """)  # nosec B608
            params["now"] = now
        else:
            cols = ["user_id", "ticker", "added_at"] + list(kwargs.keys())
            placeholders = [f":{c}" if c != "added_at" else ":now" for c in cols]
            params = {"user_id": user_id, "ticker": ticker.upper(), "now": now}
            params.update({k: v for k, v in kwargs.items()})
            query = text(f"""
                INSERT INTO ticker_universe ({', '.join(cols)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT (user_id, ticker) DO UPDATE SET
                    {', '.join(f"{k} = EXCLUDED.{k}" for k in kwargs)}
            """)  # nosec B608
        try:
            with self.engine.begin() as conn:
                conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"upsert({ticker}) failed: {e}")
            return False

    def remove(self, user_id: str, ticker: str, reason: str = "") -> bool:
        """Soft-delete a ticker (set status='removed')."""
        query = text("""
            UPDATE ticker_universe
            SET status = 'removed', removed_at = NOW(), removal_reason = :reason
            WHERE user_id = :uid AND ticker = :ticker
        """)
        try:
            with self.engine.begin() as conn:
                conn.execute(query, {"uid": user_id, "ticker": ticker.upper(), "reason": reason})
            return True
        except Exception as e:
            logger.error(f"remove({ticker}) failed: {e}")
            return False

    # ── Ticker Research CRUD ──

    def get_research(self, user_id: str, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get research records for a ticker."""
        query = text("""
            SELECT * FROM ticker_research
            WHERE user_id = :uid AND ticker = :ticker
            ORDER BY created_at DESC
            LIMIT :lim
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(query, {"uid": user_id, "ticker": ticker.upper(), "lim": limit}).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_research({ticker}) failed: {e}")
            return []

    def add_research(self, user_id: str, ticker: str, agent_name: str,
                     research_type: str, confidence_score: float,
                     target_weight: float = None, expected_return: float = None,
                     risk_score: float = None, thesis: str = "",
                     risks: list = None, data_sources: dict = None,
                     raw_analysis: dict = None) -> bool:
        """Add a research record."""
        query = text("""
            INSERT INTO ticker_research
                (user_id, ticker, agent_name, research_type,
                 confidence_score, target_weight, expected_return, risk_score,
                 thesis, risks, data_sources, raw_analysis)
            VALUES
                (:uid, :ticker, :agent, :rtype,
                 :conf, :tw, :er, :risk,
                 :thesis, :risks, :ds, :raw)
        """)
        params = {
            "uid": user_id, "ticker": ticker.upper(), "agent": agent_name,
            "rtype": research_type, "conf": confidence_score,
            "tw": target_weight, "er": expected_return, "risk": risk_score,
            "thesis": thesis,
            "risks": risks or [],
            "ds": self._json(data_sources or {}),
            "raw": self._json(raw_analysis or {}),
        }
        try:
            with self.engine.begin() as conn:
                conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"add_research({ticker}) failed: {e}")
            return False

    # ── Target Allocations CRUD ──

    def get_target_allocations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all target allocations for a user."""
        query = text("""
            SELECT * FROM target_allocations
            WHERE user_id = :uid
            ORDER BY target_weight DESC
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(query, {"uid": user_id}).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_target_allocations failed: {e}")
            return []

    def upsert_target(self, user_id: str, ticker: str, **kwargs) -> bool:
        """Insert or update a target allocation."""
        import re
        # Validate kwargs keys to prevent SQL injection
        for k in kwargs:
            if not re.match(r"^[a-zA-Z0-9_]+$", k):
                raise ValueError(f"Invalid field name: {k}")

        params = {k: v for k, v in kwargs.items()}
        params["uid"] = user_id
        params["ticker"] = ticker.upper()
        params["now"] = datetime.now(timezone.utc)

        # Build dynamic SET clause
        set_clause = ", ".join(f"{k} = :{k}" for k in kwargs)
        query = text(f"""
            INSERT INTO target_allocations (user_id, ticker, {', '.join(kwargs.keys())}, last_optimized_at)
            VALUES (:uid, :ticker, {', '.join(':' + k for k in kwargs.keys())}, :now)
            ON CONFLICT (user_id, ticker) DO UPDATE SET
                {set_clause}, last_optimized_at = EXCLUDED.last_optimized_at
        """)  # nosec B608
        try:
            with self.engine.begin() as conn:
                conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"upsert_target({ticker}) failed: {e}")
            return False

    def clear_targets(self, user_id: str) -> bool:
        """Clear all target allocations for a user (before re-optimization)."""
        query = text("DELETE FROM target_allocations WHERE user_id = :uid")
        try:
            with self.engine.begin() as conn:
                conn.execute(query, {"uid": user_id})
            return True
        except Exception as e:
            logger.error(f"clear_targets failed: {e}")
            return False

    # ── Audit Logs ──

    def add_log(self, user_id: str, ticker: str, action: str,
                agent_name: str = "", reasoning: str = "",
                old_status: str = "", new_status: str = "") -> bool:
        """Add an audit log entry."""
        query = text("""
            INSERT INTO ticker_universe_logs
                (user_id, ticker, action, agent_name, reasoning, old_status, new_status)
            VALUES (:uid, :ticker, :action, :agent, :reason, :old, :new)
        """)
        try:
            with self.engine.begin() as conn:
                conn.execute(query, {
                    "uid": user_id, "ticker": ticker.upper(),
                    "action": action, "agent": agent_name,
                    "reason": reasoning, "old": old_status, "new": new_status,
                })
            return True
        except Exception as e:
            logger.error(f"add_log failed: {e}")
            return False

    def get_logs(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get audit logs."""
        query = text("""
            SELECT * FROM ticker_universe_logs
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT :lim
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(query, {"uid": user_id, "lim": limit}).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_logs failed: {e}")
            return []

    # ── Migration Helper ──

    def migrate_holdings_to_universe(self, user_id: str, holdings: List[Dict[str, Any]]) -> int:
        """Batch-migrate existing holdings into ticker_universe as active."""
        count = 0
        for h in holdings:
            ticker = h.get("ticker", h.get("symbol", "")).upper()
            if not ticker:
                continue
            ok = self.upsert(
                user_id, ticker,
                company_name=h.get("company_name", ""),
                sector=h.get("sector", ""),
                status="active",
            )
            if ok:
                self.add_log(user_id, ticker, "added", "migration",
                             "Migrated from existing holdings", "", "active")
                count += 1
        logger.info(f"Migrated {count} holdings to ticker_universe for user {user_id}")
        return count

    @staticmethod
    def _json(obj: Any) -> Any:
        """Convert Python objects to JSON-compatible for PostgreSQL JSONB."""
        import json
        if obj is None:
            return None
        if isinstance(obj, (dict, list)):
            return json.dumps(obj)
        return obj