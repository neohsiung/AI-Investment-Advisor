from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, Any, List, Optional
import pandas as pd

class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.
    市場數據提供者的抽象基類。 
    
    Defines the interface for fetching price, news, and fundamental data.
    定義了獲取價格、新聞與基本面數據的介面。
    """

    @abstractmethod
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetch real-time or delayed current prices.
        獲取即時或延遲的目前價格。
        """
        pass

    @abstractmethod
    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.
        獲取歷史 OHLCV 數據。
        """
        pass

    @abstractmethod
    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch news for a ticker.
        獲取標的的新聞。
        """
        pass

    @abstractmethod
    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch fundamental info (market cap, PE, etc.).
        獲取基本面資訊（市值、市盈率等）。
        """
        pass
