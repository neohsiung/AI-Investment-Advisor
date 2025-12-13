import os
import pandas as pd
from fredapi import Fred
from src.utils.logger import setup_logger

class FredService:
    def __init__(self, api_key=None):
        self.logger = setup_logger("FredService")
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = Fred(api_key=self.api_key)
            except Exception as e:
                self.logger.error(f"Failed to initialize FRED client: {e}")

    def get_macro_indicators(self):
        """
        Fetches key macro indicators: GDP, CPI, Unemployment, Yield Spread.
        Returns a dictionary with current values and trends.
        """
        if not self.client:
            self.logger.warning("FRED client not initialized (missing API key). Returning empty data.")
            return {}

        indicators = {
            "GDP": "GDP",
            "CPI": "CPIAUCSL",
            "Unemployment": "UNRATE",
            "FedFunds": "FEDFUNDS",
            "10Y2Y_Spread": "T10Y2Y"
        }

        result = {}
        try:
            for name, series_id in indicators.items():
                # Fetch last 1 year to see trend
                series = self.client.get_series(series_id, limit=12, sort_order='desc')
                if not series.empty:
                    current = series.iloc[0]
                    prev = series.iloc[1] if len(series) > 1 else current
                    trend = "Up" if current > prev else "Down"
                    
                    result[name] = {
                        "value": float(current),
                        "date": series.index[0].strftime("%Y-%m-%d"),
                        "trend": trend
                    }
        except Exception as e:
            self.logger.error(f"Error fetching FRED data: {e}")
        
        return result
