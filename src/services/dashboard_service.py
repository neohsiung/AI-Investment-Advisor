import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Optional, Union
from src.services.analytics_service import LeverageCalculator, ROIEngine, update_daily_snapshot, PnLCalculator
from src.services.market_data_service import MarketDataService
from src.services.transaction_service import TransactionService
from src.repositories.transaction_repository import AlchemyTransactionRepository

class DashboardService:
    """
    Service for orchestrating dashboard data fetching and calculations.
    協調儀表板數據獲取與計算的服務。
    """
    
    def __init__(self, db_path: str = None):
        """
        Initialize the dashboard service.
        初始化儀表板服務。
        """
        self.db_path = db_path  # None will use environment DB_URL or DB_TYPE
        self.transaction_repo = AlchemyTransactionRepository()
        self.transaction_service = TransactionService(repository=self.transaction_repo)
        self.market_service = MarketDataService()
        
        # Analytics Engines
        self.calc = LeverageCalculator(db_path=self.db_path)
        self.roi_engine = ROIEngine(db_path=self.db_path)
        self.pnl_calc = PnLCalculator(db_path=self.db_path)

    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch_market_prices(_self, tickers: List[str]) -> Dict[str, float]:
        """
        Internal helper to fetch market prices with caching.
        內部輔助方法：獲取帶快取的市場價格。
        """
        service = MarketDataService()
        prices = service.get_current_prices(tickers)
        
        # Hardcode USD if present (Cash/Currency)
        if "USD" in tickers:
            prices["USD"] = 1.0
            
        return prices

    def prepare_dashboard_data(self, user_id: str) -> Dict[str, Any]:
        """
        Fetch transactions, prices, and calculate all dashboard metrics for the user.
        獲取交易、價格並為使用者計算所有儀表板指標。
        """
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
            
            # v4.2.3: Price Resilience Fix
            # If APIs fail, fallback to prices reported by the Broker in live_portfolio
            if live_positions:
                for p in live_positions:
                    ticker = getattr(p, 'symbol', None)
                    if ticker and (ticker not in current_prices or current_prices[ticker] == 0):
                        current_prices[ticker] = getattr(p, 'current_price', 0)

        # 5. Calculate Core Metrics
        metrics = {'nlv': 0, 'leveraged_value': 0, 'cash': 0, 'leverage_ratio': 0, 'cash_balance': 0}
        pnl_data = {'unrealized': 0, 'realized': 0, 'total': 0}
        roi = 0.0

        try:
            # Calculate basics
            metrics_derived = self.calc.calculate_metrics(current_prices, user_id=user_id)
            pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
            
            # OVERRIDE with Real-time Data if available
            if live_portfolio.get('total_equity', 0) > 0:
                 # v4.2.3: Standardized Metrics Alignment (Follows Core-Metrics-Specs)
                 # NLV = Database Cash + (Invested Capital + Unrealized P&L)
                 metrics['cash_balance'] = metrics_derived.get('cash_balance', 0)
                 metrics['invested_capital'] = pnl_data.get('margin_invested', pnl_data.get('invested_capital', 0))
                 metrics['unrealized_pnl'] = pnl_data.get('unrealized', 0)
                 
                 # Target NLV = Cash + Invested + Unrealized
                 metrics['nlv'] = metrics['cash_balance'] + metrics['invested_capital'] + metrics['unrealized_pnl']
                 
                 # Gross Exposure calculation based on CORE_METRICS_SPEC
                 # Gross = Cash + Nominal MV (Nominal MV already includes Unrealized P&L)
                 live_mv_nominal = 0.0
                 live_positions = live_portfolio.get('positions', [])
                 for p in live_positions:
                     price = current_prices.get(p.symbol, 0) or getattr(p, 'current_price', 0)
                     leverage = getattr(p, 'leverage', 1.0)
                     live_mv_nominal += (p.quantity * price) * leverage
                 
                 metrics['gross_nlv'] = metrics['cash_balance'] + live_mv_nominal
                 
                 if metrics['nlv'] > 0:
                     metrics['leverage_ratio'] = metrics['gross_nlv'] / metrics['nlv']
            else:
                 metrics = metrics_derived
                 metrics['gross_nlv'] = metrics['nlv'] # Fallback
                 metrics['invested_capital'] = pnl_data.get('margin_invested', pnl_data.get('invested_capital', 0))
                 metrics['unrealized_pnl'] = pnl_data.get('unrealized', 0)

            roi = self.roi_engine.calculate_roi(metrics['nlv'], user_id=user_id)
        except Exception as e:
            st.error(f"指標計算錯誤: {e}")

        # 6. Prepare Positions DataFrame
        positions_df = pd.DataFrame()
        if live_positions:
             # Convert live positions to DF
             data = []
             for p in live_positions:
                 price = current_prices.get(p.symbol, 0) or getattr(p, 'current_price', 0)
                 gross = p.quantity * price
                 loan = 0.0
                 if hasattr(p, 'leverage') and p.leverage > 1:
                     loan = getattr(p, 'market_value', 0) * (p.leverage - 1)
                 net_eq = gross - loan

                 data.append({
                      'ticker': p.symbol,
                      'quantity': p.quantity,
                      'current_price': price,
                      'leverage': getattr(p, 'leverage', 1.0),
                      'gross_mv': gross,
                      'loan': loan,
                      'net_equity': net_eq,
                      'unrealized_pnl': getattr(p, 'unrealized_pnl', 0.0)
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
                positions_df['gross_mv'] = positions_df['quantity'] * positions_df['current_price']
                # Also add loan and net_equity for consistent structure
                positions_df['loan'] = 0.0
                positions_df['net_equity'] = positions_df['gross_mv']
                positions_df['leverage'] = 1.0 # Added for fallback consistency

        return {
            'transactions_df': transactions_df,
            'current_prices': current_prices,
            'metrics': metrics,
            'pnl_data': pnl_data,
            'roi': roi,
            'positions_df': positions_df,
            'broker_breakdown': live_portfolio.get('broker_breakdown', {})
        }
