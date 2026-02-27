from typing import Dict, List, Any, Optional
from datetime import datetime
from src.data.providers.base import MarketDataProvider
from src.services.fred_service import FredService
from src.utils.logger import setup_logger
from src.utils.tracing import trace_external_call

class FredProvider(MarketDataProvider):
    """
    Standard Provider Wrapper for FRED (Federal Reserve Economic Data).
    FRED Provider 包裝器，繼承自 MarketDataProvider 以符合系統標準。
    """
    def __init__(self, user_id: str = "system"):
        self.logger = setup_logger("FredProvider")
        self.fred_service = FredService(user_id=user_id)
        self.name = "FRED"

    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        FRED doesn't provide real-time stock prices. Returns empty.
        FRED 不提供即時股票價格。
        """
        return {}

    @trace_external_call("fred")
    def fetch_historical(self, ticker: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetches historical macro data. 
        獲取歷史宏觀數據。
        """
        # Note: FredService.get_macro_indicators returns a specific structured format.
        # We might need to extend it for generic historical series if needed.
        self.logger.info(f"Fetching historical data for {ticker} from FRED")
        if not self.fred_service.client:
            return []
        
        try:
            series = self.fred_service.client.get_series(ticker, observation_start=start_date, observation_end=end_date)
            return [{"date": idx.strftime("%Y-%m-%d"), "value": val} for idx, val in series.items()]
        except Exception as e:
            self.logger.error(f"Failed to fetch {ticker} from FRED: {e}")
            return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetches series info from FRED.
        獲取 FRED 序列資訊。
        """
        if not self.fred_service.client:
            return {}
        try:
            info = self.fred_service.client.get_series_info(ticker)
            return info.to_dict() if hasattr(info, 'to_dict') else dict(info)
        except Exception as e:
            self.logger.error(f"Failed to fetch info for {ticker} from FRED: {e}")
            return {}

    def get_news(self, ticker: str) -> List[Dict[str, Any]]:
        """
        FRED doesn't provide news articles. Returns empty.
        """
        return []
