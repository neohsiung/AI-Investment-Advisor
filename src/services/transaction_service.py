from sqlalchemy import text
import uuid
import json
from datetime import datetime
import pandas as pd
from src.database import get_db_connection
from src.ingestor import TradeIngestor
from src.analytics import update_daily_snapshot

class TransactionService:
    def __init__(self, db_path=None, user_id=None):
        self.db_path = db_path
        self.user_id = user_id

    def get_transactions(self, limit=100):
        """Retrieves recent transactions."""
        conn = get_db_connection(self.db_path)
        try:
            if self.user_id:
                query = text("SELECT * FROM transactions WHERE user_id = :uid ORDER BY trade_date DESC LIMIT :limit")
                df = pd.read_sql(query, conn, params={"limit": limit, "uid": self.user_id}) 
            else:
                # Fallback for generic access (admin tool?) or empty
                query = text("SELECT * FROM transactions ORDER BY trade_date DESC LIMIT :limit")
                df = pd.read_sql(query, conn, params={"limit": limit})
            return df
        except Exception as e:
            print(f"Error fetching transactions: {e}")
            return None # Return empty DF?
        finally:
            conn.close()

    def add_manual_trade(self, ticker, date_str, action, quantity, price, fees):
        """Adds a manual transaction via Ingestor and updates snapshot."""
        try:
            ingestor = TradeIngestor(db_path=self.db_path)
            # Pass user_id
            ingestor.ingest_manual_trade(ticker, date_str, action, quantity, price, fees, user_id=self.user_id)
            
            # Trigger snapshot update
            update_daily_snapshot(db_path=self.db_path, user_id=self.user_id)
            return True, f"已新增交易: {action} {quantity} {ticker} @ {price}"
        except Exception as e:
            return False, f"交易新增失敗: {e}"

    def delete_transaction(self, transaction_id):
        """Deletes a transaction by ID."""
        conn = get_db_connection(self.db_path)
        try:
            # Enforce user_id check
            if self.user_id:
                conn.execute(text("DELETE FROM transactions WHERE id = :id AND user_id = :uid"), {"id": transaction_id, "uid": self.user_id})
            else:
                conn.execute(text("DELETE FROM transactions WHERE id = :id"), {"id": transaction_id})
            conn.commit()
            
            # Recalculate snapshot
            update_daily_snapshot(db_path=self.db_path, user_id=self.user_id)
            
            return True, f"Transaction {transaction_id} deleted."
        except Exception as e:
            return False, f"Failed to delete transaction: {e}"
        finally:
            conn.close()
