import os
import requests
import pandas as pd
from typing import Dict, Any, List
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger

class FMPProvider(MarketDataProvider):
    """
    Financial Modeling Prep Data Provider.
    Requires FMP_API_KEY env var.
    """
    def __init__(self, api_key: str = None):
        self.logger = setup_logger("FMPProvider")
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.base_url = "https://financialmodelingprep.com/api/v3"
        
        if not self.api_key:
            self.logger.warning("FMP_API_KEY not found.")

    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        if not self.api_key or not tickers: return {}
        prices = {}
        try:
            ticker_str = ",".join(tickers)
            url = f"{self.base_url}/quote/{ticker_str}"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    if 'symbol' in item and 'price' in item:
                        prices[item['symbol']] = item['price']
        except Exception as e:
            self.logger.error(f"FMP fetch_current_prices error: {e}")
        return prices

    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        # FMP History
        return pd.DataFrame()

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.api_key: return []
        try:
             url = f"{self.base_url}/stock_news"
             params = {"tickers": ticker, "limit": limit, "apikey": self.api_key}
             resp = requests.get(url, params=params, timeout=5)
             if resp.status_code == 200:
                 data = resp.json()
                 news = []
                 for item in data:
                     news.append({
                         "title": item.get('title'),
                         "link": item.get('url'),
                         "publisher": item.get('site'),
                         "publishedDate": item.get('publishedDate')
                     })
                 return news
        except Exception as e:
            self.logger.error(f"FMP fetch_news error: {e}")
        return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        if not self.api_key: return {}
        try:
            url = f"{self.base_url}/profile/{ticker}"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    item = data[0]
                    return {
                        "market_cap": item.get('mktCap'),
                        "sector": item.get('sector'),
                        "industry": item.get('industry'),
                        "description": item.get('description'),
                        "website": item.get('website')
                    }
        except Exception as e:
            self.logger.error(f"FMP fetch_info error: {e}")
        return {}
