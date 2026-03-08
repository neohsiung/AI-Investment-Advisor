from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
import pandas as pd
import uuid

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
    def add(self, user_id: str, ticker: str, date: str, action: str, quantity: float, price: float, fees: float, leverage: float = 1.0, source_file: str = None) -> None:
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
            if account_id:
                sql += " AND source_file = :account_id"
                params["account_id"] = account_id
            sql += " ORDER BY trade_date DESC, action DESC"
            return conn.execute(text(sql), params).fetchall()

    def get_all_by_user_df(self, user_id: str, account_id: str = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            sql = "SELECT * FROM transactions WHERE user_id = :user_id"
            params = {"user_id": user_id}
            if account_id:
                sql += " AND source_file = :account_id"
                params["account_id"] = account_id
            sql += " ORDER BY trade_date DESC, action DESC"
            return pd.read_sql(text(sql), conn, params=params)

    def get_active_tickers(self, user_id: str, account_id: str = None) -> List[str]:
        with self.engine.connect() as conn:
            acc_filter = " AND source_file = :account_id" if account_id else ""
            query = text(f"""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions
                WHERE user_id = :user_id {acc_filter}
                GROUP BY ticker
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"user_id": user_id}
            if account_id: params["account_id"] = account_id
            rows = conn.execute(query, params).fetchall()
            return [r[0] for r in rows]

    def add(self, user_id: str, ticker: str, date: str, action: str, quantity: float, price: float, fees: float, leverage: float = 1.0, source_file: str = None) -> None:
        amount = (price * quantity) / leverage if leverage and leverage > 0 else (price * quantity)
        with self.engine.begin() as conn:
            query_trans = text("""
                INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, leverage, source_file)
                VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, :leverage, :source_file)
            """)
            conn.execute(query_trans, {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "ticker": ticker,
                "trade_date": date,
                "action": action.upper(),
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount,
                "leverage": leverage,
                "source_file": source_file
            })

    def get_holdings_summary(self, user_id: str, account_id: str = None) -> List[tuple]:
        with self.engine.connect() as conn:
            acc_filter = " AND source_file = :account_id" if account_id else ""
            query = text(f"""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions WHERE user_id = :uid {acc_filter} 
                GROUP BY ticker 
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"uid": user_id}
            if account_id: params["account_id"] = account_id
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
            acc_filter = " AND source_file = :account_id" if account_id else ""
            query = text(f"""
                SELECT SUM(CASE 
                    WHEN action = 'DEPOSIT' THEN amount 
                    WHEN action = 'WITHDRAWAL' THEN -amount 
                    ELSE 0 
                END) FROM transactions WHERE user_id = :user_id {acc_filter}
            """)
            params = {"user_id": user_id}
            if account_id: params["account_id"] = account_id
            result = conn.execute(query, params).fetchone()
            return float(result[0]) if result and result[0] is not None else 0.0

    def calculate_net_invested_capital(self, user_id: str, account_id: str = None) -> float:
        """
        Calculates user-contributed capital, EXCLUDING internal balancing adjustments.
        Used for ROI and PnL metrics.
        """
        with self.engine.connect() as conn:
            acc_filter = " AND source_file = :account_id" if account_id else ""
            query = text(f"""
                SELECT SUM(CASE 
                    WHEN action = 'DEPOSIT' THEN amount 
                    WHEN action = 'WITHDRAWAL' THEN -amount 
                    ELSE 0 
                END) FROM transactions 
                WHERE user_id = :user_id 
                {acc_filter}
                AND ticker NOT IN ('CASH', 'STABILIZE_CASH', 'STABILIZE_CAP', 'ETORO_SYNC')
            """)
            params = {"user_id": user_id}
            if account_id: params["account_id"] = account_id
            result = conn.execute(query, params).fetchone()
            return float(result[0]) if result and result[0] is not None else 0.0

    def get_cash_balance(self, user_id: str, account_id: str = None) -> float:
        with self.engine.connect() as conn:
            cash_flow_sum = self.get_cash_flow_sum(user_id, account_id)
            acc_filter = " AND source_file = :account_id" if account_id else ""
            query_actions = text(f"""
                SELECT SUM(CASE 
                    WHEN action = 'BUY' THEN -amount 
                    WHEN action = 'SELL' THEN amount 
                    WHEN action = 'DIVIDEND' THEN amount 
                    WHEN action = 'FEE' THEN -amount
                    WHEN action = 'TAX' THEN -amount
                    ELSE 0 
                END) as impact
                FROM transactions 
                WHERE user_id = :user_id {acc_filter}
            """)
            params = {"user_id": user_id}
            if account_id: params["account_id"] = account_id
            impact = conn.execute(query_actions, params).scalar() or 0.0
            return float(cash_flow_sum + impact)

    def delete(self, user_id: str, transaction_id: str) -> None:
        with self.engine.begin() as conn:
            query = text("DELETE FROM transactions WHERE id = :id AND user_id = :user_id")
            conn.execute(query, {"id": transaction_id, "user_id": user_id})

    def get_holdings(self, user_id: str, account_id: str = None) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            acc_filter = " AND source_file = :account_id" if account_id else ""
            query = text(f"""
                SELECT ticker, 
                       SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty,
                       AVG(price) as avg_price
                FROM transactions 
                WHERE user_id = :uid {acc_filter}
                GROUP BY ticker 
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"uid": user_id}
            if account_id: params["account_id"] = account_id
            rows = conn.execute(query, params).fetchall()
            return [{"ticker": r[0], "quantity": float(r[1]), "avg_price": float(r[2])} for r in rows]

    def get_leverage_summary(self, user_id: str, account_id: str = None) -> List[tuple]:
        with self.engine.connect() as conn:
            acc_filter = " AND source_file = :account_id" if account_id else ""
            query = text(f"""
                SELECT ticker, 
                       SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty,
                       SUM(CASE 
                         WHEN action='BUY' THEN quantity * leverage 
                         WHEN action='SELL' THEN -quantity * leverage 
                         ELSE 0 END) / 
                       NULLIF(SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END), 0) as avg_leverage
                FROM transactions 
                WHERE user_id = :uid {acc_filter}
                GROUP BY ticker
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            params = {"uid": user_id}
            if account_id: params["account_id"] = account_id
            rows = conn.execute(query, params).fetchall()
            return [(r[0], float(r[1]), float(r[2] or 1.0)) for r in rows]

    def get_all_accounts(self, user_id: str) -> List[str]:
        with self.engine.connect() as conn:
            query = text("SELECT DISTINCT source_file FROM transactions WHERE user_id = :uid AND source_file IS NOT NULL")
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            return [r[0] for r in rows]
