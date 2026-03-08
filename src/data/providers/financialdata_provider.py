import requests
import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional
from src.data.providers.base import MarketDataProvider
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.utils.tracing import trace_external_call

class FinancialDataProvider(MarketDataProvider):
    """
    FinancialData.Net Data Provider.
    FinancialData.Net 數據提供者。
    
    Provides stock prices, insider trading, and ETF holdings.
    提供股價、內線交易與 ETF 持倉數據。
    """
    def __init__(self, api_key: str = None, user_id: str = None, settings_service: SettingsService = None):
        """
        Initialize the provider.
        """
        self.logger = setup_logger("FinancialDataProvider")
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        
        # Load API key from settings
        settings = self.settings_service.get_all_settings()
        self.api_key = api_key or settings.get("financialdata_api_key")
        self.base_url = "https://financialdata.net/api/v1"
        
        if not self.api_key:
            self.logger.warning("FINANCIALDATA_API_KEY not found in settings.")

    @trace_external_call("financialdata")
    def fetch_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetch current stock prices. 
        Note: The API returns the latest available price record.
        """
        if not self.api_key or not tickers:
            return {}
        
        prices = {}
        for ticker in tickers:
            try:
                # API expects 'identifier' for the symbol
                url = f"{self.base_url}/stock-prices"
                params = {
                    "identifier": ticker,
                    "key": self.api_key,
                    "limit": 1  # Only need the latest
                }
                resp = requests.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list):
                        # Assuming the first item is the most recent
                        prices[ticker] = float(data[0].get('close', 0))
                elif resp.status_code == 429:
                    self.logger.error("FinancialData.Net Rate limit exceeded (300/day).")
                    break
            except Exception as e:
                self.logger.error(f"FinancialData error for {ticker}: {e}")
                
        return prices

    def fetch_history(self, ticker: str, period: str = "1y", days: int = None) -> pd.DataFrame:
        """
        Fetch historical price data.
        """
        if not self.api_key:
            return pd.DataFrame()
        
        try:
            url = f"{self.base_url}/stock-prices"
            params = {
                "identifier": ticker,
                "key": self.api_key,
                "limit": days or 252  # Default to ~1 year of trading days
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if not data:
                    return pd.DataFrame()
                
                df = pd.DataFrame(data)
                # Map fields: 'date', 'open', 'high', 'low', 'close', 'volume'
                df['Date'] = pd.to_datetime(df['date'])
                df.set_index('Date', inplace=True)
                df = df.rename(columns={
                    'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'
                })
                # Sort ascending
                df = df.sort_index()
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception as e:
            self.logger.error(f"FinancialData history error for {ticker}: {e}")
            
        return pd.DataFrame()

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch press releases or news if supported.
        FinancialData.Net news endpoint might vary.
        """
        # Placeholder as the focus is on specialized data
        return []

    def fetch_info(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch basic company information.
        """
        if not self.api_key:
            return {}
        try:
            url = f"{self.base_url}/company-information"
            params = {"identifier": ticker, "key": self.api_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list):
                    item = data[0]
                    return {
                        "name": item.get('name'),
                        "sector": item.get('sector'),
                        "industry": item.get('industry'),
                        "description": item.get('description'),
                        "exchange": item.get('exchange')
                    }
        except Exception as e:
            self.logger.error(f"FinancialData info error for {ticker}: {e}")
        return {}

    # --- Specialized Functions ---

    def fetch_insider_trading(self, ticker: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch insider transactions.
        """
        if not self.api_key:
            return []
        try:
            url = f"{self.base_url}/insider-transactions"
            params = {"identifier": ticker, "key": self.api_key, "limit": limit}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self.logger.error(f"FinancialData insider error for {ticker}: {e}")
        return []

    def fetch_etf_holdings(self, etf_ticker: str) -> List[Dict[str, Any]]:
        """
        Fetch holdings for a specific ETF.
        """
        if not self.api_key:
            return []
        try:
            url = f"{self.base_url}/etf-holdings"
            params = {"identifier": etf_ticker, "key": self.api_key}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self.logger.error(f"FinancialData ETF holdings error for {etf_ticker}: {e}")
        return []
