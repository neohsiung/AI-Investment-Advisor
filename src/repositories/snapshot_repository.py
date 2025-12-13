from abc import ABC, abstractmethod
import pandas as pd
from sqlalchemy import text
from src.data.database import get_db_connection

class SnapshotRepository(ABC):
    @abstractmethod
    def get_history_by_user(self, user_id):
        pass

    @abstractmethod
    def get_latest_by_user(self, user_id):
        pass

class SqliteSnapshotRepository(SnapshotRepository):
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def get_history_by_user(self, user_id):
        """Returns dataframe of all snapshots for a user."""
        conn = get_db_connection(self.db_path)
        try:
            query = "SELECT * FROM daily_snapshots WHERE user_id = :uid ORDER BY date ASC"
            df = pd.read_sql(query, conn, params={"uid": user_id})
            return df
        finally:
            conn.close()

    def get_latest_by_user(self, user_id):
        """Returns the latest snapshot row as a dict or Series."""
        conn = get_db_connection(self.db_path)
        try:
            query = "SELECT * FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1"
            df = pd.read_sql(query, conn, params={"uid": user_id})
            if not df.empty:
                return df.iloc[0]
            return None
        finally:
            conn.close()
