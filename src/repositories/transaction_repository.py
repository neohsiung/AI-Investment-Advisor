from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
import pandas as pd
import uuid

# Valid values for the entry_category column.
ENTRY_CATEGORY_TRADE = "trade"
ENTRY_CATEGORY_CAPITAL_FLOW = "capital_flow"
ENTRY_CATEGORY_SYNC_ADJUSTMENT = "sync_adjustment"

# Immutable sets used for write-time validation.
VALID_ENTRY_CATEGORIES: frozenset = frozenset({
    ENTRY_CATEGORY_TRADE,
    ENTRY_CATEGORY_CAPITAL_FLOW,
    ENTRY_CATEGORY_SYNC_ADJUSTMENT,
})

# Actions that represent real asset transactions (must have a non-empty ticker).
TRADE_ACTIONS: frozenset = frozenset({"BUY", "SELL"})

# Actions that represent capital movements (must have amount > 0).
CAPITAL_ACTIONS: frozenset = frozenset({"DEPOSIT", "WITHDRAWAL"})

class ITransactionRepository(ABC):
    """
    Interface for Transaction Repository.
    交易儲存庫介面。
    """
    @abstractmethod
    def get_all_by_user(self, user_id: str, account_id: str = None) -> List[Any]:
        pass

    @abstractmethod
    def get_active_tickers(self, user_id: str, account_id: str = None) -> List[str]:
        pass

    @abstractmethod
    def add(
        self,
        user_id: str,
        ticker: str,
        date: str,
        action: str,
        quantity: float,
        price: float,
        fees: float,
        leverage: float = 1.0,
        source_file: str = None,
        entry_category: str = ENTRY_CATEGORY_TRADE,
        amount: Optional[float] = None,
    ) -> None:
        pass

    @abstractmethod
    def delete(self, user_id: str, transaction_id: str) -> None:
        pass

    @abstractmethod
    def get_holdings(self, user_id: str, account_id: str = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_holdings_summary(self, user_id: str, account_id: str = None) -> List[tuple]:
        pass

    @abstractmethod
    def get_latest_leverage(self, user_id: str) -> float:
        pass

    @abstractmethod
    def get_cash_flow_sum(self, user_id: str, account_id: str = None) -> float:
        pass

    @abstractmethod
    def calculate_net_invested_capital(self, user_id: str, account_id: str = None) -> float:
        pass

    @abstractmethod
    def get_cash_balance(self, user_id: str, account_id: str = None) -> float:
        pass

    @abstractmethod
    def get_leverage_summary(self, user_id: str, account_id: str = None) -> List[tuple]:
        pass

    @abstractmethod
    def get_all_accounts(self, user_id: str) -> List[str]:
        pass

class AlchemyTransactionRepository(BaseRepository, ITransactionRepository):
    """
    Implementation of ITransactionRepository using SQLAlchemy.
    """
    def __init__(self, engine: Any = None):
        BaseRepository.__init__(self, engine or get_db_engine())

    def get_all_by_user(self, user_id: str, account_id: str = None) -> List[Any]:
        with self.engine.connect() as conn:
            sql = "SELECT * FROM transactions WHERE user_id = :user_id"
            params = {"user_id": user_id}
            query = text("""
                SELECT * FROM transactions 
                WHERE user_id = :user_id 
                AND (:account_id IS NULL OR source_file = :account_id)
                ORDER BY trade_date DESC, action DESC
            """)
            params = {"user_id": user_id, "account_id": account_id}
            return conn.execute(query, params).fetchall()

    def get_all_by_user_df(self, user_id: str, account_id: str = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            query = text("""
                SELECT * FROM transactions 
                WHERE user_id = :user_id 
                AND (:account_id IS NULL OR source_file = :account_id)
                ORDER BY trade_date DESC, action DESC
            """)
            params = {"user_id": user_id, "account_id": account_id}
            return pd.read_sql(query, conn, params=params)

    def get_active_tickers(self, user_id: str, account_id: str = None) -> List[str]:
        with self.engine.connect() as conn:
            query = text("""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions
                WHERE user_id = :user_id AND (:account_id IS NULL OR source_file = :account_id)
                GROUP BY ticker
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"user_id": user_id, "account_id": account_id}
            rows = conn.execute(query, params).fetchall()
            return [r[0] for r in rows]

    def add(
        self,
        user_id: str,
        ticker: str,
        date: str,
        action: str,
        quantity: float,
        price: float,
        fees: float,
        leverage: float = 1.0,
        source_file: str = None,
        entry_category: str = ENTRY_CATEGORY_TRADE,
        amount: Optional[float] = None,
    ) -> None:
        """
        Insert a transaction record with write-time validation.
        寫入交易記錄，包含寫入時驗證防止非法資料進入資料庫。

        Validation rules:
          1. entry_category must be one of VALID_ENTRY_CATEGORIES.
          2. BUY / SELL actions must have a non-empty ticker.
          3. capital_flow entries must have action in CAPITAL_ACTIONS and amount > 0.
        """
        # Guard 1: entry_category must be a known value
        if entry_category not in VALID_ENTRY_CATEGORIES:
            raise ValueError(
                f"Invalid entry_category='{entry_category}'. "
                f"Must be one of {sorted(VALID_ENTRY_CATEGORIES)}. "
                f"Use constants: ENTRY_CATEGORY_TRADE, ENTRY_CATEGORY_CAPITAL_FLOW, "
                f"ENTRY_CATEGORY_SYNC_ADJUSTMENT."
            )

        # Guard 2: BUY/SELL must have a real ticker (prevents ghost trades)
        action_upper = action.upper()
        if action_upper in TRADE_ACTIONS and (not ticker or not ticker.strip()):
            raise ValueError(
                f"{action_upper} transaction requires a non-empty ticker, got: {ticker!r}. "
                f"Synthetic cash flows should use action='DEPOSIT'/'WITHDRAWAL'."
            )

        # Guard 3: capital_flow must use DEPOSIT/WITHDRAWAL with a positive amount
        if entry_category == ENTRY_CATEGORY_CAPITAL_FLOW:
            if action_upper not in CAPITAL_ACTIONS:
                raise ValueError(
                    f"capital_flow entry must use action DEPOSIT or WITHDRAWAL, "
                    f"got: '{action_upper}'. Trade entries should use entry_category='trade'."
                )

        # Compute amount: explicit override > derived from price * qty / leverage
        if amount is None:
            amount = (price * quantity) / leverage if leverage and leverage > 0 else (price * quantity)

        if entry_category == ENTRY_CATEGORY_CAPITAL_FLOW and amount <= 0:
            raise ValueError(
                f"capital_flow transaction must have amount > 0, got: {amount}. "
                f"Check price ({price}) and quantity ({quantity})."
            )

        with self.engine.begin() as conn:
            query_trans = text("""
                INSERT INTO transactions
                  (id, user_id, ticker, trade_date, action, quantity, price, fees,
                   amount, leverage, source_file, entry_category)
                VALUES
                  (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees,
                   :amount, :leverage, :source_file, :entry_category)
            """)
            conn.execute(query_trans, {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "ticker": ticker,
                "trade_date": date,
                "action": action_upper,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount,
                "leverage": leverage,
                "source_file": source_file,
                "entry_category": entry_category,
            })

    def get_holdings_summary(self, user_id: str, account_id: str = None) -> List[tuple]:
        with self.engine.connect() as conn:
            query = text("""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions 
                WHERE user_id = :uid AND (:account_id IS NULL OR source_file = :account_id)
                GROUP BY ticker 
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"uid": user_id, "account_id": account_id}
            rows = conn.execute(query, params).fetchall()
            return [(row[0], float(row[1])) for row in rows]

    def get_latest_leverage(self, user_id: str) -> float:
        with self.engine.connect() as conn:
            snap = conn.execute(text("SELECT leverage_ratio FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1"), {"uid": user_id}).fetchone()
            return float(snap[0]) if snap and snap[0] else 1.0

    def get_cash_flow_sum(self, user_id: str, account_id: str = None) -> float:
        """
        Calculates raw cash flow (Deposits - Withdrawals), INCLUDING sync adjustments.
        Used for current cash balance.
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT SUM(CASE 
                    WHEN action = 'DEPOSIT' THEN amount 
                    WHEN action = 'WITHDRAWAL' THEN -amount 
                    ELSE 0 
                END) FROM transactions 
                WHERE user_id = :user_id 
                AND (:account_id IS NULL OR source_file = :account_id)
            """)
            params = {"user_id": user_id, "account_id": account_id}
            result = conn.execute(query, params).fetchone()
            return float(result[0]) if result and result[0] is not None else 0.0

    def calculate_net_invested_capital(self, user_id: str, account_id: str = None) -> float:
        """
        Calculates user-contributed capital, EXCLUDING internal balancing adjustments.
        Filters by entry_category = 'capital_flow' so ETORO_SYNC entries are
        automatically excluded regardless of their ticker value.
        Used for ROI and PnL metrics.
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT SUM(CASE 
                    WHEN action = 'DEPOSIT' THEN amount 
                    WHEN action = 'WITHDRAWAL' THEN -amount 
                    ELSE 0 
                END) FROM transactions 
                WHERE user_id = :user_id 
                AND (:account_id IS NULL OR source_file = :account_id)
                AND entry_category = :category
            """)
            params = {
                "user_id": user_id, 
                "account_id": account_id,
                "category": ENTRY_CATEGORY_CAPITAL_FLOW
            }
            result = conn.execute(query, params).fetchone()
            return float(result[0]) if result and result[0] is not None else 0.0

    def get_cash_balance(self, user_id: str, account_id: str = None) -> float:
        with self.engine.connect() as conn:
            cash_flow_sum = self.get_cash_flow_sum(user_id, account_id)
            query_actions = text("""
                SELECT SUM(CASE 
                    WHEN action = 'BUY' THEN -amount 
                    WHEN action = 'SELL' THEN amount 
                    WHEN action = 'DIVIDEND' THEN amount 
                    WHEN action = 'FEE' THEN -amount
                    WHEN action = 'TAX' THEN -amount
                    ELSE 0 
                END) as impact
                FROM transactions 
                WHERE user_id = :user_id 
                AND (:account_id IS NULL OR source_file = :account_id)
            """)
            params = {"user_id": user_id, "account_id": account_id}
            impact = conn.execute(query_actions, params).scalar() or 0.0
            return float(cash_flow_sum + impact)

    def delete(self, user_id: str, transaction_id: str) -> None:
        with self.engine.begin() as conn:
            query = text("DELETE FROM transactions WHERE id = :id AND user_id = :user_id")
            conn.execute(query, {"id": transaction_id, "user_id": user_id})

    def get_holdings(self, user_id: str, account_id: str = None) -> List[Dict[str, Any]]:
        """
        Return open holdings with weighted-average cost.

        Strategy:
          1. If position_lots is seeded for this user → O(1) read from lots.
          2. Otherwise → O(N) fallback that replays BUY history (legacy path).
        """
        # --- Attempt O(1) path via position_lots ---
        try:
            from src.repositories.position_lot_repository import AlchemyPositionLotRepository
            lot_repo = AlchemyPositionLotRepository(self.engine)
            if lot_repo.has_lots_for_user(user_id):
                lots = lot_repo.get_open_lots(user_id)
                # Aggregate lots per ticker
                agg: Dict[str, Dict[str, float]] = {}
                for lot in lots:
                    t = lot["ticker"]
                    if t not in agg:
                        agg[t] = {"total_qty": 0.0, "total_cost": 0.0}
                    agg[t]["total_qty"] += lot["quantity"]
                    agg[t]["total_cost"] += lot["quantity"] * lot["open_price"]
                return [
                    {
                        "ticker": t,
                        "quantity": v["total_qty"],
                        "avg_price": v["total_cost"] / v["total_qty"] if v["total_qty"] > 0 else 0.0,
                    }
                    for t, v in agg.items()
                    if v["total_qty"] > 0.0001
                ]
        except Exception: # nosec B110
            pass  # Gracefully fall back to legacy path

        # --- Legacy O(N) fallback: weighted-average BUY price ---
        with self.engine.connect() as conn:
            query = text("""
                SELECT ticker,
                       SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty,
                       SUM(CASE WHEN action='BUY' THEN quantity * price ELSE 0 END) /
                           NULLIF(SUM(CASE WHEN action='BUY' THEN quantity ELSE 0 END), 0) as avg_price
                FROM transactions
                WHERE user_id = :uid AND (:account_id IS NULL OR source_file = :account_id)
                GROUP BY ticker
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"uid": user_id, "account_id": account_id}
            rows = conn.execute(query, params).fetchall()
            return [{"ticker": r[0], "quantity": float(r[1]), "avg_price": float(r[2])} for r in rows]

    def get_leverage_summary(self, user_id: str, account_id: str = None) -> List[tuple]:
        with self.engine.connect() as conn:
            query = text("""
                SELECT ticker, 
                       SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty,
                       SUM(CASE 
                         WHEN action='BUY' THEN quantity * leverage 
                         WHEN action='SELL' THEN -quantity * leverage 
                         ELSE 0 END) / 
                       NULLIF(SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END), 0) as avg_leverage
                FROM transactions 
                WHERE user_id = :uid AND (:account_id IS NULL OR source_file = :account_id)
                GROUP BY ticker
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"uid": user_id, "account_id": account_id}
            rows = conn.execute(query, params).fetchall()
            return [(r[0], float(r[1]), float(r[2] or 1.0)) for r in rows]

    def get_all_accounts(self, user_id: str) -> List[str]:
        with self.engine.connect() as conn:
            query = text("SELECT DISTINCT source_file FROM transactions WHERE user_id = :uid AND source_file IS NOT NULL")
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            return [r[0] for r in rows]
