from abc import ABC, abstractmethod
import pandas as pd
from sqlalchemy import text
from src.data.database import get_db_connection

class IReportRepository(ABC):
    @abstractmethod
    def get_latest_reports(self, limit: int = 100) -> pd.DataFrame:
        pass

class SqliteReportRepository(IReportRepository):
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def get_latest_reports(self, limit: int = 100) -> pd.DataFrame:
        conn = get_db_connection(self.db_path)
        try:
            query = text(f"SELECT date, summary, content FROM reports ORDER BY date DESC LIMIT :limit")
            df = pd.read_sql(query, conn, params={"limit": limit})
            return df
        finally:
            conn.close()
