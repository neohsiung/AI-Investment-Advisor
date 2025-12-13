from sqlalchemy import text
import uuid
import json
from datetime import datetime
import pandas as pd
from src.data.database import get_db_connection
# from src.ingestor import TradeIngestor # Removed for Clean Clean Architecture
from src.analytics import update_daily_snapshot

class TransactionService:
    def __init__(self, db_path="data/portfolio.db", user_id=None, repository=None):
        self.db_path = db_path
        self.user_id = user_id
        # Allow injection or default to Sqlite
        from src.repositories.transaction_repository import SqliteTransactionRepository
        self.repository = repository or SqliteTransactionRepository()

    def get_transactions(self, user_id=None):
        """
        Get all transactions for a user.
        If user_id is not provided, use self.user_id
        """
        uid = user_id or self.user_id
        if not uid:
            return pd.DataFrame()
        return self.repository.get_all_by_user_df(uid)

    def add_manual_trade(self, ticker, date_str, action, quantity, price, fees):
        """Adds a manual transaction via Repository and updates snapshot."""
        if not self.user_id:
             return False, "User ID not set."

        try:
            # Use Repository
            self.repository.add(
                user_id=self.user_id,
                ticker=ticker,
                date=date_str,
                action=action,
                quantity=quantity,
                price=price,
                fees=fees
            )

            # Trigger snapshot update
            update_daily_snapshot(db_path=self.db_path, user_id=self.user_id)
            return True, f"已新增交易: {action} {quantity} {ticker} @ {price}"
        except Exception as e:
            return False, f"交易新增失敗: {e}"

    def delete_transaction(self, transaction_id):
        """Deletes a transaction by ID."""
        if not self.user_id:
             return False, "User ID not set."

        try:
            # Use Repository
            self.repository.delete(user_id=self.user_id, transaction_id=transaction_id)

            # Recalculate snapshot
            update_daily_snapshot(db_path=self.db_path, user_id=self.user_id)

            return True, f"Transaction {transaction_id} deleted."
        except Exception as e:
            return False, f"Failed to delete transaction: {e}"
