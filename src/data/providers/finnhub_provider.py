import os
import requests
import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Any, Optional
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.utils.tracing import trace_external_call

class FinnhubProvider(MarketDataProvider):
    """
    Finnhub Provider for real-time data, sentiment, and earnings.
    Finnhub 數據提供者，支援即時行情、情緒分析與財報日曆。
    """
    def __init__(self, user_id: str = "system", settings_service: SettingsService = None):
        self.logger = setup_logger("FinnhubProvider")
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        self.base_url = "https://finnhub.io/api/v1"
        self.api_key = self._get_api_key()

    def _get_api_key(self) -> str:
        settings = self.settings_service.get_all_settings()
        return settings.get("source_finnhub_api_key") or settings.get("FINNHUB_API_KEY")

    @trace_external_call("finnhub")
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetches current prices using Quote endpoint.
        """
        results = {}
        for ticker in tickers:
            try:
                url = f"{self.base_url}/quote"
                params = {"symbol": ticker, "token": self.api_key}
                resp = requests.get(url, params=params, timeout=10)
                data = resp.json()
                if data and "c" in data:
                    results[ticker] = float(data["c"])
            except Exception as e:
                self.logger.error(f"Finnhub quote failed for {ticker}: {e}")
        return results

    @trace_external_call("finnhub")
    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """
        Fetches historical data using Stock Candles endpoint.
        """
        try:
            import time
            from datetime import datetime
            import pandas as pd
            
            days_int = days if days else 365
            end_ts = int(time.time())
            start_ts = end_ts - (days_int * 86400)
            
            url = f"{self.base_url}/stock/candle"
            params = {
                "symbol": ticker,
                "resolution": "D",
                "from": start_ts,
                "to": end_ts,
                "token": self.api_key
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            
            if data.get("s") != "ok":
                return pd.DataFrame()
                
            history = []
            for i in range(len(data["t"])):
                history.append({
                    "Date": datetime.fromtimestamp(data["t"][i]),
                    "Open": float(data["o"][i]),
                    "High": float(data["h"][i]),
                    "Low": float(data["l"][i]),
                    "Close": float(data["c"][i]),
                    "Volume": int(data["v"][i])
                })
            df = pd.DataFrame(history)
            df.set_index("Date", inplace=True)
            return df
        except Exception as e:
            self.logger.error(f"Finnhub candles failed for {ticker}: {e}")
            return pd.DataFrame()

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetches company profile 2.
        """
        try:
            url = f"{self.base_url}/stock/profile2"
            params = {"symbol": ticker, "token": self.api_key}
            resp = requests.get(url, params=params, timeout=10)
            return resp.json()
        except Exception as e:
            self.logger.error(f"Finnhub profile failed for {ticker}: {e}")
            return {}

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches company news.
        """
        try:
            from datetime import datetime, timedelta
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            
            url = f"{self.base_url}/company-news"
            params = {
                "symbol": ticker,
                "from": start,
                "to": end,
                "token": self.api_key
            }
            resp = requests.get(url, params=params, timeout=10)
            items = resp.json()
            
            results = []
            if isinstance(items, list):
                for item in items[:limit]:
                    results.append({
                        "title": item.get("headline"),
                        "url": item.get("url"),
                        "time_published": item.get("datetime"),
                        "summary": item.get("summary"),
                        "source": "Finnhub",
                        "related": item.get("related")
                    })
            return results
        except Exception as e:
            self.logger.error(f"Finnhub news failed for {ticker}: {e}")
            return []
            
    def get_sentiment(self, ticker: str) -> Dict[str, Any]:
        """
        Fetches news sentiment.
        """
        try:
            url = f"{self.base_url}/news-sentiment"
            params = {"symbol": ticker, "token": self.api_key}
            resp = requests.get(url, params=params, timeout=10)
            return resp.json()
        except Exception as e:
            self.logger.error(f"Finnhub sentiment failed for {ticker}: {e}")
            return {}
