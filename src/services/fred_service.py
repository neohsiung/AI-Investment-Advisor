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
        
        fred_api_key = settings.get("source_fred_api_key")
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
            "10Y2Y_Spread": "T10Y2Y",
            "ISM_Mfg_PMI": "NAPM", # ISM Manufacturing PMI
            "ISM_Svc_PMI": "NM_NMF", # ISM Services PMI
            "NFP": "PAYEMS", # Non-Farm Payrolls
            "ISM_Mfg_Employment": "ISM_MAN_EMP", 
            "ISM_Mfg_Inventory": "ISM_MAN_INV"
        }

        result = {}
        try:
            for name, series_id in indicators.items():
                # Fetch last 12 periods to see trend and calculate scorecard
                series = self.client.get_series(series_id, limit=12, sort_order='desc')
                if not series.empty:
                    current = series.iloc[0]
                    prev = series.iloc[1] if len(series) > 1 else current
                    trend = "Up" if current > prev else "Down"
                    
                    result[name] = {
                        "value": float(current),
                        "date": series.index[0].strftime("%Y-%m-%d"),
                        "trend": trend,
                        "history": series.tolist()[:12] # Keep limited history for scorecard logic
                    }
                    
            # Labor Market Dynamic Cooling Model (Milestone 1.3)
            # Evaluate if employment is cooling vs freezing based on NFP (PAYEMS) trend
            nfp_data = result.get("NFP", {}).get("history", [])
            labor_cooling_signal = False
            if len(nfp_data) >= 3:
                 # Cooling defined as positive but shrinking NFP growth over last 3 months
                 # (Just an approximation since PAYEMS is total level, diff is monthly job growth)
                 month1_growth = nfp_data[0] - nfp_data[1]  # Most recent
                 month2_growth = nfp_data[1] - nfp_data[2]
                 if 0 < month1_growth < month2_growth:
                      labor_cooling_signal = True
            
            result["Labor_Cooling_Indicator"] = {
                 "value": labor_cooling_signal,
                 "date": result.get("NFP", {}).get("date", ""),
                 "trend": "Cooling" if labor_cooling_signal else "Stable/Freezing"
            }
                    
        except Exception as e:
            self.logger.error(f"Error fetching FRED data: {e}")
        
        return result
