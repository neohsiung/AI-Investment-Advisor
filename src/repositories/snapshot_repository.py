from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union
import pandas as pd
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

class ISnapshotRepository(ABC):
    """
    Interface for Snapshot Repository.
    快照儲存庫介面。
    """
    @abstractmethod
    def get_history_by_user(self, user_id: str, account_id: str = None) -> pd.DataFrame:
        """
        Get all snapshots for a user as a DataFrame.
        取得使用者的所有快照資料 (DataFrame)。
        """
        pass

    @abstractmethod
    def get_latest_by_user(self, user_id: str, account_id: str = None) -> Optional[Union[pd.Series, Dict[str, Any]]]:
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
        leverage_ratio: float,
        conviction_level: float = 0.0,
        time_horizon: Optional[str] = None,
        account_id: str = None
    ) -> None:
        """
        Save or update a daily snapshot.
        儲存或更新每日快照。
        """
        pass

class AlchemySnapshotRepository(BaseRepository, ISnapshotRepository):
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

    def get_history_by_user(self, user_id: str, account_id: str = None) -> pd.DataFrame:
        """
        Get all snapshots for a user as a DataFrame.
        取得使用者的所有快照資料 (DataFrame)。
        """
        with self.engine.connect() as conn:
            where_clause = "WHERE user_id = :uid"
            params = {"uid": user_id, "aid": account_id or ""}
            where_clause += " AND account_id = :aid"
                
            query = text(f"SELECT * FROM daily_snapshots {where_clause} ORDER BY date ASC")
            return pd.read_sql(query, conn, params=params)

    def get_latest_by_user(self, user_id: str, account_id: str = None) -> Optional[Union[pd.Series, Dict[str, Any]]]:
        """
        Get the latest snapshot for a user.
        取得使用者的最新快照。
        """
        with self.engine.connect() as conn:
            where_clause = "WHERE user_id = :uid"
            params = {"uid": user_id, "aid": account_id or ""}
            where_clause += " AND account_id = :aid"

            query = text(f"SELECT * FROM daily_snapshots {where_clause} ORDER BY date DESC LIMIT 1")
            df = pd.read_sql(query, conn, params=params)
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
        leverage_ratio: float,
        conviction_level: float = 0.0,
        time_horizon: Optional[str] = None,
        account_id: str = None
    ) -> None:
        """
        Save or update a daily snapshot.
        儲存或更新每日快照。
        """
        # Prepare params
        # v4.1.1 Patch: Sanitize inf/nan for Postgres NUMERIC compatibility
        import math
        def sanitize(v):
            if v is None or (isinstance(v, float) and (math.isinf(v) or math.isnan(v))):
                return 0.0
            return v

        params = {
            "date": date,
            "user_id": user_id,
            "account_id": account_id or "",  # Normalize None to empty string
            "nlv": sanitize(nlv),
            "cash_balance": sanitize(cash_balance),
            "invested_capital": sanitize(invested_capital),
            "pnl": sanitize(pnl),
            "tnv": sanitize(total_tnv),
            "lev": sanitize(leverage_ratio),
            "conv": sanitize(conviction_level),
            "horizon": time_horizon
        }

        with self.engine.begin() as conn:
            try:
                # 1. Try Update (Compatible with both SQLite and Postgres)
                update_sql = text('''
                    UPDATE daily_snapshots SET
                        total_nlv = :nlv,
                        cash_balance = :cash_balance,
                        invested_capital = :invested_capital,
                        pnl = :pnl,
                        total_tnv = :tnv,
                        leverage_ratio = :lev,
                        conviction_level = :conv,
                        time_horizon = :horizon
                    WHERE date = :date AND user_id = :user_id AND account_id = :account_id
                ''')
                res = conn.execute(update_sql, params)
                
                # 2. If no rows updated, Insert
                if res.rowcount == 0:
                    insert_sql = text('''
                        INSERT INTO daily_snapshots (
                            date, user_id, account_id, total_nlv, cash_balance, invested_capital, 
                            pnl, total_tnv, leverage_ratio, conviction_level, time_horizon
                        )
                        VALUES (
                            :date, :user_id, :account_id, :nlv, :cash_balance, :invested_capital, 
                            :pnl, :tnv, :lev, :conv, :horizon
                        )
                    ''')
                    conn.execute(insert_sql, params)
            except Exception as e:
                print(f"\n[CRITICAL SQL ERROR] {e}")
                # self.logger.error if available, but for now standard print is used above
                raise e

# Legacy aliases removed in v4.1.7
# @deprecated: Use AlchemySnapshotRepository
