import streamlit as st
from src.services.analytics_service import AnalyticsService
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.services.market_data_service import MarketDataService

class PerformanceService:
    """Service for orchestrating portfolio performance data fetching and analysis."""
    
    def __init__(self, db_path="data/portfolio.db", user_id=None):
        self.db_path = db_path
        self.user_id = user_id
        self.analytics_service = AnalyticsService(db_path=db_path, user_id=user_id)
        self.market_service = MarketDataService()
        self.trans_repo = SqliteTransactionRepository()

    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch_prices(_self, tickers):
        """Internal helper to fetch market prices with caching."""
        return _self.market_service.get_current_prices(tickers)

    def prepare_performance_data(self):
        """Fetch all data needed for the performance page."""
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
