import pandas as pd
from typing import List, Dict, Any, Optional
from src.utils.logger import setup_logger

# Providers
from src.data.providers.base import MarketDataProvider
from src.data.providers.polygon_provider import PolygonProvider
from src.data.providers.fmp_provider import FMPProvider
from src.data.providers.yfinance_provider import YFinanceProvider
from src.services.fred_service import FredService

class MarketDataService:
    def __init__(self):
        self.logger = setup_logger("MarketDataService")
        
        # Initialize Providers
        self.polygon = PolygonProvider()
        self.fmp = FMPProvider()
        self.yfinance = YFinanceProvider()
        
        # Initialize FRED (Macro Primary)
        try:
            self.fred = FredService()
        except Exception:
            self.fred = None
            self.logger.warning("FRED Service init failed, macro data will be limited.")
        
        # Priority Order (Primary -> Backup -> Fallback)
        self.providers: List[MarketDataProvider] = [
            self.polygon,
            self.fmp,
            self.yfinance
        ]

    def _get_provider_name(self, provider):
        return provider.__class__.__name__

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Get current prices with failover.
        """
        if not tickers: return {}
        
        for provider in self.providers:
            try:
                # Specific logic: Polygon might fail if no key, skip?
                # The provider itself handles missing keys by logging warning and returning empty.
                prices = provider.fetch_current_prices(tickers)
                if prices:
                    # Check if we got all tickers? Or at least some?
                    # For now, if we got > 0 prices, return.
                    # Ideally we merge results if partial.
                    self.logger.info(f"Fetched prices from {self._get_provider_name(provider)}")
                    return prices
            except Exception as e:
                self.logger.warning(f"Provider {self._get_provider_name(provider)} failed for prices: {e}")
        
        return {}

    def get_market_context(self, tickers: List[str]):
        """
        Get detailed context (OHLCV + Indicators).
        """
        context = {}
        for ticker in tickers:
            indicators = self.get_technical_indicators(ticker)
            ohlcv = self.get_ohlcv(ticker)
            
            # Note: The original Search fallback is simplified here or removed.
            # We rely on our 3 layers of providers.
            
            context[ticker] = {
                "price_data": ohlcv,
                "indicators": indicators
            }
        return context

    def get_ohlcv(self, ticker: str, days=30) -> Dict[str, List]:
        """
        Get OHLCV History.
        """
        # History is tricky: Polygon API is different from YF.
        # For v3.2 MVP, we default to YFinance for history as it is free and reliable for daily timeframe.
        # Polygon/FMP history implementation is a TODO optimization.
        # We manually prioritize YFinance for history for now, or just iterate.
        
        # Override Priority for History: YFinance -> Polygon -> FMP
        # (Since YFinance implementation is most robust in our current code)
        history_providers = [self.yfinance, self.polygon, self.fmp] 
        
        for provider in history_providers:
            try:
                df = provider.fetch_history(ticker, days=days)
                if not df.empty:
                    # Ensure format
                    df = df.tail(days)
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
                 self.logger.warning(f"History fetch failed on {self._get_provider_name(provider)}: {e}")
        return {}

    def get_technical_indicators(self, ticker: str) -> Dict[str, Any]:
        """
        Calculate indicators. Relies on fetch_history (defaulting to YFinance).
        """
        try:
            # We use self.get_ohlcv methodology but need DataFrame.
            # So we call fetch_history on YFinance directly or iterate.
            
            df = pd.DataFrame()
            # Prioritize YFinance for indicators base data
            for provider in [self.yfinance, self.polygon]:
                df = provider.fetch_history(ticker, period="1y")
                if not df.empty: break
            
            if df.empty or len(df) < 26:
                return {"rsi": 50, "macd": "neutral", "sma": {}, "volume": {}}

            close = df['Close']
            if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
            
            volume = df['Volume']
            if isinstance(volume, pd.DataFrame): volume = volume.iloc[:, 0]

            # Indicators Logic (Same as before)
            sma_20 = close.rolling(window=20).mean().iloc[-1]
            sma_50 = close.rolling(window=50).mean().iloc[-1]
            sma_200 = close.rolling(window=200).mean().iloc[-1]

            current_vol = volume.iloc[-1]
            avg_vol_20 = volume.rolling(window=20).mean().iloc[-1]

            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

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
            self.logger.error(f"Indicator calc error for {ticker}: {e}")
            return {"rsi": 50, "macd": "neutral", "sma": {}, "volume": {}}

    def get_news(self, ticker: str) -> List[str]:
        """
        Get News using Strategy: FMP -> YFinance -> Polygon
        """
        # News Strategy: FMP is best for Financial News
        news_providers = [self.fmp, self.yfinance, self.polygon]
        
        all_news = []
        for provider in news_providers:
            try:
                news = provider.fetch_news(ticker, limit=5)
                if news:
                    # Format to strings
                    for n in news:
                        title = n.get('title', 'No Title')
                        link = n.get('link', '#')
                        all_news.append(f"{title} ({link})")
                    
                    if len(all_news) >= 5: break
            except Exception as e:
                 self.logger.warning(f"News fetch failed on {self._get_provider_name(provider)}")
        
        return all_news[:5]

    def get_financials(self, ticker: str) -> Dict[str, Any]:
        """
        Get Fundamentals. Preferred: FMP -> YFinance
        """
        fund_providers = [self.fmp, self.yfinance, self.polygon]
        
        for provider in fund_providers:
            try:
                info = provider.fetch_info(ticker)
                if info and info.get('market_cap'): # Basic validation
                     # Normalize keys if needed, but for now we expect mostly common keys
                     return info
            except Exception:
                continue
        return {}

    def get_macro_data(self):
        """
        Get Macro Data. Priority: FRED -> YFinance
        """
        macro_data = {}
        
        # 1. Try FRED (Primary)
        try:
            if self.fred:
                fred_data = self.fred.get_macro_indicators()
                if fred_data:
                    macro_data["economics"] = fred_data
                    self.logger.info("Fetched macro data from FRED")
        except Exception as e:
            self.logger.warning(f"FRED fetch failed: {e}")

        # 2. Try YFinance (Backup/Real-time Sentiment)
        try:
             tickers = ["^VIX", "^TNX", "SPY"]
             prices = self.yfinance.fetch_current_prices(tickers)
             if prices:
                 macro_data["market_indicators"] = prices
        except Exception as e:
             self.logger.error(f"YFinance Macro data error: {e}")
             
        return macro_data

    def get_yield_curve_inversion(self):
         """
         Legacy Logic using YFinance Provider History.
         TODO: Can also use FRED series 'T10Y2Y' directly if available.
         """
         # 1. Try FRED (Primary)
         try:
             if self.fred:
                 fred_data = self.fred.get_macro_indicators()
                 if "10Y2Y_Spread" in fred_data:
                     spread_val = fred_data["10Y2Y_Spread"]["value"]
                     return {
                         "spread": spread_val,
                         "inverted": spread_val < 0,
                         "desc": "10Y-2Y Spread (FRED)"
                     }
         except Exception as e:
             self.logger.warning(f"FRED yield curve fetch failed: {e}")

         # 2. Fallback to YFinance
         try:
             # Fallback to YFinance 10Y - 3M (classic recession indicator)
             # Fetch 5d history
             df_tnx = self.yfinance.fetch_history("^TNX", period="5d")
             df_irx = self.yfinance.fetch_history("^IRX", period="5d")
             
             tnx = df_tnx['Close'].iloc[-1] if not df_tnx.empty else None
             irx = df_irx['Close'].iloc[-1] if not df_irx.empty else None
             
             if isinstance(tnx, pd.Series): tnx = tnx.item()
             if isinstance(irx, pd.Series): irx = irx.item()

             if tnx is not None and irx is not None:
                 spread = float(tnx) - float(irx)
                 return {
                     "spread": round(spread, 2),
                     "inverted": spread < 0,
                     "10y": round(float(tnx), 2),
                     "3m": round(float(irx), 2),
                     "desc": "10Y-3M Spread (Yahoo)"
                 }
             return {}
         except Exception as e:
             self.logger.error(f"Yield curve error: {e}")
             return {}

