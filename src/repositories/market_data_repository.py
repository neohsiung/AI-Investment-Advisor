import yfinance as yf
import pandas as pd
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.utils.logger import setup_logger

class IMarketDataRepository(ABC):
    """
    Interface for Market Data Repository.
    市場數據儲存庫介面。
    """
    @abstractmethod
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetch latest closing prices for a list of tickers.
        取得一系列標的的最新收盤價。
        """
        pass

    @abstractmethod
    def fetch_history(self, ticker: str, period: str = "1y", days: Optional[int] = None) -> pd.DataFrame:
        """
        Fetch historical data for a ticker.
        取得標的的歷史數據。
        """
        pass

    @abstractmethod
    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch news for a specific ticker.
        取得特定標體的新聞。
        """
        pass

    @abstractmethod
    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch fundamental information for a ticker.
        取得標底的基本面資訊。
        """
        pass

class AlchemyMarketDataRepository(IMarketDataRepository):
    """
    Repository for fetching market data from external sources (e.g., yfinance).
    從外部來源（如 yfinance）獲取市場數據的儲存庫。
    """
    def __init__(self):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        self.logger = setup_logger("MarketDataRepo")

    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetch latest closing prices for a list of tickers.
        取得一系列標的的最新收盤價。
        """
        if not tickers:
            return {}
        
        try:
            data = yf.download(tickers, period="1d", auto_adjust=True, progress=False)
            prices = {}
            
            if len(tickers) == 1:
                ticker = tickers[0]
                if not data.empty:
                    val = data['Close'].iloc[-1]
                    # Handle Series vs Scalar
                    if isinstance(val, pd.Series):
                        val = val.item()
                    prices[ticker] = float(val)
            else:
                if not data.empty and 'Close' in data.columns:
                    close_data = data['Close']
                    for ticker in tickers:
                        if ticker in close_data.columns:
                            val = close_data[ticker].iloc[-1]
                            if pd.notna(val):
                                prices[ticker] = float(val)
            return prices
        except Exception as e:
            self.logger.error(f"Error fetching prices: {e}")
            return {}

    def fetch_history(self, ticker: str, period: str = "1y", days: Optional[int] = None) -> pd.DataFrame:
        """
        Fetch historical data for a ticker.
        取得標的的歷史數據。
        """
        try:
            p = period
            if days:
                p = f"{days + 20}d" # Fetch extra for indicators
            
            df = yf.download(ticker, period=p, progress=False, auto_adjust=True)
            return df
        except Exception as e:
            self.logger.error(f"Error fetching history for {ticker}: {e}")
            return pd.DataFrame()

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch news for a specific ticker.
        取得特定標體的新聞。
        """
        try:
            t = yf.Ticker(ticker)
            news = t.news
            return news[:limit] if news else []
        except Exception as e:
            self.logger.error(f"Error fetching news for {ticker}: {e}")
            return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch fundamental information for a ticker.
        取得標底的基本面資訊。
        """
        try:
            t = yf.Ticker(ticker)
            return t.info
        except Exception as e:
            self.logger.error(f"Error fetching info for {ticker}: {e}")
            return {}

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyMarketDataRepository
