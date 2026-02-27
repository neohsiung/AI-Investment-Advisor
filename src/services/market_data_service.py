import pandas as pd
from typing import List, Dict, Any, Optional, Union
from datetime import date
from src.utils.logger import setup_logger

# Providers
from src.data.providers.base import MarketDataProvider
from src.data.providers.polygon_provider import PolygonProvider
from src.data.providers.tiingo_provider import TiingoProvider
from src.data.providers.fmp_provider import FMPProvider
from src.data.providers.yfinance_provider import YFinanceProvider
from src.data.providers.fred_provider import FredProvider
from src.data.providers.alpha_vantage_provider import AlphaVantageProvider
from src.data.providers.finnhub_provider import FinnhubProvider
from src.services.search_service import InternetSearchService
from src.services.settings_service import SettingsService

class MarketDataService:
    """
    Unified service for fetching market data from multiple providers.
    從多個提供者獲取市場數據的統一服務。
    """
    def __init__(self, user_id: Optional[str] = None, settings_service: Optional[SettingsService] = None):
        """
        Initialize the market data service.
        初始化市場數據服務。
        """
        self.logger = setup_logger("MarketDataService")
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        
        # Initialize Providers
        self.polygon = PolygonProvider(settings_service=self.settings_service)
        self.tiingo = TiingoProvider(settings_service=self.settings_service)
        self.fmp = FMPProvider(settings_service=self.settings_service)
        self.yfinance = YFinanceProvider()
        self.fred = FredProvider(user_id=self.user_id)
        self.alpha_vantage = AlphaVantageProvider(user_id=self.user_id)
        self.finnhub = FinnhubProvider(user_id=self.user_id)
        
        # Initialize Search (Tavily Primary, DuckDuckGo Fallback)
        self.search_service = InternetSearchService(settings_service=self.settings_service)
        
        # Priority Order (Primary -> Backup -> Fallback)
        # Optimized Order: Polygon (Unlimited) -> Tiingo (P1) -> Finnhub -> FMP -> AlphaVantage -> YFinance
        self.providers: List[MarketDataProvider] = [
            self.polygon,
            self.tiingo,
            self.finnhub,
            self.fmp,
            self.alpha_vantage,
            self.yfinance
        ]

    def _get_provider_name(self, provider: MarketDataProvider) -> str:
        """
        Helper to get the class name of a provider.
        獲取提供者類別名稱的輔助方法。
        """
        return provider.__class__.__name__

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Get current prices with failover and merging. Iterates providers until all tickers are resolved.
        獲取目前價格（含備援與合併）。遍歷提供者直到所有代號都解析完畢。
        """
        if not tickers: return {}
        
        all_prices = {}
        missing_tickers = list(tickers)
        
        # Priority: Polygon (Unlimited) -> FMP (300/min) -> YFinance (Free)
        for provider in [self.polygon, self.fmp, self.yfinance]:
            if not missing_tickers:
                break
                
            try:
                # Only request missing tickers
                prices = provider.fetch_current_prices(missing_tickers)
                if prices:
                    self.logger.info(f"Fetched {len(prices)} prices from {self._get_provider_name(provider)}")
                    
                    # VALIDATION: Only accept positive prices
                    valid_prices = {}
                    for k, v in prices.items():
                        if v > 0:
                            valid_prices[k] = v
                    
                    all_prices.update(valid_prices)
                    # Update missing list
                    missing_tickers = [t for t in tickers if t not in all_prices]
            except Exception as e:
                self.logger.warning(f"Provider {self._get_provider_name(provider)} failed for prices: {e}")
        
        # v4.2.3: Final Fallback: Internet Search for critical missing tickers
        if missing_tickers:
             self.logger.info(f"Final Fallback: Searching web for {missing_tickers}")
             for ticker in missing_tickers:
                 price = self.get_price_from_search(ticker)
                 if price > 0:
                     all_prices[ticker] = price
        
        return all_prices

    def get_price_from_search(self, ticker: str) -> float:
        """
        Last-resort method to extract price from internet search results.
        最後的備援方法：從網路搜尋結果中提取價格。
        """
        import re
        query = f"{ticker} stock current price USD"
        try:
            results = self.search_service.search_financial_context(query, max_results=2)
            for res in results:
                snippet = res.get('snippet', '') + " " + res.get('title', '')
                # Look for patterns like $123.45 or 123.45 USD
                patterns = [
                    r'\$\s?([0-9]{1,5}\.[0-9]{1,2})',
                    r'([0-9]{1,5}\.[0-9]{1,2})\s?USD'
                ]
                for p in patterns:
                    matches = re.findall(p, snippet)
                    if matches:
                        price = float(matches[0])
                        # Basic sanity check (exclude 0 or ridiculously high values if not BRK.A)
                        if price > 0 and (price < 10000 or ticker == 'BRK.A'):
                            self.logger.info(f"Verified {ticker} price from search: ${price}")
                            return price
        except Exception as e:
            self.logger.warning(f"Search-based price fetch failed for {ticker}: {e}")
        return 0.0
    def get_market_context(self, tickers: List[str], enrich: bool = False) -> Dict[str, Any]:
        """
        Get detailed market context (OHLCV + Indicators) for a list of tickers.
        獲取一系列標的的詳細市場內容（OHLCV + 指標）。
        """
        context = {}
        for ticker in tickers:
            indicators = self.get_technical_indicators(ticker)
            ohlcv = self.get_ohlcv(ticker)
            
            data = {
                "price_data": ohlcv,
                "indicators": indicators
            }
            
            if enrich:
                data["financials"] = self.get_financials(ticker)
                data["news"] = self.get_news(ticker)
                data["web_intelligence"] = self.get_web_intelligence(ticker)
                
            context[ticker] = data
        return context

    def get_web_intelligence(self, ticker: str) -> List[Dict[str, str]]:
        """
        Tavily-powered deep web search for qualitative intelligence.
        Every call consumes Tavily credits to ensure the service is utilized.
        透過 Tavily 搜尋個股的深度定性情報。每次呼叫消耗 Tavily Credits。
        
        Queries:
          1. Breaking news / risk alerts for today
          2. Analyst opinions / catalysts / competitive moat
        """
        today_str = date.today().isoformat()
        queries = [
            f"{ticker} stock latest news risk alert {today_str}",
            f"{ticker} analyst opinion catalyst moat 2026",
        ]
        
        results = []
        for query in queries:
            try:
                search_results = self.search_service.search_financial_context(
                    query, max_results=3
                )
                results.extend(search_results)
            except Exception as e:
                self.logger.warning(f"Web intelligence search failed for '{query}': {e}")
        
        if results:
            self.logger.info(
                f"Fetched {len(results)} web intelligence items for {ticker} via Tavily"
            )
        return results

    def get_ohlcv(self, ticker: str, days: int = 30) -> Dict[str, List[Any]]:
        """
        Get historical OHLCV data for a specific ticker.
        獲取特定標的的歷史 OHLCV 數據。
        """
        # Override Priority for History: Polygon -> YFinance -> FMP
        history_providers = [self.polygon, self.yfinance, self.fmp] 
        
        for provider in history_providers:
            try:
                df = provider.fetch_history(ticker, days=days)
                if df is not None and not df.empty:
                    self.logger.info(f"Fetched history for {ticker} from {self._get_provider_name(provider)}")
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
                
                # Sanity check for historical data
                closes = df['Close'].tolist()
                suspicious_vals = [100.0, 110.0, 89.0]
                bad_prices = [p for p in closes if p in suspicious_vals]
                if bad_prices:
                    self.logger.warning(
                        f"SUSPICIOUS HISTORICAL PRICE DETECTED for {ticker} from {self._get_provider_name(provider)}: "
                        f"{bad_prices[0]}. This might be an API fallback error."
                    )

            except Exception as e:
                 self.logger.warning(f"History fetch failed on {self._get_provider_name(provider)}: {e}")
        return {}

    def get_ohlcv_batch(self, tickers: List[str], days: int = 30) -> Dict[str, Dict[str, List[Any]]]:
        """
        Get historical OHLCV data for multiple tickers in batch.
        批次獲取多個標的的歷史 OHLCV 數據。
        """
        results = {}
        for ticker in tickers:
            data = self.get_ohlcv(ticker, days=days)
            if data:
                results[ticker] = data
        return results

    def get_technical_indicators(self, ticker: str) -> Dict[str, Any]:
        """
        Calculate indicators. Relies on fetch_history (defaulting to YFinance).
        計算指標。依賴 fetch_history（預設為 YFinance）。
        """
        try:
            # We use self.get_ohlcv methodology but need DataFrame.
            # So we call fetch_history on YFinance directly or iterate.
            
            df = pd.DataFrame()
            # Prioritize Polygon for indicators base data (Unlimited history)
            for provider in [self.polygon, self.yfinance]:
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

    def get_news(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Get News using Strategy: Tiingo -> Finnhub -> AlphaVantage -> FMP -> YFinance -> Polygon
        返回結構化新聞數據：優先使用 Tiingo。
        """
        # News Strategy: Tiingo is best for tagged financial news, Finnhub/AlphaVantage following.
        news_providers = [self.tiingo, self.finnhub, self.alpha_vantage, self.fmp, self.yfinance, self.polygon]
        
        all_news = []
        for provider in news_providers:
            try:
                news = provider.fetch_news(ticker, limit=5)
                if news:
                    # v5.0: Return raw dicts for better flexibility in agents/sentinel
                    all_news.extend(news)
                    if len(all_news) >= 5: break
            except Exception as e:
                 self.logger.warning(f"News fetch failed on {self._get_provider_name(provider)}")
        
        return all_news[:5]

    def get_financials(self, ticker: str) -> Dict[str, Any]:
        """
        Get fundamental financial data for a ticker.
        獲取標底的基本面財務數據。
        """
        fund_providers = [self.fmp, self.alpha_vantage, self.finnhub, self.yfinance, self.polygon]
        
        for provider in fund_providers:
            try:
                info = provider.fetch_info(ticker)
                if info and info.get('market_cap'): # Basic validation
                     # Normalize keys if needed, but for now we expect mostly common keys
                     return info
            except Exception as e:
                self.logger.debug(f"Provider {self._get_provider_name(provider)} failed for financials: {e}")
                continue
        return {}

    def get_valuation_metrics(self, ticker: str) -> Dict[str, Any]:
        """
        Alias/Sub-set of financials for valuation.
        估值指標的別名/子集。
        """
        # For now, it returns financials which contains valuation data (market cap etc.)
        return self.get_financials(ticker)

    def get_macro_data(self) -> Dict[str, Any]:
        """
        Get comprehensive macro economic indicators and market sentiment.
        獲取全面的宏觀經濟指標與市場情緒。
        """
        macro_data = {}
        
        # 1. Try FRED (Primary)
        try:
            if self.fred:
                # Use standard fetch_historical or specialized getter
                # For backward compatibility with existing agents:
                fred_data = self.fred.fred_service.get_macro_indicators()
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

    def get_yield_curve_inversion(self) -> Dict[str, Any]:
         """
         Check for yield curve inversion status.
         檢查殖利率曲線倒掛狀態。
         """
         # 1. Try FRED (Primary)
         try:
             if self.fred:
                 fred_data = self.fred.fred_service.get_macro_indicators()
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

