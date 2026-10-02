"""
Shadow Ledger Repository
========================
Provides persistence for the Shadow Ledger & Paper Trading Validation Track (P2).
Tracks virtual positions, simulated slippage, daily mark-to-market performance,
drawdowns, and graduation milestones prior to live capital deployment.
"""
from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.data.database import BaseRepository, get_db_engine
from src.utils.logger import setup_logger

logger = setup_logger("ShadowLedgerRepository")

SHADOW_POSITION_UPDATABLE_FIELDS = frozenset({
    "current_price",
    "peak_price",
    "peak_pnl_pct",
    "unrealized_pnl",
    "unrealized_pnl_pct",
    "max_drawdown_pct",
    "institutional_support_price",
    "support_breached",
    "evaluation_days",
    "status",
    "graduation_date",
    "graduation_metrics",
    "notes",
    "updated_at",
})


class IShadowLedgerRepository(ABC):
    """Domain Interface for Shadow Ledger persistence."""

    @abstractmethod
    def create_position(
        self,
        user_id: str,
        ticker: str,
        strategy_name: str,
        entry_price: float,
        simulated_quantity: float,
        allocated_capital: float,
        fees_and_slippage: float = 0.0,
        institutional_support_price: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record a new open shadow position."""
        pass

    @abstractmethod
    def get_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific shadow position by ID."""
        pass

    @abstractmethod
    def get_open_position(self, user_id: str, ticker: str) -> Optional[Dict[str, Any]]:
        """Get currently OPEN shadow position for user and ticker, if one exists."""
        pass

    @abstractmethod
    def list_positions(
        self,
        user_id: str,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List shadow positions filtered by user, status, and/or ticker."""
        pass

    @abstractmethod
    def update_position(self, position_id: str, **kwargs) -> bool:
        """Update fields of an existing shadow position."""
        pass

    @abstractmethod
    def close_position(
        self,
        position_id: str,
        status: str,
        final_price: float,
        graduation_metrics: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Close/graduate/fail a shadow position with terminal status and metrics."""
        pass


class AlchemyShadowLedgerRepository(BaseRepository, IShadowLedgerRepository):
    """PostgreSQL / SQLite implementation of IShadowLedgerRepository."""

    def __init__(self, db_path: Optional[str] = None, engine: Any = None):
        eng = engine or get_db_engine(db_path)
        BaseRepository.__init__(self, eng)
        self._init_tables()

    def _init_tables(self) -> None:
        """Initialize shadow ledger schema idempotently."""
        is_sqlite = "sqlite" in str(self.engine.url)

        if is_sqlite:
            queries = [
                text("""
                CREATE TABLE IF NOT EXISTS shadow_positions (
                    id                          TEXT PRIMARY KEY,
                    user_id                     TEXT NOT NULL,
                    ticker                      TEXT NOT NULL,
                    strategy_name               TEXT NOT NULL DEFAULT 'unspecified',
                    status                      TEXT NOT NULL DEFAULT 'OPEN',
                    entry_date                  TEXT NOT NULL,
                    entry_price                 REAL NOT NULL,
                    simulated_quantity          REAL NOT NULL,
                    allocated_capital           REAL NOT NULL,
                    current_price               REAL NOT NULL,
                    peak_price                  REAL NOT NULL,
                    peak_pnl_pct                REAL NOT NULL DEFAULT 0.0,
                    unrealized_pnl              REAL NOT NULL DEFAULT 0.0,
                    unrealized_pnl_pct          REAL NOT NULL DEFAULT 0.0,
                    max_drawdown_pct            REAL NOT NULL DEFAULT 0.0,
                    fees_and_slippage           REAL NOT NULL DEFAULT 0.0,
                    institutional_support_price REAL,
                    support_breached            INTEGER NOT NULL DEFAULT 0,
                    evaluation_days             INTEGER NOT NULL DEFAULT 0,
                    graduation_date             TEXT,
                    graduation_metrics          TEXT DEFAULT '{}',
                    notes                       TEXT DEFAULT '',
                    created_at                  TEXT NOT NULL,
                    updated_at                  TEXT NOT NULL
                );
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_shadow_positions_user_status
                    ON shadow_positions(user_id, status);
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_shadow_positions_user_ticker
                    ON shadow_positions(user_id, ticker);
                """),
            ]
        else:
            queries = [
                text("""
                CREATE TABLE IF NOT EXISTS shadow_positions (
                    id                          VARCHAR(64) PRIMARY KEY,
                    user_id                     VARCHAR(64) NOT NULL,
                    ticker                      VARCHAR(20) NOT NULL,
                    strategy_name               VARCHAR(64) NOT NULL DEFAULT 'unspecified',
                    status                      VARCHAR(20) NOT NULL DEFAULT 'OPEN',
                    entry_date                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    entry_price                 NUMERIC(14, 4) NOT NULL,
                    simulated_quantity          NUMERIC(14, 4) NOT NULL,
                    allocated_capital           NUMERIC(14, 2) NOT NULL,
                    current_price               NUMERIC(14, 4) NOT NULL,
                    peak_price                  NUMERIC(14, 4) NOT NULL,
                    peak_pnl_pct                NUMERIC(8, 4) NOT NULL DEFAULT 0.0,
                    unrealized_pnl              NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
                    unrealized_pnl_pct          NUMERIC(8, 4) NOT NULL DEFAULT 0.0,
                    max_drawdown_pct            NUMERIC(8, 4) NOT NULL DEFAULT 0.0,
                    fees_and_slippage           NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
                    institutional_support_price NUMERIC(14, 4),
                    support_breached            BOOLEAN NOT NULL DEFAULT FALSE,
                    evaluation_days             INTEGER NOT NULL DEFAULT 0,
                    graduation_date             TIMESTAMPTZ,
                    graduation_metrics          JSONB DEFAULT '{}',
                    notes                       TEXT DEFAULT '',
                    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_shadow_positions_user_status
                    ON shadow_positions(user_id, status);
                """),
                text("""
                CREATE INDEX IF NOT EXISTS idx_shadow_positions_user_ticker
                    ON shadow_positions(user_id, ticker);
                """),
            ]

        for q in queries:
            try:
                with self.engine.begin() as conn:
                    conn.execute(q)
            except Exception as e:
                logger.debug("Shadow ledger table init statement skipped/failed: %s", e)

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        """Convert SQLAlchemy row mapping to normalized dictionary."""
        d = dict(row._mapping)
        # Parse graduation_metrics if JSON string
        if isinstance(d.get("graduation_metrics"), str):
            try:
                d["graduation_metrics"] = json.loads(d["graduation_metrics"])
            except Exception:
                pass
        # Normalize support_breached to bool
        if "support_breached" in d:
            d["support_breached"] = bool(d["support_breached"])
        # Normalize numeric floats
        for f in [
            "entry_price", "simulated_quantity", "allocated_capital", "current_price",
            "peak_price", "peak_pnl_pct", "unrealized_pnl", "unrealized_pnl_pct",
            "max_drawdown_pct", "fees_and_slippage", "institutional_support_price"
        ]:
            if d.get(f) is not None:
                d[f] = float(d[f])
        return d

    def create_position(
        self,
        user_id: str,
        ticker: str,
        strategy_name: str,
        entry_price: float,
        simulated_quantity: float,
        allocated_capital: float,
        fees_and_slippage: float = 0.0,
        institutional_support_price: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        pos_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc)
        is_sqlite = "sqlite" in str(self.engine.url)
        now_str = now_utc.isoformat()

        insert_sql = text("""
            INSERT INTO shadow_positions (
                id, user_id, ticker, strategy_name, status,
                entry_date, entry_price, simulated_quantity, allocated_capital,
                current_price, peak_price, peak_pnl_pct, unrealized_pnl,
                unrealized_pnl_pct, max_drawdown_pct, fees_and_slippage,
                institutional_support_price, support_breached, evaluation_days,
                graduation_metrics, notes, created_at, updated_at
            ) VALUES (
                :id, :user_id, :ticker, :strategy_name, 'OPEN',
                :entry_date, :entry_price, :simulated_quantity, :allocated_capital,
                :current_price, :peak_price, 0.0, 0.0,
                0.0, 0.0, :fees_and_slippage,
                :institutional_support_price, :support_breached, 0,
                :graduation_metrics, :notes, :created_at, :updated_at
            )
        """)

        metrics_json = "{}"
        support_breached_val = 0 if is_sqlite else False

        params = {
            "id": pos_id,
            "user_id": str(user_id),
            "ticker": ticker.upper().strip(),
            "strategy_name": strategy_name,
            "entry_date": now_str if is_sqlite else now_utc,
            "entry_price": float(entry_price),
            "simulated_quantity": float(simulated_quantity),
            "allocated_capital": float(allocated_capital),
            "current_price": float(entry_price),
            "peak_price": float(entry_price),
            "fees_and_slippage": float(fees_and_slippage),
            "institutional_support_price": float(institutional_support_price) if institutional_support_price else None,
            "support_breached": support_breached_val,
            "graduation_metrics": metrics_json,
            "notes": notes or "",
            "created_at": now_str if is_sqlite else now_utc,
            "updated_at": now_str if is_sqlite else now_utc,
        }

        with self.engine.begin() as conn:
            conn.execute(insert_sql, params)

        created = self.get_position(pos_id)
        if not created:
            raise RuntimeError(f"Failed to retrieve newly created shadow position {pos_id}")
        return created

    def get_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM shadow_positions WHERE id = :id"),
                {"id": position_id}
            ).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def get_open_position(self, user_id: str, ticker: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT * FROM shadow_positions
                    WHERE user_id = :uid AND ticker = :ticker AND status = 'OPEN'
                    ORDER BY entry_date DESC
                    LIMIT 1
                """),
                {"uid": str(user_id), "ticker": ticker.upper().strip()}
            ).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def list_positions(
        self,
        user_id: str,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses = ["user_id = :uid"]
        params: Dict[str, Any] = {"uid": str(user_id)}

        if status:
            clauses.append("status = :status")
            params["status"] = status.upper().strip()

        if ticker:
            clauses.append("ticker = :ticker")
            params["ticker"] = ticker.upper().strip()

        where_clause = " AND ".join(clauses)
        sql = f"SELECT * FROM shadow_positions WHERE {where_clause} ORDER BY entry_date DESC"

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def update_position(self, position_id: str, **kwargs) -> bool:
        """Update allowed fields of a shadow position."""
        if not kwargs:
            return False

        unknown = set(kwargs) - SHADOW_POSITION_UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"Fields not allowed in shadow_positions update: {sorted(unknown)}")

        is_sqlite = "sqlite" in str(self.engine.url)
        params: Dict[str, Any] = {"id": position_id}
        set_clauses: List[str] = []

        now_utc = datetime.now(timezone.utc)
        kwargs["updated_at"] = now_utc.isoformat() if is_sqlite else now_utc

        for key, val in kwargs.items():
            if key == "graduation_metrics" and isinstance(val, (dict, list)):
                val = json.dumps(val)
            elif key == "support_breached" and is_sqlite:
                val = 1 if val else 0
            params[key] = val
            set_clauses.append(f"{key} = :{key}")

        sql = f"UPDATE shadow_positions SET {', '.join(set_clauses)} WHERE id = :id"

        with self.engine.begin() as conn:
            res = conn.execute(text(sql), params)
            return res.rowcount > 0

    def close_position(
        self,
        position_id: str,
        status: str,
        final_price: float,
        graduation_metrics: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> bool:
        pos = self.get_position(position_id)
        if not pos:
            return False

        now_utc = datetime.now(timezone.utc)
        is_sqlite = "sqlite" in str(self.engine.url)
        grad_date = now_utc.isoformat() if is_sqlite else now_utc

        entry_price = float(pos["entry_price"])
        quantity = float(pos["simulated_quantity"])
        allocated_capital = float(pos["allocated_capital"])
        unrealized_pnl = round(quantity * final_price - allocated_capital, 2)
        unrealized_pnl_pct = round(((final_price / entry_price) - 1.0) * 100, 4) if entry_price > 0 else 0.0

        update_payload: Dict[str, Any] = {
            "status": status.upper().strip(),
            "current_price": float(final_price),
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "graduation_date": grad_date,
            "graduation_metrics": graduation_metrics or {},
        }
        if notes:
            update_payload["notes"] = notes

        return self.update_position(position_id, **update_payload)
