"""
Position Lot Repository
=======================
Provides O(1) average-cost lookup by maintaining an explicit lot-level
ledger (``position_lots`` table) instead of replaying full transaction history.

Each open position is recorded as one or more "lots". When a position is
partially or fully closed the corresponding lots are marked ``is_open = FALSE``
and a ``close_price`` is recorded for realised-PnL tracking.

Architecture note:
  IPositionLotRepository  — Pure domain interface (no DB dependency)
  AlchemyPositionLotRepository — PostgreSQL implementation via SQLAlchemy
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import text

from src.data.database import BaseRepository, get_db_engine
from src.utils.logger import setup_logger

logger = setup_logger("PositionLotRepository")


# ---------------------------------------------------------------------------
# Domain Interface
# ---------------------------------------------------------------------------

class IPositionLotRepository(ABC):
    """Interface for the position-lot ledger."""

    @abstractmethod
    def get_open_lots(
        self,
        user_id: str,
        ticker: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return open lots for a user, optionally filtered by ticker.

        Returns a list of dicts with keys:
          id, user_id, ticker, open_date, quantity, open_price, leverage
        """

    @abstractmethod
    def open_lot(
        self,
        user_id: str,
        ticker: str,
        open_date: str,
        quantity: float,
        open_price: float,
        leverage: float = 1.0,
        source_tx_id: Optional[str] = None,
    ) -> str:
        """Record a new open lot.  Returns the new lot ``id``."""

    @abstractmethod
    def close_lot(
        self,
        lot_id: str,
        close_date: str,
        close_price: float,
        quantity_to_close: Optional[float] = None,
    ) -> None:
        """Mark a lot (or part of it) as closed.

        If ``quantity_to_close`` is less than the lot's remaining quantity a
        partial-close split is performed automatically.
        """

    @abstractmethod
    def has_lots_for_user(self, user_id: str) -> bool:
        """Return True if the position_lots table has been seeded for this user."""

    @abstractmethod
    def backfill_from_transactions(self, user_id: str) -> int:
        """Replay transaction history to populate position_lots.

        Returns the number of lots created.

        This is idempotent: existing lots are cleared before re-seeding so
        repeated calls are safe.
        """

    @abstractmethod
    def get_avg_cost_map(self, user_id: str) -> Dict[str, float]:
        """Return {ticker: weighted_avg_open_price} for all open lots.

        This is the primary O(1) access pattern that replaces the full
        history-replay in PnLCalculator / get_holdings().
        """


# ---------------------------------------------------------------------------
# SQLAlchemy Implementation
# ---------------------------------------------------------------------------

class AlchemyPositionLotRepository(BaseRepository, IPositionLotRepository):
    """PostgreSQL implementation of IPositionLotRepository."""

    def __init__(self, engine: Any = None):
        BaseRepository.__init__(self, engine or get_db_engine())

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_open_lots(
        self,
        user_id: str,
        ticker: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            if ticker:
                query = text("""
                    SELECT id, user_id, ticker, open_date, quantity,
                           open_price, leverage, source_tx_id
                    FROM position_lots
                    WHERE user_id = :uid AND ticker = :ticker AND is_open = TRUE
                    ORDER BY open_date ASC
                """)
                rows = conn.execute(query, {"uid": user_id, "ticker": ticker}).fetchall()
            else:
                query = text("""
                    SELECT id, user_id, ticker, open_date, quantity,
                           open_price, leverage, source_tx_id
                    FROM position_lots
                    WHERE user_id = :uid AND is_open = TRUE
                    ORDER BY ticker, open_date ASC
                """)
                rows = conn.execute(query, {"uid": user_id}).fetchall()

        return [dict(r._mapping) for r in rows]

    def has_lots_for_user(self, user_id: str) -> bool:
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM position_lots WHERE user_id = :uid"),
                {"uid": user_id},
            ).scalar()
        return (result or 0) > 0

    def get_avg_cost_map(self, user_id: str) -> Dict[str, float]:
        """O(1) weighted-average cost per ticker from open lots."""
        with self.engine.connect() as conn:
            query = text("""
                SELECT
                    ticker,
                    SUM(quantity * open_price) / NULLIF(SUM(quantity), 0) AS avg_cost
                FROM position_lots
                WHERE user_id = :uid AND is_open = TRUE
                GROUP BY ticker
            """)
            rows = conn.execute(query, {"uid": user_id}).fetchall()
        return {r[0]: float(r[1]) for r in rows if r[1] is not None}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def open_lot(
        self,
        user_id: str,
        ticker: str,
        open_date: str,
        quantity: float,
        open_price: float,
        leverage: float = 1.0,
        source_tx_id: Optional[str] = None,
    ) -> str:
        lot_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO position_lots
                      (id, user_id, ticker, open_date, quantity, open_price,
                       leverage, is_open, source_tx_id)
                    VALUES
                      (:id, :uid, :ticker, :open_date, :qty, :price,
                       :leverage, TRUE, :src_tx)
                """),
                {
                    "id": lot_id,
                    "uid": user_id,
                    "ticker": ticker,
                    "open_date": open_date,
                    "qty": quantity,
                    "price": open_price,
                    "leverage": leverage,
                    "src_tx": source_tx_id,
                },
            )
        return lot_id

    def close_lot(
        self,
        lot_id: str,
        close_date: str,
        close_price: float,
        quantity_to_close: Optional[float] = None,
    ) -> None:
        with self.engine.begin() as conn:
            lot_row = conn.execute(
                text("SELECT quantity, open_price, leverage, user_id, ticker, open_date FROM position_lots WHERE id = :id"),
                {"id": lot_id},
            ).fetchone()

            if lot_row is None:
                logger.warning(f"close_lot: lot {lot_id} not found, skipping.")
                return

            lot_qty = float(lot_row[0])

            # --- Full close ---
            if quantity_to_close is None or quantity_to_close >= lot_qty:
                conn.execute(
                    text("""
                        UPDATE position_lots
                        SET is_open = FALSE, close_date = :close_date, close_price = :close_price
                        WHERE id = :id
                    """),
                    {"id": lot_id, "close_date": close_date, "close_price": close_price},
                )
            else:
                # --- Partial close: reduce existing lot + create closed stub ---
                remaining = lot_qty - quantity_to_close
                conn.execute(
                    text("UPDATE position_lots SET quantity = :qty WHERE id = :id"),
                    {"qty": remaining, "id": lot_id},
                )
                # Insert the closed portion as a separate lot record
                conn.execute(
                    text("""
                        INSERT INTO position_lots
                          (id, user_id, ticker, open_date, close_date, quantity,
                           open_price, close_price, leverage, is_open, source_tx_id)
                        SELECT
                          :new_id, user_id, ticker, open_date, :close_date, :closed_qty,
                          open_price, :close_price, leverage, FALSE, source_tx_id
                        FROM position_lots WHERE id = :original_id
                    """),
                    {
                        "new_id": str(uuid.uuid4()),
                        "close_date": close_date,
                        "closed_qty": quantity_to_close,
                        "close_price": close_price,
                        "original_id": lot_id,
                    },
                )

    # ------------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------------

    def backfill_from_transactions(self, user_id: str) -> int:
        """FIFO-based replay of transactions to seed position_lots.

        Clears existing lots for this user first (idempotent).
        Skips STABILIZE / ETORO_SYNC / CASH synthetic tickers.
        Returns the number of open lots created.
        """
        from src.repositories.transaction_repository import AlchemyTransactionRepository

        # 1. Clear existing lots for this user to ensure idempotency
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM position_lots WHERE user_id = :uid"),
                {"uid": user_id},
            )

        # 2. Fetch all transactions in chronological order
        tx_repo = AlchemyTransactionRepository(self.engine)
        transactions = list(reversed(list(tx_repo.get_all_by_user(user_id))))

        # In-memory FIFO lot tracker: {ticker: [{'qty':..., 'price':..., 'lev':..., 'date':..., 'tx_id':...}]}
        open_lots: Dict[str, List[Dict]] = {}
        lots_created = 0

        SYNTHETIC_PREFIXES = ("STABILIZE", "__ANCHOR_", "NLV_")
        SYNTHETIC_TICKERS = {"CASH", "STABILIZE_CASH", "STABILIZE_CAP", "ETORO_SYNC"}

        for row in transactions:
            ticker = row.ticker
            action = row.action
            qty = float(row.quantity)
            price = float(row.price)
            leverage = float(getattr(row, "leverage", 1.0) or 1.0)
            trade_date = str(row.trade_date)
            tx_id = str(row.id)

            # Skip synthetic / non-equity tickers
            if ticker in SYNTHETIC_TICKERS:
                continue
            if any(ticker.startswith(pfx) for pfx in SYNTHETIC_PREFIXES):
                continue

            if action == "BUY":
                if ticker not in open_lots:
                    open_lots[ticker] = []
                open_lots[ticker].append({
                    "qty": qty,
                    "price": price,
                    "leverage": leverage,
                    "date": trade_date,
                    "tx_id": tx_id,
                })
            elif action == "SELL":
                # FIFO: consume oldest lots first
                remaining_sell = qty
                if ticker not in open_lots:
                    continue
                while remaining_sell > 0.0001 and open_lots[ticker]:
                    lot = open_lots[ticker][0]
                    if lot["qty"] <= remaining_sell + 0.0001:
                        remaining_sell -= lot["qty"]
                        open_lots[ticker].pop(0)
                    else:
                        lot["qty"] -= remaining_sell
                        remaining_sell = 0.0

        # 3. Persist remaining (open) lots to DB
        for ticker, lots in open_lots.items():
            for lot in lots:
                if lot["qty"] > 0.0001:
                    self.open_lot(
                        user_id=user_id,
                        ticker=ticker,
                        open_date=lot["date"],
                        quantity=lot["qty"],
                        open_price=lot["price"],
                        leverage=lot["leverage"],
                        source_tx_id=lot["tx_id"],
                    )
                    lots_created += 1

        logger.info(f"backfill_from_transactions: created {lots_created} open lots for user={user_id}")
        return lots_created
