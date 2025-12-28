import pandas as pd
from datetime import datetime
from src.utils.logger import setup_logger

from src.repositories.market_data_repository import MarketDataRepository

class MarketDataService:
    def __init__(self, db_path=None, repository=None):
        self.logger = setup_logger("MarketData")
        self.repository = repository or MarketDataRepository()

    def get_current_prices(self, tickers):
        """
        Get current prices for a list of tickers.
        獲取一組 Tickers 的最新價格。
        
        Args:
            tickers (list): List of stock symbols.
            
        Returns:
            dict: {ticker: price}
        """
        if not tickers:
            return {}
        try:
            return self.repository.fetch_current_prices(tickers)
        except Exception as e:
            self.logger.error(f"Error fetching prices: {e}")
            return {}

    def get_market_context(self, tickers):
        """
        Get detailed market context (OHLCV + Indicators).
        獲取更詳細的市場數據 (用於 Agent Context)，包含價格數據 (OHLCV) 與技術指標。
        
        Args:
            tickers (list): List of stock symbols.
            
        Returns:
            dict: Nested dict with price_data and indicators for each ticker.
        """
        context = {}
        for ticker in tickers:
            indicators = self.get_technical_indicators(ticker)
            ohlcv = self.get_ohlcv(ticker)

            # AI Fallback: If no data, try to fetch via search (Simplified logic)
            # AI 備援機制：若無數據，嘗試透過搜尋獲取 (簡化邏辑)
            if not ohlcv:
                self.logger.warning(f"Missing data for {ticker}, attempting fallback...")
                ai_data = self._fetch_from_search(ticker)
                if ai_data:
                     # Map simple data if possible (目前僅回傳註記，不強行轉換數值以避免風險)
                     if 'price' in ai_data:
                         ohlcv = {"close": [ai_data['price']]} 
                     if 'indicators' in ai_data:
                        indicators.update(ai_data['indicators'])

            context[ticker] = {
                "price_data": ohlcv,
                "indicators": indicators
            }
        return context

    def get_ohlcv(self, ticker, days=30):
        """
        Get historical OHLCV data.
        獲取 OHLCV 歷史數據。
        
        Args:
            ticker (str): Symbol.
            days (int): Number of days to return.
            
        Returns:
            dict: Lists for open, high, low, close, volume, date.
        """
        try:
            df = self.repository.fetch_history(ticker, days=days)
            if df.empty:
                return {}
            
            # Keep only last 'days' (僅保留最近 N 天)
            df = df.tail(days)
            
            # Helper to extract list from Series or DataFrame
            def to_list(series):
                if isinstance(series, pd.DataFrame):
                    return series.iloc[:, 0].tolist()
                return series.tolist()

            return {
                "date": [d.strftime('%Y-%m-%d') for d in df.index],
                "open": to_list(df['Open']),
                "high": to_list(df['High']),
                "low": to_list(df['Low']),
                "close": to_list(df['Close']),
                "volume": to_list(df['Volume'])
            }
        except Exception as e:
            self.logger.error(f"Error fetching OHLCV for {ticker}: {e}")
            return {}

    def get_technical_indicators(self, ticker):
        """
        Calculate technical indicators (RSI, MACD, SMA).
        計算技術指標 (RSI, MACD, MA)。
        
        Args:
            ticker (str): Stock symbol.
            
        Returns:
            dict: Indicator values.
        """
        try:
            # Fetch 1y using repository (讀取一年數據計算指標)
            df = self.repository.fetch_history(ticker, period="1y")
            if df.empty or len(df) < 26:
                return {"rsi": 50, "macd": "neutral", "sma": {}, "volume": {}}

            close = df['Close']
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            
            # Volume
            volume = df['Volume']
            if isinstance(volume, pd.DataFrame):
                volume = volume.iloc[:, 0]
            
            # Simple Moving Averages (移動平均線)
            sma_20 = close.rolling(window=20).mean().iloc[-1]
            sma_50 = close.rolling(window=50).mean().iloc[-1]
            sma_200 = close.rolling(window=200).mean().iloc[-1]

            # Volume Metrics (成交量指標)
            current_vol = volume.iloc[-1]
            avg_vol_20 = volume.rolling(window=20).mean().iloc[-1]

            # RSI (14)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            # MACD (12, 26, 9)
            exp1 = close.ewm(span=12, adjust=False).mean()
            exp2 = close.ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()

            macd_val = macd.iloc[-1]
            signal_val = signal.iloc[-1]

            macd_status = "bullish" if macd_val > signal_val else "bearish"

            return {
                "rsi": round(float(current_rsi), 2) if pd.notna(current_rsi) else 50,
                "macd": macd_status,
                "macd_val": round(float(macd_val), 2) if pd.notna(macd_val) else 0,
                "sma": {
                    "sma_20": round(float(sma_20), 2) if pd.notna(sma_20) else 0,
                    "sma_50": round(float(sma_50), 2) if pd.notna(sma_50) else 0,
                    "sma_200": round(float(sma_200), 2) if pd.notna(sma_200) else 0
                },
                "volume": {
                    "current": int(current_vol) if pd.notna(current_vol) else 0,
                    "avg_20": int(avg_vol_20) if pd.notna(avg_vol_20) else 0
                }
            }

        except Exception as e:
            self.logger.error(f"Error calculating indicators for {ticker}: {e}")
            return {"rsi": 50, "macd": "neutral", "macd_val": 0, "sma": {}, "volume": {}}

    def get_news(self, ticker):
        """
        Fetch news for a ticker.
        獲取個股新聞。
        
        Args:
            ticker (str): Stock symbol.
            
        Returns:
            list: List of strings (Title - Link)
        """
        try:
            raw_news = self.repository.fetch_news(ticker, limit=5)
            formatted_news = []
            for n in raw_news:
                title = n.get('title', '')
                link = n.get('link', '')
                formatted_news.append(f"{title} ({link})")
            return formatted_news
        except Exception as e:
            self.logger.error(f"Error fetching news for {ticker}: {e}")
            return []

    def get_financials(self, ticker):
        """
        Fetch fundamental financial data.
        獲取基本面數據。
        
        Args:
            ticker (str): Stock symbol.
            
        Returns:
            dict: Fundamental data.
        """
        try:
            info = self.repository.fetch_info(ticker)

            return {
                "market_cap": info.get('marketCap'),
                "trailing_pe": info.get('trailingPE'),
                "forward_pe": info.get('forwardPE'),
                "eps": info.get('trailingEps'),
                "revenue_growth": info.get('revenueGrowth'),
                "profit_margins": info.get('profitMargins'),
                "sector": info.get('sector'),
                "industry": info.get('industry')
            }
        except Exception as e:
            self.logger.error(f"Error fetching financials for {ticker}: {e}")
            return {}

    def get_macro_data(self):
        """
        Fetch macro economic data (VIX, 10Y Yield, SPY).
        獲取總經數據 (VIX, 10Y Yield, SPY)。
        
        Returns:
            dict: {symbol: price}
        """
        try:
            tickers = ["^VIX", "^TNX", "SPY"]
            result = {}
            for t in tickers:
                 df = self.repository.fetch_history(t, period="5d")
                 if not df.empty and 'Close' in df.columns:
                     val = df['Close'].iloc[-1]
                     if isinstance(val, pd.Series): val = val.item()
                     result[t] = round(float(val), 2)
            return result
        except Exception as e:
            self.logger.error(f"Error fetching macro data: {e}")
            return {}

    def get_yield_curve_inversion(self):
        """
        Calculate if the US Yield Curve is inverted (10Y - 3M).
        計算美債殖利率曲線倒掛 (10Y - 3M)。
        
        Returns:
            dict: {spread, inverted, 10y, 3m}
        """
        try:
            # 1. Fetch 10Y (TNX)
            df_tnx = self.repository.fetch_history("^TNX", period="5d")
            tnx = None
            if not df_tnx.empty and 'Close' in df_tnx.columns:
                 val = df_tnx['Close'].iloc[-1]
                 if isinstance(val, pd.Series): val = val.item()
                 tnx = val

            # 2. Fetch 3M (IRX)
            df_irx = self.repository.fetch_history("^IRX", period="5d")
            irx = None
            if not df_irx.empty and 'Close' in df_irx.columns:
                val = df_irx['Close'].iloc[-1]
                if isinstance(val, pd.Series): val = val.item()
                irx = val

            if tnx is not None and irx is not None:
                spread = float(tnx) - float(irx)
                return {
                    "spread": round(spread, 2),
                    "inverted": spread < 0,
                    "10y": round(float(tnx), 2),
                    "3m": round(float(irx), 2),
                    "desc": "10Y-3M Spread"
                }
            return {}
        except Exception as e:
            self.logger.error(f"Error calculating yield curve: {e}")
            return {}

    def _fetch_from_search(self, ticker):
        """
        Fallback: Use Internet Search.
        備援：使用網路搜尋。
        
        Args:
            ticker (str): Stock symbol.
            
        Returns:
            dict or None: Search results or None if not found.
        """
        try:
            from src.services.search_service import InternetSearchService
            search_service = InternetSearchService()
            
            # 1. Try Search for Price
            query = f"{ticker} stock price today"
            results = search_service.search_financial_context(query, max_results=1)
            
            if results:
                snippet = results[0]['snippet']
                return {"note": "Price data missing, search found: " + snippet[:100]}
                
            return None
            
        except ImportError:
            self.logger.warning("SearchService not available.")
            return None
        except Exception as e:
            self.logger.error(f"Search fallback failed: {e}")
            return None
