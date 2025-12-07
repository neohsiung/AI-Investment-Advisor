from abc import ABC, abstractmethod
from sqlalchemy import text
from src.database import get_db_connection
import pandas as pd

class ITransactionRepository(ABC):
    @abstractmethod
    def get_all_by_user(self, user_id: str):
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

    def add(self, user_id: str, ticker: str, date: str, action: str, quantity: float, price: float, fees: float):
        """
        新增一筆交易紀錄
        """
        import uuid
        
        # Calculate amount (Total cost/proceeds)
        # Note: Usually Amount = (Price * Quantity) +/- Fees depending on sign
        # But schema says amount. Let's assume standard absolute val or let logic handle sign?
        # In ingestor manual trade: usually cost basis.
        # Let's simple cal: Amount = Price * Quantity
        amount = price * quantity
        
        with get_db_connection() as conn:
            query = text("""
                INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount)
                VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount)
            """)
            conn.execute(query, {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "ticker": ticker,
                "trade_date": date,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount
            })
            conn.commit()

    def delete(self, user_id: str, transaction_id: int):
        """
        刪除特定 ID 的交易紀錄 (需驗證 user_id)
        """
        with get_db_connection() as conn:
            query = text("DELETE FROM transactions WHERE id = :id AND user_id = :user_id")
            conn.execute(query, {"id": transaction_id, "user_id": user_id})
            conn.commit()

    def get_holdings(self, user_id: str):
        """
        取得使用者的當前持倉 (聚合計算)
        TODO: 這部分邏輯目前散落在 analytics.py，未來可遷移至此
        """
        pass
