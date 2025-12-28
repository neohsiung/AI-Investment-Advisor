from abc import ABC, abstractmethod
import pandas as pd
from sqlalchemy import text
from src.data.database import get_db_connection

class IDataRepository(ABC):
    @abstractmethod
    def get_table_preview(self, table_name: str, user_id: str, limit: int = 100) -> pd.DataFrame:
        pass

class SqliteDataRepository(IDataRepository):
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def get_table_preview(self, table_name: str, user_id: str, limit: int = 100) -> pd.DataFrame:
        # Whitelist validation
        allowed_tables = ["transactions", "daily_snapshots", "cash_flows", "positions", "reports", "settings", "prompt_history"]
        if table_name not in allowed_tables:
            raise ValueError("Invalid table name")

        conn = get_db_connection(self.db_path)
        try:
            # Using f-string safely because of whitelist above
            query = text(f"SELECT * FROM {table_name} WHERE user_id = :uid ORDER BY 1 DESC LIMIT :limit")
            df = pd.read_sql(query, conn, params={"uid": user_id, "limit": limit})
            return df
        finally:
            conn.close()
