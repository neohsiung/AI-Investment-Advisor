import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Optional
from src.services.analytics_service import AnalyticsService
from src.repositories.transaction_repository import AlchemyTransactionRepository
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
        self.trans_repo = AlchemyTransactionRepository()

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
        
        # 確保 pnl_data 不為 None
        if pnl_data is None:
            pnl_data = {'realized': 0, 'unrealized': 0, 'total': 0, 'details': {}}

        # 3. Get performance history
        history_df = self.analytics_service.get_performance_history()
        
        # 確保 history_df 不為 None
        if history_df is None:
            import pandas as pd
            history_df = pd.DataFrame()

        return {
            'pnl_data': pnl_data,
            'history_df': history_df,
            'current_prices': current_prices,
            'active_tickers': active_tickers
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
            
            # Fetch current prices for all tickers in recommendations
            unique_tickers = df['ticker'].unique().tolist()
            current_prices = self.market_service.get_current_prices(unique_tickers)
            
            # Function to determine if a signal was correct
            def check_accuracy(row):
                ticker = row['ticker']
                signal = str(row['signal']).upper()
                price_at_signal = row['price_at_signal']
                current_price = current_prices.get(ticker)
                
                if current_price is None or price_at_signal is None or price_at_signal == 0:
                    return None
                
                if signal == 'BUY':
                    return 1 if current_price > price_at_signal else 0
                elif signal == 'SELL':
                    return 1 if current_price < price_at_signal else 0
                return None

            df['is_correct'] = df.apply(check_accuracy, axis=1)
            
            # Calculate accuracy per agent
            # Filter rows where correctness could be determined
            valid_df = df[df['is_correct'].notnull()]
            if valid_df.empty:
                stats = df.groupby('agent').size().reset_index(name='recommendation_count')
                stats['accuracy'] = 0.0
                return stats.to_dict('records')
            
            stats = valid_df.groupby('agent').agg(
                recommendation_count=('id', 'count'),
                correct_count=('is_correct', 'sum')
            ).reset_index()
            
            stats['accuracy'] = (stats['correct_count'] / stats['recommendation_count']) * 100
            
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

