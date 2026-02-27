import os
import requests
from typing import Dict, List, Any, Optional
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger
from src.repositories.settings_repository import AlchemySettingsRepository
from src.utils.tracing import trace_external_call

class AlphaVantageProvider(MarketDataProvider):
    """
    Alpha Vantage Provider for financial data and indicators.
    Alpha Vantage 數據提供者，支援行情與技術指標。
    """
    def __init__(self, user_id: str = "system", settings_repo=None):
        self.logger = setup_logger("AlphaVantageProvider")
        self.user_id = user_id
        self.settings_repo = settings_repo or AlchemySettingsRepository()
        self.base_url = "https://www.alphavantage.co/query"
        self.api_key = self._get_api_key()

    def _get_api_key(self) -> str:
        settings = self.settings_repo.get_all_dict(self.user_id)
        return settings.get("ALPHA_VANTAGE_API_KEY") or os.getenv("ALPHA_VANTAGE_API_KEY", "")

    @trace_external_call("alpha_vantage")
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetches current prices using GLOBAL_QUOTE.
        """
        results = {}
        for ticker in tickers:
            try:
                params = {
                    "function": "GLOBAL_QUOTE",
                    "symbol": ticker,
                    "apikey": self.api_key
                }
                resp = requests.get(self.base_url, params=params, timeout=10)
                data = resp.json().get("Global Quote", {})
                if data:
                    results[ticker] = float(data.get("05. price", 0))
            except Exception as e:
                self.logger.error(f"AlphaVantage failed for {ticker}: {e}")
        return results

    @trace_external_call("alpha_vantage")
    def fetch_historical(self, ticker: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetches historical data using TIME_SERIES_DAILY.
        """
        try:
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "outputsize": "full",
                "apikey": self.api_key
            }
            resp = requests.get(self.base_url, params=params, timeout=10)
            raw_data = resp.json().get("Time Series (Daily)", {})
            
            history = []
            for date_str, values in raw_data.items():
                if start_date <= date_str <= end_date:
                    history.append({
                        "date": date_str,
                        "open": float(values["1. open"]),
                        "high": float(values["2. high"]),
                        "low": float(values["3. low"]),
                        "close": float(values["4. close"]),
                        "volume": int(values["5. volume"])
                    })
            return sorted(history, key=lambda x: x["date"])
        except Exception as e:
            self.logger.error(f"AlphaVantage historical failed for {ticker}: {e}")
            return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetches company overview using OVERVIEW.
        """
        try:
            params = {
                "function": "OVERVIEW",
                "symbol": ticker,
                "apikey": self.api_key
            }
            resp = requests.get(self.base_url, params=params, timeout=10)
            return resp.json()
        except Exception as e:
            self.logger.error(f"AlphaVantage overview failed for {ticker}: {e}")
            return {}

    def get_news(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Fetches news sentiment using NEWS_SENTIMENT.
        """
        try:
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "apikey": self.api_key
            }
            resp = requests.get(self.base_url, params=params, timeout=10)
            feed = resp.json().get("feed", [])
            
            results = []
            for item in feed:
                results.append({
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "time_published": item.get("time_published"),
                    "summary": item.get("summary"),
                    "sentiment_score": item.get("overall_sentiment_score"),
                    "sentiment_label": item.get("overall_sentiment_label"),
                    "source": "AlphaVantage"
                })
            return results
        except Exception as e:
            self.logger.error(f"AlphaVantage news failed for {ticker}: {e}")
            return []
