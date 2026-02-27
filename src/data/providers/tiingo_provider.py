import os
import requests
import pandas as pd
from typing import Dict, Any, List, Optional
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.utils.tracing import trace_external_call

class TiingoProvider(MarketDataProvider):
    """
    Tiingo Data Provider for OHLCV, IEX real-time prices, and News.
    Tiingo 數據提供者，支援 OHLCV、IEX 即時價格與新聞流。
    
    Registration: https://api.tiingo.com/
    Priority in Matrix: P1 (Clean News, 500/1000 daily usage reported)
    """

    def __init__(self, api_key: str = None, user_id: str = None, settings_service: SettingsService = None):
        """
        Initialize the Tiingo provider.
        初始化 Tiingo 提供者。
        """
        self.logger = setup_logger("TiingoProvider")
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        
        # Priority: explicit -> DB -> Env
        self.api_key = api_key or settings.get("source_tiingo_api_key") or os.getenv("TIINGO_API_KEY")
        self.base_url = "https://api.tiingo.com"
        
        if not self.api_key:
            self.logger.warning("TIINGO_API_KEY not found. Data fetching may fail.")

    @trace_external_call("tiingo")
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetch real-time (IEX) prices for a list of tickers in bulk.
        使用 Tiingo IEX API 批次獲取即時價格。
        """
        if not self.api_key or not tickers:
            return {}
            
        prices = {}
        try:
            # Tiingo supports bulk via comma-separated tickers
            ticker_str = ",".join(tickers)
            url = f"{self.base_url}/iex/"
            params = {
                "tickers": ticker_str,
                "token": self.api_key
            }
            
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json() # List of ticker objects
                for entry in data:
                    ticker = entry.get('ticker')
                    last_price = entry.get('last') or entry.get('tngoLast')
                    if ticker and last_price and last_price > 0:
                        prices[ticker] = float(last_price)
                        
            if prices:
                self.logger.info(f"Tiingo: Fetched {len(prices)} bulk prices.")
        except Exception as e:
            self.logger.error(f"Tiingo fetch_current_prices error: {e}")
            
        return prices

    @trace_external_call("tiingo")
    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """
        Fetch historical end-of-day OHLCV data.
        獲取日終歷史 OHLCV 數據。
        """
        if not self.api_key:
            return pd.DataFrame()
            
        try:
            # Map days to start_date
            # Default to 1 year back
            days_int = days if days else 365
            start_date = (pd.Timestamp.now() - pd.Timedelta(days=days_int)).strftime('%Y-%m-%d')
            
            url = f"{self.base_url}/tiingo/daily/{ticker}/prices"
            params = {
                "startDate": start_date,
                "token": self.api_key
            }
            
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if not data:
                    return pd.DataFrame()
                    
                df = pd.DataFrame(data)
                # Tiingo keys: date, adjClose, adjHigh, adjLow, adjOpen, adjVolume
                df['Date'] = pd.to_datetime(df['date'])
                df.set_index('Date', inplace=True)
                
                # Use adjusted prices for accuracy
                df = df.rename(columns={
                    'adjOpen': 'Open',
                    'adjHigh': 'High',
                    'adjLow': 'Low',
                    'adjClose': 'Close',
                    'adjVolume': 'Volume'
                })
                
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception as e:
            self.logger.error(f"Tiingo fetch_history error for {ticker}: {e}")
            
        return pd.DataFrame()

    @trace_external_call("tiingo")
    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch tagged financial news via Tiingo's news engine.
        透過 Tiingo 新聞引擎獲取具備標籤的財經新聞。
        """
        if not self.api_key:
            return []
            
        try:
            url = f"{self.base_url}/tiingo/news"
            params = {
                "tickers": ticker,
                "limit": limit,
                "token": self.api_key
            }
            
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                results = resp.json()
                news_list = []
                for item in results:
                    news_list.append({
                        "title": item.get('title'),
                        "link": item.get('url'),
                        "publisher": item.get('source'),
                        "published_at": item.get('publishedDate'),
                        "summary": item.get('description')
                    })
                return news_list
        except Exception as e:
            self.logger.error(f"Tiingo news error for {ticker}: {e}")
            
        return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch basic ticker information.
        獲取基本標的資訊。
        """
        if not self.api_key:
            return {}
            
        try:
            url = f"{self.base_url}/tiingo/daily/{ticker}"
            params = {"token": self.api_key}
            
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                res = resp.json()
                return {
                    "name": res.get('name'),
                    "description": res.get('description'),
                    "exchange": res.get('exchangeCode'),
                    "start_date": res.get('startDate'),
                    "end_date": res.get('endDate')
                }
        except Exception as e:
             self.logger.debug(f"Tiingo info error for {ticker}: {e}")
             
        return {}
