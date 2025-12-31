from abc import ABC, abstractmethod
from sqlalchemy import text
from src.data.database import get_db_connection
import pandas as pd

class ITransactionRepository(ABC):
    @abstractmethod
    def get_all_by_user(self, user_id: str):
        pass

    @abstractmethod
    def get_active_tickers(self, user_id: str):
        """Get list of tickers where user has a positive holding quantity (> 0.0001)."""
        pass

    @abstractmethod
    def add(self, user_id: str, ticker: str, date: str, action: str, quantity: float, price: float, fees: float):
        pass

    @abstractmethod
    def delete(self, user_id: str, transaction_id: int):
        pass

    @abstractmethod
    def get_holdings(self, user_id: str):
        pass

    @abstractmethod
    def get_holdings_summary(self, user_id: str):
        """
        Get aggregated holdings for a user.
        取得使用者的聚合持倉 (Ticker, Quantity)。
        """
        pass

    @abstractmethod
    def get_latest_leverage(self, user_id: str):
        """
        Get the latest leverage ratio from daily snapshots.
        從每日快照中取得最新的槓桿比率。
        """
        pass

    @abstractmethod
    def get_cash_flow_sum(self, user_id: str) -> float:
        """
        Calculate total cash flows (excluding trades).
        """
        pass

    @abstractmethod
    def calculate_net_invested_capital(self, user_id: str) -> float:
        """
        Calculate net invested capital (Deposits - Withdrawals).
        """
        pass

class SqliteTransactionRepository(ITransactionRepository):
    def get_all_by_user(self, user_id: str):
        """
        取得特定使用者的所有交易紀錄
        """
        with get_db_connection() as conn:
            query = text("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY trade_date DESC")
            result = conn.execute(query, {"user_id": user_id})
            return result.fetchall()

    def get_all_by_user_df(self, user_id: str) -> pd.DataFrame:
        """
        取得特定使用者的所有交易紀錄 (DataFrame 格式)
        """
        with get_db_connection() as conn:
            query = "SELECT * FROM transactions WHERE user_id = :user_id ORDER BY trade_date DESC"
            return pd.read_sql(query, conn, params={"user_id": user_id})

    def get_unique_tickers(self, user_id: str):
        """Get list of unique tickers traded by user."""
        with get_db_connection() as conn:
            query = text("SELECT DISTINCT ticker FROM transactions WHERE user_id = :user_id")
            rows = conn.execute(query, {"user_id": user_id}).fetchall()
            return [r[0] for r in rows]

    def get_active_tickers(self, user_id: str):
        """Get list of tickers where user has a positive holding quantity (> 0.0001)."""
        with get_db_connection() as conn:
            query = text("""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions
                WHERE user_id = :user_id
                GROUP BY ticker
                HAVING net_qty > 0.0001
            """)
            rows = conn.execute(query, {"user_id": user_id}).fetchall()
            return [r[0] for r in rows]

    def add(self, user_id: str, ticker: str, date: str, action: str, quantity: float, price: float, fees: float):
        """
        新增一筆交易紀錄
        """
        import uuid

        # Calculate amount (Total cost/proceeds)
        amount = price * quantity
        transaction_id = str(uuid.uuid4())

        with get_db_connection() as conn:
            # Determine standardized action
            std_action = action.upper()
            if std_action == 'WITHDRAW':
                std_action = 'WITHDRAWAL'

            # Insert into transactions (Activity Log)
            query_trans = text("""
                INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount)
                VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount)
            """)
            conn.execute(query_trans, {
                "id": transaction_id,
                "user_id": user_id,
                "ticker": ticker,
                "trade_date": date,
                "action": std_action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount
            })

            # Check for Cash Flow (Deposit/Withdrawal)
            # Analytics engine relies on 'cash_flows' table for NLV/ROI calculations
            if std_action in ['DEPOSIT', 'WITHDRAWAL']:
                query_cash = text("""
                    INSERT INTO cash_flows (id, user_id, date, amount, type, description)
                    VALUES (:id, :user_id, :date, :amount, :type, :desc)
                """)
                conn.execute(query_cash, {
                    "id": transaction_id,
                    "user_id": user_id,
                    "date": date,
                    "amount": amount,
                    "type": std_action,
                    "desc": f"Manual {std_action} via UI"
                })

            conn.commit()

    def delete(self, user_id: str, transaction_id: int):
        """
        刪除特定 ID 的交易紀錄 (需驗證 user_id)
        同時嘗試刪除關聯的 cash_flows (如果存在)
        """
        with get_db_connection() as conn:
            # Delete from transactions
            query_trans = text("DELETE FROM transactions WHERE id = :id AND user_id = :user_id")
            conn.execute(query_trans, {"id": transaction_id, "user_id": user_id})

            # Delete from cash_flows (if it was a deposit/withdrawal)
            query_cash = text("DELETE FROM cash_flows WHERE id = :id AND user_id = :user_id")
            conn.execute(query_cash, {"id": transaction_id, "user_id": user_id})

            conn.commit()

    def get_holdings_summary(self, user_id: str):
        """
        Get aggregated holdings for a user.
        取得使用者的聚合持倉 (Ticker, Quantity)。
        """
        with get_db_connection() as conn:
            query = text("""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions WHERE user_id = :uid GROUP BY ticker HAVING net_qty > 0.0001
            """)
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            return [(row[0], row[1]) for row in rows]

    def get_latest_leverage(self, user_id: str):
        """
        Get the latest leverage ratio from daily snapshots.
        從每日快照中取得最新的槓桿比率。
        """
        with get_db_connection() as conn:
            snap = conn.execute(text("SELECT leverage_ratio FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1"), {"uid": user_id}).fetchone()
            return float(snap[0]) if snap and snap[0] else 1.0

    def get_cash_flow_sum(self, user_id: str) -> float:
        """
        Calculate total cash flows (sum of amounts in cash_flows table).
        Used for NLV calculation.
        """
        with get_db_connection() as conn:
            query = text("SELECT SUM(amount) FROM cash_flows WHERE user_id = :user_id")
            result = conn.execute(query, {"user_id": user_id}).fetchone()
            return result[0] if result and result[0] is not None else 0.0

    def calculate_net_invested_capital(self, user_id: str) -> float:
        """
        Calculate net invested capital (Deposits - Withdrawals).
        """
        with get_db_connection() as conn:
            query = text("SELECT SUM(CASE WHEN type='DEPOSIT' THEN amount WHEN type='WITHDRAWAL' THEN -amount ELSE 0 END) FROM cash_flows WHERE user_id = :user_id")
            result = conn.execute(query, {"user_id": user_id}).fetchone()
            return result[0] if result and result[0] is not None else 0.0

    def get_holdings(self, user_id: str):
        """
        取得使用者的當前持倉 (聚合計算)
        TODO: 這部分邏輯目前散落在 analytics.py，未來可遷移至此
        """
        pass
