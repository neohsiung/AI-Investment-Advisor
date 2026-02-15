import os
import requests
import pandas as pd
from typing import Dict, Any, List
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger

from src.services.settings_service import SettingsService

class FMPProvider(MarketDataProvider):
    """
    Financial Modeling Prep Data Provider.
    Requires FMP_API_KEY env var or DB setting.
    """
    def __init__(self, api_key: str = None, user_id: str = None, settings_service: SettingsService = None):
        self.logger = setup_logger("FMPProvider")
        
        # Resolve Settings
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        
        # Priority: explicit -> DB -> Env
        self.api_key = api_key or settings.get("source_fmp_api_key") or os.getenv("FMP_API_KEY")
        self.base_url = "https://financialmodelingprep.com/api/v3"
        
        if not self.api_key:
            self.logger.warning("FMP_API_KEY not found.")

    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        if not self.api_key or not tickers: return {}
        prices = {}
        
        # Chunking to avoid "URI Too Long" (Limit batch to 50)
        batch_size = 50
        
        try:
            for i in range(0, len(tickers), batch_size):
                chunk = tickers[i:i + batch_size]
                ticker_str = ",".join(chunk)
                
                # Use Verified Stable Endpoint (2025/2026 Standard)
                # Replaces Legacy /api/v3/quote
                url = "https://financialmodelingprep.com/stable/quote"
                params = {"symbol": ticker_str, "apikey": self.api_key}
                
                resp = requests.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data:
                        if 'symbol' in item and 'price' in item:
                            prices[item['symbol']] = item['price']
                else:
                     self.logger.warning(f"FMP Batch Failed ({resp.status_code})")
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
                        "website": item.get('website'),
                        "ceo": item.get('ceo')
                    }
        except Exception as e:
            self.logger.error(f"FMP fetch_info error: {e}")
        return {}

    def fetch_sector_performance(self) -> List[Dict[str, Any]]:
        """Fetch real-time sector performance."""
        if not self.api_key: return []
        try:
            url = f"{self.base_url}/sector-performance"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                # Returns list of {sector: '...', changesPercentage: '...'}
                return resp.json()
        except Exception as e:
            self.logger.error(f"FMP sector perf error: {e}")
        return []

    def fetch_stock_peers(self, ticker: str) -> List[str]:
        """Fetch stock peers (competitors) for supply chain/industry analysis."""
        if not self.api_key: return []
        try:
            url = f"{self.base_url}/stock_peers"
            params = {"symbol": ticker, "apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # format: [{"peersList": ["A", "B"]}] or just list depending on version
                if data and isinstance(data[0], dict):
                    return data[0].get('peersList', [])
                return [] 
        except Exception as e:
            self.logger.error(f"FMP peers error: {e}")
        return []

    def fetch_key_metrics(self, ticker: str) -> Dict[str, Any]:
        """Fetch Key Metrics (TTM) - PE, EPS, etc."""
        if not self.api_key: return {}
        try:
            url = f"{self.base_url}/key-metrics-ttm/{ticker}"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data: return data[0]
        except Exception as e:
            self.logger.error(f"FMP key metrics error: {e}")
        return {}
    
    def fetch_financial_ratios(self, ticker: str) -> Dict[str, Any]:
        """Fetch Financial Ratios (TTM)"""
        if not self.api_key: return {}
        try:
            url = f"{self.base_url}/ratios-ttm/{ticker}"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data: return data[0]
        except Exception as e:
            self.logger.error(f"FMP ratios error: {e}")
        return {}
