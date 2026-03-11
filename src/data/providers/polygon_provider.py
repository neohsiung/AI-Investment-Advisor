import os
import requests
import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, Any, List
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger

from src.services.settings_service import SettingsService
from src.utils.tracing import trace_external_call

class PolygonProvider(MarketDataProvider):
    """
    Polygon.io Data Provider for stock snapshots and historical data.
    Polygon.io 股票快照與歷史數據提供者。
    
    Requires POLYGON_API_KEY env var or DB setting.
    需要 POLYGON_API_KEY 環境變數或資料庫設定。
    """
    def __init__(self, api_key: str = None, user_id: str = None, settings_service: SettingsService = None):
        """
        Initialize the Polygon provider.
        初始化 Polygon 提供者。
        """
        self.logger = setup_logger("PolygonProvider")
        
        # Resolve Settings
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        
        # Priority: explicit -> DB
        self.api_key = api_key or settings.get("source_polygon_api_key")
        self.base_url = "https://api.polygon.io"
        
        if not self.api_key:
            self.logger.warning("POLYGON_API_KEY not found. Some features may fail.")

    @trace_external_call("polygon")
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetch current stock prices using Polygon's snapshot API.
        Optimized to use v3 bulk snapshot if multiple tickers are requested.
        """
        if not self.api_key or not tickers: return {}
        prices = {}
        
        # Strategy: Use v3 snapshot for bulk (Up to 1 call instead of N)
        try:
            ticker_list = ",".join(tickers)
            url = f"{self.base_url}/v3/snapshot"
            params = {
                "ticker.any_of": ticker_list,
                "apiKey": self.api_key
            }
            
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])
                for res in results:
                    ticker = res.get('ticker')
                    # v3 snapshot structure: session.price or last_trade.p
                    session = res.get('session', {})
                    val = session.get('price') or res.get('last_trade', {}).get('p')
                    if ticker and val and val > 0:
                        prices[ticker] = val
                
                if prices:
                    self.logger.info(f"Polygon: Fetched {len(prices)} bulk prices via v3 snapshot.")
                    # Check if all tickers resolved
                    if len(prices) == len(tickers):
                        return prices
            elif resp.status_code == 403:
                self.logger.warning(f"Polygon v3 snapshot 403 (Forbidden). Plan may not support bulk snapshot.")
            else:
                self.logger.warning(f"Polygon v3 snapshot failed (Status {resp.status_code}): {resp.text}")
        except Exception as e:
            self.logger.warning(f"Polygon v3 bulk snapshot failed: {e}. Falling back to v2 single-ticker.")

        # Fallback: v2 Single-ticker snapshots (Expensive but reliable if v3 fails)
        try:
            for ticker in tickers:
                if ticker in prices: continue
                url = f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
                params = {"apiKey": self.api_key}
                resp = requests.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    t_data = data.get('ticker', {})
                    val = t_data.get('lastTrade', {}).get('p') or t_data.get('day', {}).get('c')
                    
                    if not val or val <= 0:
                        val = t_data.get('prevDay', {}).get('c')

                    if val and val > 0:
                        prices[ticker] = val
                elif resp.status_code == 403:
                    self.logger.warning(f"Polygon v2 snapshot 403 for {ticker}. Plan lacks real-time permissions.")
                    # v4.3.2: Critical Fallback: Use prev close for ALL tickers that failed snapshots
                    val = self._fetch_prev_close(ticker)
                    if val > 0:
                        prices[ticker] = val
        except Exception as e:
            self.logger.error(f"Polygon v2 fallback error: {e}")
        
        return prices

    def _fetch_prev_close(self, ticker: str) -> float:
        """
        Fetch the previous day's close price as a fallback.
        獲取前一交易日收盤價作為備援。
        """
        try:
            url = f"{self.base_url}/v2/aggs/ticker/{ticker}/prev"
            params = {"adjusted": "true", "apiKey": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])
                if results and 'c' in results[0]:
                    return results[0]['c']
        except (requests.RequestException, ValueError, IndexError):
            pass
        return 0.0

    @trace_external_call("polygon")
    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a ticker.
        獲取標的的歷史 OHLCV 數據。
        """
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

    @trace_external_call("polygon")
    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch the latest stock news via Polygon's news API.
        透過 Polygon 的新聞 API 獲取最新股票新聞。
        """
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

    @trace_external_call("polygon")
    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch ticker reference information (company profile).
        獲取標的參考資訊（公司概況）。
        """
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
