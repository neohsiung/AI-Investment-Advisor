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
    Polygon.io 資料提供者。需要 POLYGON_API_KEY 環境變數。
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
        # Polygon Snapshot API (所有代號) 很有效率但可能過於繁重。
        # 目前先用迴圈，之後再優化或改用 Snapshot。
        # Using Snapshot - Ticker
        try:
            for ticker in tickers:
                url = f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
                params = {"apiKey": self.api_key}
                resp = requests.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    # Snapshot response: ticker.lastTrade.p or ticker.min.c (close)
                    # Snapshot 回應：ticker.lastTrade.p 或 ticker.min.c (收盤價)
                    if 'ticker' in data and 'lastTrade' in data['ticker']:
                        val = data['ticker']['lastTrade']['p']
                        if val > 0:
                            prices[ticker] = val
                    elif 'ticker' in data and 'day' in data['ticker']:
                         val = data['ticker']['day']['c']
                         if val > 0:
                             prices[ticker] = val
                    
                    # Fallback: internal prevDay (Efficient)
                    # Fallback: 內部 prevDay (高效)
                    if ticker not in prices and 'ticker' in data and 'prevDay' in data['ticker']:
                        val = data['ticker']['prevDay']['c']
                        if val > 0:
                            prices[ticker] = val

                    # Final External Fallback (Only if snapshot had NO data)
                    if ticker not in prices:
                        prev = self._fetch_prev_close(ticker)
                        if prev > 0:
                            prices[ticker] = prev

        except Exception as e:
            self.logger.error(f"Polygon fetch_current_prices error: {e}")
        
        return prices

    def _fetch_prev_close(self, ticker: str) -> float:
        """Fetch previous day's close price as fallback."""
        try:
            url = f"{self.base_url}/v2/aggs/ticker/{ticker}/prev"
            params = {"adjusted": "true", "apiKey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])
                if results and 'c' in results[0]:
                    return results[0]['c']
        except Exception:
            pass
        return 0.0

    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        if not self.api_key: return pd.DataFrame()
        try:
            # Map period/days to 'from' date. 
            # Default to 1 year back for '1y' or 'days' if provided.
            from_date = (pd.Timestamp.now() - pd.Timedelta(days=days if days else 365)).strftime('%Y-%m-%d')
            to_date = pd.Timestamp.now().strftime('%Y-%m-%d')
            
            url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
            params = {"adjusted": "true", "sort": "asc", "limit": 5000, "apiKey": self.api_key}
            
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])
                if not results:
                    return pd.DataFrame()
                
                df = pd.DataFrame(results)
                # Polygon keys: o (open), h (high), l (low), c (close), v (volume), t (timestamp)
                # Polygon 鍵值：o (開盤), h (最高), l (最低), c (收盤), v (成交量), t (時間戳)
                df = df.rename(columns={
                    'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume', 't': 'Timestamp'
                })
                df['Date'] = pd.to_datetime(df['Timestamp'], unit='ms')
                df.set_index('Date', inplace=True)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception as e:
            self.logger.error(f"Polygon fetch_history error: {e}")
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
