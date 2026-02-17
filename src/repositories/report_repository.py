from abc import ABC, abstractmethod
from typing import Any
import pandas as pd
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

class IReportRepository(ABC):
    """
    Interface for Report Repository.
    報告儲存庫介面。
    """
    @abstractmethod
    def get_latest_reports(self, limit: int = 100) -> pd.DataFrame:
        """
        Get latest reports as a DataFrame.
        取得最新報告的資料表。
        """
        pass

class ReportRepositoryImpl(BaseRepository, IReportRepository):
    """
    Implementation of IReportRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IReportRepository。
    """
    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))

    def get_latest_reports(self, limit: int = 100) -> pd.DataFrame:
        """
        Get latest reports as a DataFrame.
        取得最新報告的資料表。
        """
        with self.engine.connect() as conn:
            # Map new schema to expected output if necessary
            query = text("SELECT created_at as date, title as summary, content FROM reports ORDER BY created_at DESC LIMIT :limit")
            return pd.read_sql(query, conn, params={"limit": limit})

# Legacy alias
# @deprecated: Use ReportRepositoryImpl
SqliteReportRepository = ReportRepositoryImpl
