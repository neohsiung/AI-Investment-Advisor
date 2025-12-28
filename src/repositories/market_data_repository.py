
import yfinance as yf
import pandas as pd
from typing import Dict, Any, List, Optional
from src.utils.logger import setup_logger

class MarketDataRepository:
    """
    Repository for fetching market data from external sources (e.g., yfinance).
    Implements the Interface Adapter layer.
    """
    def __init__(self):
        self.logger = setup_logger("MarketDataRepo")

    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """Fetch latest closing prices for a list of tickers."""
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
                    prices[ticker] = val
            else:
                if not data.empty and 'Close' in data.columns:
                    close_data = data['Close']
                    for ticker in tickers:
                        if ticker in close_data.columns:
                            val = close_data[ticker].iloc[-1]
                            if pd.notna(val):
                                prices[ticker] = val
            return prices
        except Exception as e:
            self.logger.error(f"Error fetching prices: {e}")
            return {}

    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """Fetch historical data."""
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
        """Fetch news for a ticker."""
        try:
            t = yf.Ticker(ticker)
            news = t.news
            return news[:limit] if news else []
        except Exception as e:
            self.logger.error(f"Error fetching news for {ticker}: {e}")
            return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """Fetch fundamental info."""
        try:
            t = yf.Ticker(ticker)
            return t.info
        except Exception as e:
            self.logger.error(f"Error fetching info for {ticker}: {e}")
            return {}
