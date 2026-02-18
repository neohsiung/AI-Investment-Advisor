import os
import pandas as pd
import fredapi
import logging
from typing import Dict, List, Any, Union
from src.utils.logger import setup_logger

from src.services.settings_service import SettingsService

class FredService:
    """
    FRED (Federal Reserve Economic Data) Service for fetching macro indicators.
    FRED (聯邦儲備經濟數據) 服務，用於獲取宏觀經濟指標。
    """
    def __init__(self, user_id: str = None, settings_service: Any = None):
        """
        Initialize the FRED service.
        初始化 FRED 服務。
        """
        self.logger = setup_logger("FredService")
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        
        fred_api_key = settings.get("source_fred_api_key") or os.getenv("FRED_API_KEY")
        self.client = None
        if not fred_api_key:
            self.logger.warning("FRED_API_KEY not found in environment or database.")
            self.client = None
            return

        try:
            import fredapi
            self.client = fredapi.Fred(api_key=fred_api_key)
            self.logger.info("✓ FRED client initialized successfully.")
        except ImportError:
            self.logger.error("fredapi package not found. Please install it.")
            self.client = None
        except Exception as e:
            self.logger.error(f"Failed to initialize FRED client: {e}")

    def get_macro_indicators(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetches key macro indicators like GDP, CPI, and Yield Spreads.
        獲取關鍵宏觀指標，如 GDP、CPI 與殖利率利差。
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
