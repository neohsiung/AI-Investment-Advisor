from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import pandas as pd

class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.
    Defines the interface for fetching price, news, and fundamental data.
    """

    @abstractmethod
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """Fetch real-time or delayed current prices."""
        pass

    @abstractmethod
    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """Fetch historical OHLCV data."""
        pass

    @abstractmethod
    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch news for a ticker."""
        pass

    @abstractmethod
    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """Fetch fundamental info (market cap, PE, etc.)."""
        pass
