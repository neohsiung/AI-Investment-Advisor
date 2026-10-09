import os
import pandas as pd
import fredapi
import logging
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
            self.logger.warning("FRED_API_KEY not found in database settings.")
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

        # In-memory macro caching (6 hours TTL) to conserve API quota
        self._macro_cache: Dict[str, Any] = {}
        self._macro_cache_time: float = 0.0
        self._CACHE_TTL_SECONDS: int = 21600  # 6 hours

    def get_macro_indicators(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetches key macro indicators like GDP, CPI, and Yield Spreads.
        獲取關鍵宏觀指標，如 GDP、CPI 與殖利率利差。
        """
        if not self.client:
            self.logger.warning("FRED client not initialized (missing API key). Returning empty data.")
            return {}

        import time
        import json
        now = time.time()
        if self._macro_cache and (now - self._macro_cache_time < self._CACHE_TTL_SECONDS):
            self.logger.debug("Returning cached macro indicators from memory.")
            return self._macro_cache

        # Check Redis distributed cache (1 hour TTL)
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                cached_str = r.get("market_data:fred_indicators")
                if cached_str:
                    cached_data = json.loads(cached_str)
                    self._macro_cache = cached_data
                    self._macro_cache_time = now
                    self.logger.info("Returning cached macro indicators from Redis.")
                    return cached_data
        except Exception as r_err:
            self.logger.debug(f"Redis macro cache check skipped: {r_err}")

        # Quota Guard: Ensure <= 60% capacity utilization
        from src.infrastructure.governance.quota_governor import ExternalQuotaGovernor
        governor = ExternalQuotaGovernor.get_instance()
        if not governor.can_acquire("fred"):
            if self._macro_cache:
                self.logger.info("FRED 60% capacity cap reached; returning stale cached macro data.")
                return self._macro_cache
            self.logger.warning("FRED 60% capacity cap reached and no cache available.")
            return {}

        indicators = {
            "GDP": "GDP",
            "CPI": "CPIAUCSL",
            "Unemployment": "UNRATE",
            "FedFunds": "FEDFUNDS",
            "10Y2Y_Spread": "T10Y2Y",
            "NFP": "PAYEMS",
            "Industrial_Production": "INDPRO",
            "Initial_Claims": "ICSA",
            "VIX": "VIXCLS",
            "TNX_10Y": "DGS10",
        }

        result = {}
        success_count = 0
        for name, series_id in indicators.items():
            try:
                series = self.client.get_series(series_id, limit=12, sort_order='desc')
                success_count += 1
                if not series.empty:
                    valid_series = series.dropna()
                    if not valid_series.empty:
                        current = valid_series.iloc[0]
                        prev = valid_series.iloc[1] if len(valid_series) > 1 else current
                        trend = "Up" if current > prev else "Down"
                        
                        result[name] = {
                            "value": float(current),
                            "date": valid_series.index[0].strftime("%Y-%m-%d"),
                            "trend": trend,
                            "history": valid_series.tolist()[:12]
                        }
            except Exception as ser_err:
                self.logger.debug(f"FRED series '{name}' ({series_id}) fetch skipped: {ser_err}")

        # If every call failed with exception (e.g. API error or network failure), return empty dict
        if success_count == 0:
            return {}

        # Labor Market Dynamic Cooling Model (Milestone 1.3)
        # Evaluate if employment is cooling vs freezing based on NFP (PAYEMS) trend
        nfp_data = result.get("NFP", {}).get("history", [])
        labor_cooling_signal = False
        if len(nfp_data) >= 3:
            month1_growth = nfp_data[0] - nfp_data[1]  # Most recent
            month2_growth = nfp_data[1] - nfp_data[2]
            if 0 < month1_growth < month2_growth:
                labor_cooling_signal = True

        result["Labor_Cooling_Indicator"] = {
            "value": labor_cooling_signal,
            "date": result.get("NFP", {}).get("date", ""),
            "trend": "Cooling" if labor_cooling_signal else "Stable/Freezing"
        }
        
        if result:
            governor.record_usage("fred", count=len(indicators))
            self._macro_cache = result
            self._macro_cache_time = now
            try:
                from src.infrastructure.cache.redis_client import get_redis_sync
                r = get_redis_sync(decode_responses=True)
                if r:
                    r.setex("market_data:fred_indicators", int(self._CACHE_TTL_SECONDS), json.dumps(result))
            except Exception as r_err:
                self.logger.debug(f"Failed to cache fred indicators in Redis: {r_err}")

        return result
