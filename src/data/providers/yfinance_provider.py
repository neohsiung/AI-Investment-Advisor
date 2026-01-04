import yfinance as yf
import pandas as pd
from typing import Dict, Any, List
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger

class YFinanceProvider(MarketDataProvider):
    """
    YFinance Provider (Wrapper around yfinance).
    Acts as the legacy/backup solution.
    """
    def __init__(self):
        self.logger = setup_logger("YFinanceProvider")

    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        if not tickers: return {}
        try:
            data = yf.download(tickers, period="1d", auto_adjust=True, progress=False)
            prices = {}
            
            if len(tickers) == 1:
                ticker = tickers[0]
                if not data.empty:
                    val = data['Close'].iloc[-1]
                    if isinstance(val, pd.Series): val = val.item()
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
            self.logger.error(f"YFinance fetch_current_prices error: {e}")
            return {}

    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        try:
            p = period
            if days:
                p = f"{days + 20}d" 
            return yf.download(ticker, period=p, progress=False, auto_adjust=True)
        except Exception as e:
            self.logger.error(f"YFinance fetch_history error: {e}")
            return pd.DataFrame()

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            t = yf.Ticker(ticker)
            news = t.news
            formatted = []
            for n in news[:limit]:
                # Handle new yfinance news structure (nested in 'content')
                content = n.get('content', {})
                # Some older versions might be flat, so try both or check structure
                title = content.get('title') if 'content' in n else n.get('title')
                
                # Link extraction
                link = n.get('link')
                if not link and 'clickThroughUrl' in content:
                    link = content['clickThroughUrl'].get('url')
                
                # Publisher
                publisher = n.get('publisher')
                if not publisher and 'provider' in content:
                    publisher = content['provider'].get('displayName')

                formatted.append({
                     "title": title,
                     "link": link,
                     "publisher": publisher
                 })
            return formatted
        except Exception as e:
            self.logger.error(f"YFinance fetch_news error: {e}")
            return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            return {
                "market_cap": info.get('marketCap'),
                "trailing_pe": info.get('trailingPE'),
                "forward_pe": info.get('forwardPE'),
                "sector": info.get('sector'),
                "industry": info.get('industry')
            }
        except Exception as e:
            self.logger.error(f"YFinance fetch_info error: {e}")
            return {}
