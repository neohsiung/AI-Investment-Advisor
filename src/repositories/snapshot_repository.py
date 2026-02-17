from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union
import pandas as pd
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

class ISnapshotRepository(ABC):
    """
    Interface for Snapshot Repository.
    快照儲存庫介面。
    """
    @abstractmethod
    def get_history_by_user(self, user_id: str) -> pd.DataFrame:
        """
        Get all snapshots for a user as a DataFrame.
        取得使用者的所有快照資料 (DataFrame)。
        """
        pass

    @abstractmethod
    def get_latest_by_user(self, user_id: str) -> Optional[Union[pd.Series, Dict[str, Any]]]:
        """
        Get the latest snapshot for a user.
        取得使用者的最新快照。
        """
        pass

    @abstractmethod
    def save_snapshot(
        self, 
        user_id: str, 
        date: str, 
        nlv: float, 
        cash_balance: float, 
        invested_capital: float, 
        pnl: float, 
        total_tnv: float, 
        leverage_ratio: float
    ) -> None:
        """
        Save or update a daily snapshot.
        儲存或更新每日快照。
        """
        pass

class SnapshotRepositoryImpl(BaseRepository, ISnapshotRepository):
    """
    Implementation of ISnapshotRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 ISnapshotRepository。
    """
    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))

    def get_history_by_user(self, user_id: str) -> pd.DataFrame:
        """
        Get all snapshots for a user as a DataFrame.
        取得使用者的所有快照資料 (DataFrame)。
        """
        with self.engine.connect() as conn:
            query = text("SELECT * FROM daily_snapshots WHERE user_id = :uid ORDER BY date ASC")
            return pd.read_sql(query, conn, params={"uid": user_id})

    def get_latest_by_user(self, user_id: str) -> Optional[Union[pd.Series, Dict[str, Any]]]:
        """
        Get the latest snapshot for a user.
        取得使用者的最新快照。
        """
        with self.engine.connect() as conn:
            query = text("SELECT * FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1")
            df = pd.read_sql(query, conn, params={"uid": user_id})
            if not df.empty:
                return df.iloc[0]
            return None

    def save_snapshot(
        self, 
        user_id: str, 
        date: str, 
        nlv: float, 
        cash_balance: float, 
        invested_capital: float, 
        pnl: float, 
        total_tnv: float, 
        leverage_ratio: float
    ) -> None:
        """
        Save or update a daily snapshot.
        儲存或更新每日快照。
        """
        with self.engine.begin() as conn:
            sql = text('''
                INSERT INTO daily_snapshots (date, user_id, total_nlv, cash_balance, invested_capital, pnl, total_tnv, leverage_ratio)
                VALUES (:date, :user_id, :nlv, :cash_balance, :invested_capital, :pnl, :tnv, :lev)
                ON CONFLICT (date, user_id) DO UPDATE SET
                    total_nlv = EXCLUDED.total_nlv,
                    cash_balance = EXCLUDED.cash_balance,
                    invested_capital = EXCLUDED.invested_capital,
                    pnl = EXCLUDED.pnl,
                    total_tnv = EXCLUDED.total_tnv,
                    leverage_ratio = EXCLUDED.leverage_ratio
            ''')
            
            conn.execute(sql, {
                "date": date,
                "user_id": user_id,
                "nlv": nlv,
                "cash_balance": cash_balance,
                "invested_capital": invested_capital,
                "pnl": pnl,
                "tnv": total_tnv,
                "lev": leverage_ratio
            })

# Legacy aliases
# @deprecated: Use SnapshotRepositoryImpl
SqliteSnapshotRepository = SnapshotRepositoryImpl
SnapshotRepository = ISnapshotRepository
