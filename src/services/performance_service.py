import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Optional
from src.services.analytics_service import AnalyticsService
from src.repositories.transaction_repository import TransactionRepositoryImpl
from src.services.market_data_service import MarketDataService

class PerformanceService:
    """
    Service for orchestrating portfolio performance data fetching and analysis.
    協調投資組合績效數據獲取與分析的服務。
    """
    
    def __init__(self, db_path: str = None, user_id: str = None):
        """
        Initialize the performance service.
        初始化績效服務。
        """
        self.db_path = db_path
        self.user_id = user_id
        self.analytics_service = AnalyticsService(db_path=db_path, user_id=user_id)
        self.market_service = MarketDataService()
        self.trans_repo = TransactionRepositoryImpl()

    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch_prices(_self, tickers: List[str]) -> Dict[str, float]:
        """
        Internal helper to fetch market prices with caching.
        內部輔助方法：獲取帶快取的市場價格。
        """
        return _self.market_service.get_current_prices(tickers)

    def prepare_performance_data(self) -> Dict[str, Any]:
        """
        Fetch all data needed for the performance page.
        獲取績效頁面所需的所有數據。
        """
        # 1. Fetch active tickers and prices
        active_tickers = self.trans_repo.get_active_tickers(self.user_id)
        current_prices = self._fetch_prices(active_tickers) if active_tickers else {}

        # 2. Trigger snapshot update and get PnL
        self.analytics_service.trigger_snapshot_update()
        pnl_data = self.analytics_service.get_pnl_breakdown(current_prices)

        # 3. Get performance history
        history_df = self.analytics_service.get_performance_history()

        return {
            'pnl_data': pnl_data,
            'history_df': history_df
        }

    def record_recommendation(self, agent_name: str, ticker: str, signal: str, price: float) -> None:
        """
        Record an agent's recommendation for future performance tracking.
        記錄 Agent 的推薦以便未來追蹤績效。
        """
        import uuid
        from src.utils.time_utils import format_time
        from src.data.database import get_db_connection
        from sqlalchemy import text

        rec_id = str(uuid.uuid4())
        date_str = format_time() # YYYY-MM-DD HH:MM:SS

        try:
            with get_db_connection() as conn:
                query = text("""
                    INSERT INTO recommendations (id, user_id, date, agent, ticker, signal, price_at_signal)
                    VALUES (:id, :user_id, :date, :agent, :ticker, :signal, :price)
                """)
                conn.execute(query, {
                    "id": rec_id,
                    "user_id": self.user_id,
                    "date": date_str,
                    "agent": agent_name,
                    "ticker": ticker,
                    "signal": signal,
                    "price": price
                })
                conn.commit()
        except Exception as e:
            # Prevent blocking operations if logging fails
            print(f"Error recording recommendation: {e}")

    def get_agent_performance(self) -> List[Dict[str, Any]]:
        """
        Calculate performance stats for each agent based on recommendation history.
        計算每個 Agent 根據歷史推薦的績效統計。
        """
        from src.data.database import get_db_connection
        from sqlalchemy import text
        import pandas as pd
        
        try:
            with get_db_connection() as conn:
                # Fetch all recommendations
                query = text("SELECT * FROM recommendations WHERE user_id = :uid")
                df = pd.read_sql(query, conn, params={"uid": self.user_id})
                
            if df.empty:
                return []
            
            # TODO: Implement complex accuracy calculation (comparing signal price vs current/exit price)
            # For now, return a placeholder or simple count
            stats = df.groupby('agent').size().reset_index(name='count')
            return stats.to_dict('records')
            
        except Exception as e:
            print(f"Error calculating agent performance: {e}")
            return []
    
    def calculate_portfolio_alpha(self, portfolio_return: float, benchmark_return: float) -> float:
        """
        Calculate portfolio alpha (excess return over benchmark).
        計算投資組合的 Alpha 值 (超額報酬)。
        
        Args:
            portfolio_return: Portfolio return rate (e.g., 0.10 for 10%)
            benchmark_return: Benchmark return rate (e.g., 0.08 for 8%)
            
        Returns:
            Alpha value (excess return)
        """
        return portfolio_return - benchmark_return

