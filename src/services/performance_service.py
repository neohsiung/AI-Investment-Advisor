import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
        self.market_service = MarketDataService(user_id=user_id)
        self.trans_repo = AlchemyTransactionRepository()

    def _fetch_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Internal helper to fetch market prices with caching.
        內部輔助方法：獲取帶快取的市場價格。
        """
        return _self.market_service.get_current_prices(tickers)

    def prepare_performance_data(self, account_id: str = None) -> Dict[str, Any]:
        """
        Fetch all data needed for the performance page.
        獲取績效頁面所需的所有數據。
        """
        # 1. Fetch active tickers and prices
        active_tickers = self.trans_repo.get_active_tickers(self.user_id, account_id)
        current_prices = self._fetch_prices(active_tickers) if active_tickers else {}

        # 2. Trigger snapshot update with pre-fetched prices (Aggregated or Specific)
        # Note: update_daily_snapshot might need refinement to support per-account storage if we want persistent per-account records.
        # For now, we mainly rely on history reconstruction for accuracy.
        self.analytics_service.trigger_snapshot_update(current_prices=current_prices, account_id=account_id)
        pnl_data = self.analytics_service.get_pnl_breakdown(current_prices, account_id)
        
        # 確保 pnl_data 不為 None
        if pnl_data is None:
            pnl_data = {'realized': 0, 'unrealized': 0, 'total': 0, 'details': {}}

        # 3. Get performance history (History-First Reconstruction)
        history_df = _self.reconstruct_history(_self.user_id, account_id)
        
        # 確保 history_df 不為 None
        if history_df is None:
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
        from src.data.database import get_db_engine
        from sqlalchemy import text

        rec_id = str(uuid.uuid4())
        date_str = format_time() # YYYY-MM-DD HH:MM:SS

        try:
            engine = get_db_engine(self.db_path)
            with engine.begin() as conn:
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
        except Exception as e:
            # Prevent blocking operations if logging fails
            print(f"Error recording recommendation: {e}")

    def get_agent_performance(self) -> List[Dict[str, Any]]:
        """
        Calculate performance stats for each agent based on recommendation history.
        計算每個 Agent 根據歷史推薦的績效統計。
        """
        from src.data.database import get_db_engine
        from sqlalchemy import text
        import pandas as pd
        
        try:
            engine = get_db_engine(self.db_path)
            with engine.connect() as conn:
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

    def reconstruct_history(self, user_id: str, account_id: str = None) -> pd.DataFrame:
        """
        Reconstruct performance history from the transaction ledger.
        從交易帳本重建績效歷史。
        """
        from datetime import datetime, timedelta
        
        # 1. Fetch all relevant transactions
        transactions = self.trans_repo.get_all_by_user_df(user_id, account_id)
        if transactions.empty:
            return pd.DataFrame()
        
        # 確保 trade_date 為 datetime
        transactions['trade_date'] = pd.to_datetime(transactions['trade_date'])
        transactions = transactions.sort_values('trade_date')
        
        # 2. Find date range
        start_date = transactions['trade_date'].min().date()
        end_date = datetime.now().date()
        date_range = pd.date_range(start=start_date, end=end_date)
        
        # 3. Prepare historical prices
        unique_tickers = transactions[transactions['ticker'].str.len() > 0]['ticker'].unique().tolist()
        # Filter out special tickers
        tickers_to_fetch = [t for t in unique_tickers if t not in ['CASH', 'STABILIZE_CASH', 'STABILIZE_CAP', 'ETORO_SYNC'] and not t.startswith('__ANCHOR_')]
        
        # Fetch batches of history (e.g., last 365 days or since start_date)
        days_diff = (end_date - start_date).days + 1
        hist_prices_batch = self.market_service.get_ohlcv_batch(tickers_to_fetch, days=days_diff)
        
        # Pre-process batch results into DataFrames for compatibility with legacy logic
        for ticker in list(hist_prices_batch.keys()):
            data = hist_prices_batch[ticker]
            if isinstance(data, dict) and "close" in data:
                df = pd.DataFrame(data)
                # Map lowercase keys from MarketDataService to Uppercase columns for legacy logic consistency
                column_map = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}
                df.rename(columns={k: v for k, v in column_map.items() if k in df.columns}, inplace=True)
                
                if "date" in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                hist_prices_batch[ticker] = df
        
        # 4. Iterative Reconstruction
        history = []
        current_holdings = {} # {ticker: qty}
        current_costs = {}    # {ticker: total_cost}
        current_lev_qty = {}  # {ticker: qty * leverage} for weighted average leverage
        current_cash = 0.0
        current_invested = 0.0
        
        # Sort transactions for easier processing
        trans_grouped = transactions.groupby('trade_date')
        
        for curr_dt in date_range:
            curr_date_str = curr_dt.strftime('%Y-%m-%d')
            
            # Update with transactions of the day
            if curr_dt in trans_grouped.groups:
                day_trans = trans_grouped.get_group(curr_dt)
                for _, row in day_trans.iterrows():
                    ticker = row['ticker']
                    action = row['action']
                    qty = row['quantity']
                    price = row['price']
                    fees = row['fees']
                    amount = row['amount']
                    leverage = row.get('leverage', 1.0) or 1.0
                    
                    if action == 'BUY':
                        current_holdings[ticker] = current_holdings.get(ticker, 0.0) + qty
                        current_costs[ticker] = current_costs.get(ticker, 0.0) + (qty * price) + fees
                        current_lev_qty[ticker] = current_lev_qty.get(ticker, 0.0) + (qty * leverage)
                        current_cash -= ((qty * price) / leverage) + fees
                    elif action == 'SELL':
                        if ticker in current_holdings and current_holdings[ticker] > 0:
                            ratio = qty / current_holdings[ticker]
                            current_costs[ticker] *= (1 - ratio)
                            current_lev_qty[ticker] *= (1 - ratio)
                            current_holdings[ticker] -= qty
                        current_cash += amount
                    elif action == 'DEPOSIT':
                        if ticker not in ['CASH', 'STABILIZE_CASH', 'STABILIZE_CAP', 'ETORO_SYNC']:
                            current_invested += amount
                        current_cash += amount
                    elif action == 'WITHDRAWAL':
                        if ticker not in ['CASH', 'STABILIZE_CASH', 'STABILIZE_CAP', 'ETORO_SYNC']:
                            current_invested -= amount
                        current_cash -= amount
                    elif action == 'DIVIDEND':
                        current_cash += amount
                    elif action in ['FEE', 'TAX']:
                        current_cash -= amount
            
            # Calculate Portfolio Value for this day
            portfolio_val = 0.0
            for ticker, qty in current_holdings.items():
                if qty <= 0.0001: continue
                # Get price for this date
                price = 0.0
                if ticker in hist_prices_batch:
                    ticker_hist = hist_prices_batch[ticker]
                    # Find closest date <= curr_date
                    if not ticker_hist.empty:
                        # Ensure index is datetime
                        if not isinstance(ticker_hist.index, pd.DatetimeIndex):
                            ticker_hist.index = pd.to_datetime(ticker_hist.index)
                        
                        available_prices = ticker_hist[ticker_hist.index <= curr_dt]
                        if not available_prices.empty:
                            price = available_prices.iloc[-1]['Close']
                
                # Fallback to cost if no price found (for anchors or missing data)
                if price == 0 and ticker in current_costs:
                    price = current_costs[ticker] / current_holdings[ticker] if current_holdings[ticker] > 0 else 0
                
                # [FIX] Account for leverage in NLV (Equity = Nominal / Leverage)
                # Weighted Average Leverage = current_lev_qty / current_holdings
                ticker_lev = 1.0
                if ticker in current_lev_qty and qty > 0:
                    ticker_lev = current_lev_qty[ticker] / qty
                
                equity = (qty * price) / ticker_lev
                portfolio_val += equity
            
            nlv = current_cash + portfolio_val
            pnl = nlv - current_invested
            
            history.append({
                'date': curr_date_str,
                'total_nlv': nlv,
                'cash_balance': current_cash,
                'invested_capital': current_invested,
                'pnl': pnl
            })
            
        return pd.DataFrame(history)

