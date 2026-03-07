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
    def _fetch_market_prices(_self, tickers: List[str], user_id: str = None) -> Dict[str, float]:
        """
        Internal helper to fetch market prices with caching.
        內部輔助方法：獲取帶快取的市場價格。
        """
        service = MarketDataService(user_id=user_id)
        prices = service.get_current_prices(tickers)
        
        # Hardcode USD if present (Cash/Currency)
        if "USD" in tickers:
            prices["USD"] = 1.0
            
        return prices

    @st.cache_data(ttl=60, show_spinner=False)
    def prepare_dashboard_data(_self, user_id: str) -> Dict[str, Any]:
        """
        Fetch transactions, prices, and calculate all dashboard metrics for the user.
        獲取交易、價格並為使用者計算所有儀表板指標。
        """
        # 1. Identify Active Tickers First
        from src.services.portfolio_aggregator_service import PortfolioAggregatorService
        aggregator = PortfolioAggregatorService(user_id)
        live_portfolio = aggregator.get_aggregated_portfolio()
        
        active_tickers = []
        live_positions = live_portfolio.get('positions', [])
        
        if live_positions:
            active_tickers = [p.symbol for p in live_positions]
        else:
            # Fallback to transactions if no live positions
            transactions_df = _self.transaction_service.get_transactions(user_id)
            if not transactions_df.empty:
                holdings = transactions_df.copy()
                holdings['qty_signed'] = holdings.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
                active_holdings = holdings.groupby('ticker')['qty_signed'].sum()
                active_tickers = active_holdings[active_holdings > 0.0001].index.tolist()
        
        # 2. Fetch Prices ONCE
        current_prices = {}
        if active_tickers:
            current_prices = _self._fetch_market_prices(active_tickers, user_id=user_id)
            
            # price resilience fix
            if live_positions:
                for p in live_positions:
                    ticker = getattr(p, 'symbol', None)
                    if ticker and (ticker not in current_prices or current_prices[ticker] == 0):
                        current_prices[ticker] = getattr(p, 'current_price', 0)

        # 3. Update snapshot WITH pre-fetched prices (Eliminates redundant fetch inside update_daily_snapshot)
        update_daily_snapshot(_self.db_path, user_id=user_id, current_prices=current_prices)

        # 4. Fetch Transactions for other UI needs
        transactions_df = _self.transaction_service.get_transactions(user_id)

        # 5. Calculate Core Metrics using the same prices
        metrics = {'nlv': 0, 'leveraged_value': 0, 'cash': 0, 'leverage_ratio': 0, 'cash_balance': 0}
        pnl_data = {'unrealized': 0, 'realized': 0, 'total': 0}
        roi = 0.0

        try:
            # Calculate all metrics based on DB positions + Real-time Market Prices
            metrics_derived = _self.calc.calculate_metrics(current_prices, user_id=user_id)
            pnl_data = _self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
            
            # Use derived metrics exclusively to ensure consistency with DB anchors
            metrics = metrics_derived
            
            # v4.2.3: Use the repository's authoritative "Net Invested Capital" (Deposits - Withdrawals)
            metrics['invested_capital'] = _self.transaction_repo.calculate_net_invested_capital(user_id)
            metrics['unrealized_pnl'] = pnl_data.get('unrealized', 0)
            
            # Global Profit is anchored to NLV - Net Invested Capital
            pnl_data['total'] = metrics['nlv'] - metrics['invested_capital']
            pnl_data['realized'] = pnl_data['total'] - pnl_data['unrealized']

            # Gross Exposure = Total Nominal Assets + Uninvested Cash
            metrics['gross_nlv'] = metrics_derived['tnv'] + metrics_derived['cash_balance']

            roi = _self.roi_engine.calculate_roi(metrics['nlv'], user_id=user_id)
        except Exception as e:
            st.error(f"指標計算錯誤: {e}")
            logger.error(f"Metric calculation failed: {e}")

        # 6. Prepare Positions DataFrame
        positions_df = pd.DataFrame()
        if live_positions:
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
            positions_raw = transactions_df.copy()
            positions_raw['qty_signed'] = positions_raw.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
            positions_grouped = positions_raw.groupby('ticker')['qty_signed'].sum().reset_index()
            positions_df = positions_grouped[positions_grouped['qty_signed'] > 0.0001].rename(columns={'qty_signed': 'quantity'})

            if not positions_df.empty:
                positions_df['current_price'] = positions_df['ticker'].map(current_prices).fillna(0)
                positions_df['gross_mv'] = positions_df['quantity'] * positions_df['current_price']
                positions_df['loan'] = 0.0
                positions_df['net_equity'] = positions_df['gross_mv']
                positions_df['leverage'] = 1.0

        return {
            'transactions_df': transactions_df,
            'current_prices': current_prices,
            'metrics': metrics,
            'pnl_data': pnl_data,
            'roi': roi,
            'positions_df': positions_df,
            'broker_breakdown': live_portfolio.get('broker_breakdown', {})
        }
