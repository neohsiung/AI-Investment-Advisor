from abc import ABC, abstractmethod
from typing import List, Any, Dict
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
    def get_all_by_user(self, user_id: str) -> List[Any]:
        """
        Get all transactions for a specific user.
        取得特定使用者的所有交易。
        """
        pass

    @abstractmethod
    def get_active_tickers(self, user_id: str) -> List[str]:
        """
        Get list of tickers where user has a positive holding quantity.
        取得使用者持有數量大於 0 的標的列表。
        """
        pass

    @abstractmethod
    def add(self, user_id: str, ticker: str, date: str, action: str, quantity: float, price: float, fees: float) -> None:
        """
        Add a new transaction.
        新增一筆交易。
        """
        pass

    @abstractmethod
    def delete(self, user_id: str, transaction_id: str) -> None:
        """
        Delete a transaction.
        刪除一筆交易。
        """
        pass

    @abstractmethod
    def get_holdings(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Returns detailed holdings for a user.
        取得使用者的詳細持倉資料。
        """
        pass

    @abstractmethod
    def get_holdings_summary(self, user_id: str) -> List[tuple]:
        """
        Get aggregated holdings (Ticker, Quantity) for a user.
        取得使用者的聚合持倉 (標的, 數量)。
        """
        pass

    @abstractmethod
    def get_latest_leverage(self, user_id: str) -> float:
        """
        Get the latest leverage ratio from daily snapshots.
        從每日快照中取得最新的槓桿比率。
        """
        pass

    @abstractmethod
    def get_cash_flow_sum(self, user_id: str) -> float:
        """
        Calculate total cash flows (excluding trades).
        計算總現金流 (不含交易)。
        """
        pass

    @abstractmethod
    def calculate_net_invested_capital(self, user_id: str) -> float:
        """
        Calculate net invested capital (Deposits - Withdrawals).
        計算淨投入資本 (存款 - 提款)。
        """
        pass

    @abstractmethod
    def get_cash_balance(self, user_id: str) -> float:
        """
        Calculate final cash balance by combining cash flows and trade impacts.
        透過結合現金流與交易影響計算最終現金餘額。
        """
        pass

    @abstractmethod
    def get_leverage_summary(self, user_id: str) -> List[tuple]:
        """
        Get leverage summary (Ticker, Net Qty, Avg Leverage) for a user.
        取得投資組合槓桿摘要 (標的, 淨數量, 平均槓桿)。
        """
        pass

class AlchemyTransactionRepository(BaseRepository, ITransactionRepository):
    """
    Implementation of ITransactionRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 ITransactionRepository。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def get_all_by_user(self, user_id: str) -> List[Any]:
        """
        Get all transactions for a specific user.
        取得特定使用者的所有交易。
        """
        with self.engine.connect() as conn:
            # v4.2.3: Used action DESC for deterministic tie-breaking without created_at dependency.
            # Reversed in PnLCalculator, this ensures BUY is processed before SELL.
            query = text("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY trade_date DESC, action DESC")
            result = conn.execute(query, {"user_id": user_id})
            return result.fetchall()

    def get_all_by_user_df(self, user_id: str) -> pd.DataFrame:
        """
        Get all transactions for a user as a DataFrame.
        取得使用者的所有交易資料 (DataFrame)。
        """
        with self.engine.connect() as conn:
            # v4.2.3: Deterministic tie-breaking
            query = text("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY trade_date DESC, action DESC")
            return pd.read_sql(query, conn, params={"user_id": user_id})

    def get_active_tickers(self, user_id: str) -> List[str]:
        """
        Get list of tickers where user has a positive holding quantity.
        取得使用者持有數量大於 0 的標的列表。
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions
                WHERE user_id = :user_id
                GROUP BY ticker
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            rows = conn.execute(query, {"user_id": user_id}).fetchall()
            return [r[0] for r in rows]

    def add(self, user_id: str, ticker: str, date: str, action: str, quantity: float, price: float, fees: float, leverage: float = 1.0) -> None:
        """
        Add a new transaction.
        新增一筆交易。
        """
        # Calculate amount (true cash impact, which is nominal value divided by leverage)
        # 修正: amount 代表真實的現金影響 (Margin)，而非名目價值 (Nominal Value)
        # 若為 2x 槓桿，實際投入現金只需一半。
        amount = (price * quantity) / leverage if leverage and leverage > 0 else (price * quantity)
        
        with self.engine.begin() as conn:
            std_action = action.upper()
            query_trans = text("""
                INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, leverage)
                VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, :leverage)
            """)
            conn.execute(query_trans, {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "ticker": ticker,
                "trade_date": date,
                "action": std_action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount,
                "leverage": leverage
            })

    def get_holdings_summary(self, user_id: str) -> List[tuple]:
        """
        Get aggregated holdings (Ticker, Quantity) for a user.
        取得使用者的聚合持倉 (標的, 數量)。
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions WHERE user_id = :uid GROUP BY ticker HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            return [(row[0], float(row[1])) for row in rows]

    def get_latest_leverage(self, user_id: str) -> float:
        """
        Get the latest leverage ratio from daily snapshots.
        從每日快照中取得最新的槓桿比率。
        """
        with self.engine.connect() as conn:
            # Note: daily_snapshots table needs to exist
            snap = conn.execute(text("SELECT leverage_ratio FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1"), {"uid": user_id}).fetchone()
            return float(snap[0]) if snap and snap[0] else 1.0

    def get_cash_flow_sum(self, user_id: str) -> float:
        with self.engine.connect() as conn:
            # Logic: Sum of DEPOSIT - WITHDRAWAL (Corrected v4.2.0)
            # v4.2.0: 修正存款與提款的加總邏輯
            query = text("""
                SELECT SUM(CASE 
                    WHEN action = 'DEPOSIT' THEN amount 
                    WHEN action = 'WITHDRAWAL' THEN -amount 
                    ELSE 0 
                END) FROM transactions WHERE user_id = :user_id
            """)
            result = conn.execute(query, {"user_id": user_id}).fetchone()
            return float(result[0]) if result and result[0] is not None else 0.0
    def get_cash_balance(self, user_id: str) -> float:
        """
        Calculate final cash balance.
        計算最終現金餘額。
        """
        with self.engine.connect() as conn:
            # 1. Get Sum of (DEPOSIT - WITHDRAWAL) from transactions table.
            cash_flow_sum = self.get_cash_flow_sum(user_id)
            
            # 2. Get Sum of cash impact from other actions
            # BUY, FEE, TAX require cash (-)
            # SELL, DIVIDEND provide cash (+)
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
            """)
            impact = conn.execute(query_actions, {"user_id": user_id}).scalar() or 0.0
            
            return float(cash_flow_sum + impact)

    def calculate_net_invested_capital(self, user_id: str) -> float:
        """
        Calculate net invested capital (Deposits - Withdrawals).
        計算淨投入資本 (存款 - 提款)。
        """
        return self.get_cash_flow_sum(user_id)

    def delete(self, user_id: str, transaction_id: str) -> None:
        """
        Delete a specific transaction.
        刪除特定交易。
        """
        with self.engine.begin() as conn:
            query = text("DELETE FROM transactions WHERE id = :id AND user_id = :user_id")
            conn.execute(query, {"id": transaction_id, "user_id": user_id})

    def get_holdings(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Returns detailed holdings (Ticker, Quantity, Avg Price).
        取得詳細持倉資料 (標的, 數量, 平均成本)。
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT ticker, 
                       SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty,
                       AVG(price) as avg_price
                FROM transactions 
                WHERE user_id = :uid 
                GROUP BY ticker 
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            return [{"ticker": r[0], "quantity": float(r[1]), "avg_price": float(r[2])} for r in rows]

    def get_leverage_summary(self, user_id: str) -> List[tuple]:
        """
        Get leverage summary (Ticker, Net Qty, Avg Leverage) for a user.
        取得投資組合槓桿摘要 (標的, 淨數量, 平均槓桿)。
        """
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
                WHERE user_id = :uid 
                GROUP BY ticker
                HAVING SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) > 0.0001
            """)
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            return [(r[0], float(r[1]), float(r[2] or 1.0)) for r in rows]

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyTransactionRepository
