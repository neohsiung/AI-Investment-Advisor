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

        # 1. Fetch Transactions (Historical)
        transactions_df = self.transaction_service.get_transactions(user_id)
        
        # 2. Fetch Aggregated Live Data (Unified Portfolio)
        from src.services.portfolio_aggregator_service import PortfolioAggregatorService
        aggregator = PortfolioAggregatorService(user_id)
        live_portfolio = aggregator.get_aggregated_portfolio()
        
        # 3. Identify Active Tickers
        # Use live positions if available, else fallback to transaction-derived
        active_tickers = []
        live_positions = live_portfolio.get('positions', [])
        
        if live_positions:
            active_tickers = [p.symbol for p in live_positions]
        elif not transactions_df.empty:
            # Fallback
            holdings = transactions_df.copy()
            holdings['qty_signed'] = holdings.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
            active_holdings = holdings.groupby('ticker')['qty_signed'].sum()
            active_tickers = active_holdings[active_holdings > 0.0001].index.tolist()

        # 4. Fetch Prices
        current_prices = {}
        if active_tickers:
            current_prices = self._fetch_market_prices(active_tickers)

        # 5. Calculate Core Metrics
        metrics = {'nlv': 0, 'leveraged_value': 0, 'cash': 0, 'leverage_ratio': 0, 'cash_balance': 0}
        pnl_data = {'unrealized': 0, 'realized': 0, 'total': 0}
        roi = 0

        try:
            # Calculate basics
            metrics_derived = self.calc.calculate_metrics(current_prices, user_id=user_id)
            pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
            
            # OVERRIDE with Real-time Data if available
            if live_portfolio['total_equity'] > 0:
                 metrics['nlv'] = live_portfolio['total_equity']
                 metrics['cash_balance'] = live_portfolio['total_cash']
                 # Recalculate leverage if needed, or use derived
                 # metrics['leverage_ratio'] = ... 
                 metrics['leverage_ratio'] = metrics_derived.get('leverage_ratio', 0) # Keep derived for now or recalc
            else:
                 metrics = metrics_derived

            roi = self.roi_engine.calculate_roi(metrics['nlv'], user_id=user_id)
        except Exception as e:
            st.error(f"指標計算錯誤: {e}")

        # 6. Prepare Positions DataFrame
        positions_df = pd.DataFrame()
        if live_positions:
             # Convert live positions to DF
             data = []
             for p in live_positions:
                 data.append({
                     'ticker': p.symbol,
                     'quantity': p.quantity,
                     'current_price': p.current_price or current_prices.get(p.symbol, 0),
                     'market_value': p.market_value,
                     'unrealized_pnl': p.unrealized_pnl
                 })
             positions_df = pd.DataFrame(data)
        elif not transactions_df.empty:
             # Fallback to derived
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
            'positions_df': positions_df,
            'broker_breakdown': live_portfolio.get('broker_breakdown', {})
        }
