import os
import requests
import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Any, Optional
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.utils.tracing import trace_external_call

class AlphaVantageProvider(MarketDataProvider):
    """
    Alpha Vantage Provider for financial data and indicators.
    Alpha Vantage 數據提供者，支援行情與技術指標。
    """
    def __init__(self, api_key: str = None, user_id: str = None, settings_service: SettingsService = None):
        """
        Initialize the AlphaVantage provider.
        初始化 AlphaVantage 提供者。
        """
        self.logger = setup_logger("AlphaVantageProvider")
        
        # Resolve Settings
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        self.api_key = api_key or self._get_api_key()
        self.base_url = "https://www.alphavantage.co/query"

    def _get_api_key(self) -> str:
        settings = self.settings_service.get_all_settings()
        return settings.get("source_alpha_vantage_api_key") or settings.get("ALPHA_VANTAGE_API_KEY")

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
    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """
        Fetches historical data using TIME_SERIES_DAILY.
        """
        try:
            import pandas as pd
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "outputsize": "full",
                "apikey": self.api_key
            }
            resp = requests.get(self.base_url, params=params, timeout=10)
            raw_data = resp.json().get("Time Series (Daily)", {})
            
            if not raw_data:
                return pd.DataFrame()

            history = []
            # Calculate start date based on days or 1y
            days_int = days if days else 365
            start_date = (pd.Timestamp.now() - pd.Timedelta(days=days_int)).strftime('%Y-%m-%d')

            for date_str, values in raw_data.items():
                if date_str >= start_date:
                    history.append({
                        "Date": pd.to_datetime(date_str),
                        "Open": float(values["1. open"]),
                        "High": float(values["2. high"]),
                        "Low": float(values["3. low"]),
                        "Close": float(values["4. close"]),
                        "Volume": int(values["5. volume"])
                    })
            df = pd.DataFrame(history)
            if not df.empty:
                df.set_index("Date", inplace=True)
                df = df.sort_index()
            return df
        except Exception as e:
            self.logger.error(f"AlphaVantage historical failed for {ticker}: {e}")
            return pd.DataFrame()

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

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
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
            for item in feed[:limit]:
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
