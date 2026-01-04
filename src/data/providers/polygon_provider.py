import os
import requests
import pandas as pd
from typing import Dict, Any, List
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger

class PolygonProvider(MarketDataProvider):
    """
    Polygon.io Data Provider.
    Requires POLYGON_API_KEY env var.
    """
    def __init__(self, api_key: str = None):
        self.logger = setup_logger("PolygonProvider")
        self.api_key = api_key or os.getenv("POLYGON_API_KEY")
        self.base_url = "https://api.polygon.io"
        
        if not self.api_key:
            self.logger.warning("POLYGON_API_KEY not found. Some features may fail.")

    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        if not self.api_key: return {}
        prices = {}
        # Polygon Snapshot API (All tickers) is efficient but might be overkill.
        # Loop for now, optimize later or use Snapshot.
        # Using Snapshot - Ticker
        try:
            for ticker in tickers:
                url = f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
                params = {"apiKey": self.api_key}
                resp = requests.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    # Snapshot response: ticker.lastTrade.p or ticker.min.c (close)
                    if 'ticker' in data and 'lastTrade' in data['ticker']:
                        prices[ticker] = data['ticker']['lastTrade']['p']
                    elif 'ticker' in data and 'day' in data['ticker']:
                         prices[ticker] = data['ticker']['day']['c']
        except Exception as e:
            self.logger.error(f"Polygon fetch_current_prices error: {e}")
        
        return prices

    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        # Implementation for history - Aggregates (Bars)
        # TODO: Map 'period' to Polygon timespan
        return pd.DataFrame()

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.api_key: return []
        try:
            url = f"{self.base_url}/v2/reference/news"
            params = {"ticker": ticker, "limit": limit, "apiKey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                results = resp.json().get('results', [])
                news = []
                for r in results:
                    news.append({
                        "title": r.get('title'),
                        "link": r.get('article_url'),
                        "publisher": r.get('publisher', {}).get('name'),
                        "published_utc": r.get('published_utc')
                    })
                return news
        except Exception as e:
            self.logger.error(f"Polygon news error: {e}")
        return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        if not self.api_key: return {}
        try:
             url = f"{self.base_url}/v3/reference/tickers/{ticker}"
             params = {"apiKey": self.api_key}
             resp = requests.get(url, params=params, timeout=5)
             if resp.status_code == 200:
                 res = resp.json().get('results', {})
                 return {
                     "market_cap": res.get('market_cap'),
                     "industry": res.get('sic_description'), # Proxy for industry
                     "sector": res.get('sic_code') # Proxy
                 }
        except Exception as e:
             self.logger.error(f"Polygon info error: {e}")
        return {}
