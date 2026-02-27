import os
import requests
from typing import Dict, List, Any, Optional
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger
from src.repositories.settings_repository import AlchemySettingsRepository
from src.utils.tracing import trace_external_call

class FinnhubProvider(MarketDataProvider):
    """
    Finnhub Provider for real-time data, sentiment, and earnings.
    Finnhub 數據提供者，支援即時行情、情緒分析與財報日曆。
    """
    def __init__(self, user_id: str = "system", settings_repo=None):
        self.logger = setup_logger("FinnhubProvider")
        self.user_id = user_id
        self.settings_repo = settings_repo or AlchemySettingsRepository()
        self.base_url = "https://finnhub.io/api/v1"
        self.api_key = self._get_api_key()

    def _get_api_key(self) -> str:
        settings = self.settings_repo.get_all_dict(self.user_id)
        return settings.get("FINNHUB_API_KEY") or os.getenv("FINNHUB_API_KEY", "")

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

    def fetch_historical(self, ticker: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetches historical data using Stock Candles endpoint.
        """
        try:
            import time
            from datetime import datetime
            
            s_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            e_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
            
            url = f"{self.base_url}/stock/candle"
            params = {
                "symbol": ticker,
                "resolution": "D",
                "from": s_ts,
                "to": e_ts,
                "token": self.api_key
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            
            if data.get("s") != "ok":
                return []
                
            history = []
            for i in range(len(data["t"])):
                history.append({
                    "date": datetime.fromtimestamp(data["t"][i]).strftime("%Y-%m-%d"),
                    "open": float(data["o"][i]),
                    "high": float(data["h"][i]),
                    "low": float(data["l"][i]),
                    "close": float(data["c"][i]),
                    "volume": int(data["v"][i])
                })
            return history
        except Exception as e:
            self.logger.error(f"Finnhub candles failed for {ticker}: {e}")
            return []

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

    def get_news(self, ticker: str) -> List[Dict[str, Any]]:
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
                for item in items:
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
