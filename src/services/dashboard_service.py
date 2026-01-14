import streamlit as st
import pandas as pd
from src.services.analytics_service import LeverageCalculator, ROIEngine, update_daily_snapshot, PnLCalculator
from src.services.market_data_service import MarketDataService
from src.services.transaction_service import TransactionService
from src.repositories.transaction_repository import SqliteTransactionRepository

class DashboardService:
    """Service for orchestrating dashboard data fetching and calculations."""
    
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path
        self.transaction_repo = SqliteTransactionRepository()
        self.transaction_service = TransactionService(repository=self.transaction_repo)
        self.market_service = MarketDataService()
        
        # Analytics Engines
        self.calc = LeverageCalculator(db_path=self.db_path)
        self.roi_engine = ROIEngine(db_path=self.db_path)
        self.pnl_calc = PnLCalculator(db_path=self.db_path)

    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch_market_prices(_self, tickers):
        """Internal helper to fetch market prices with caching."""
        service = MarketDataService()
        prices = service.get_current_prices(tickers)
        
        # Hardcode USD if present (Cash/Currency)
        if "USD" in tickers:
            prices["USD"] = 1.0
            
        return prices

    def prepare_dashboard_data(self, user_id):
        """Fetch transactions, prices, and calculate all dashboard metrics."""
        # 0. Update snapshot
        update_daily_snapshot(self.db_path, user_id=user_id)

        # 1. Fetch Transactions
        transactions_df = self.transaction_service.get_transactions(user_id)
        
        # 2. Identify Active Tickers
        active_tickers = []
        if not transactions_df.empty:
            holdings = transactions_df.copy()
            holdings['qty_signed'] = holdings.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
            active_holdings = holdings.groupby('ticker')['qty_signed'].sum()
            active_tickers = active_holdings[active_holdings > 0.0001].index.tolist()

        # 3. Fetch Prices
        current_prices = {}
        if active_tickers:
            current_prices = self._fetch_market_prices(active_tickers)

        # 4. Calculate Core Metrics
        metrics = {'nlv': 0, 'leveraged_value': 0, 'cash': 0, 'leverage_ratio': 0, 'cash_balance': 0}
        pnl_data = {'unrealized': 0, 'realized': 0, 'total': 0}
        roi = 0

        try:
            metrics = self.calc.calculate_metrics(current_prices, user_id=user_id)
            pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
            roi = self.roi_engine.calculate_roi(metrics['nlv'], user_id=user_id)
        except Exception as e:
            # We log error but return defaults to prevent page crash
            st.error(f"指標計算錯誤: {e}")

        # 5. Prepare Positions
        positions_df = pd.DataFrame()
        if not transactions_df.empty:
            positions_raw = transactions_df.copy()
            positions_raw['qty_signed'] = positions_raw.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
            positions_grouped = positions_raw.groupby('ticker')['qty_signed'].sum().reset_index()
            positions_df = positions_grouped[positions_grouped['qty_signed'] > 0.0001].rename(columns={'qty_signed': 'quantity'})

            if not positions_df.empty:
                positions_df['current_price'] = positions_df['ticker'].map(current_prices).fillna(0)
                positions_df['market_value'] = positions_df['quantity'] * positions_df['current_price']

        return {
            'transactions_df': transactions_df,
            'current_prices': current_prices,
            'metrics': metrics,
            'pnl_data': pnl_data,
            'roi': roi,
            'positions_df': positions_df
        }
