import os
import requests
from typing import Dict, List, Any, Optional
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.utils.tracing import trace_external_call

class ReadwiseProvider:
    """
    Readwise API Provider for fetching user highlights.
    Readwise 數據提供者，用於獲取用戶的畫線與筆記。
    """
    def __init__(self, user_id: str = "system", settings_service: SettingsService = None):
        self.logger = setup_logger("ReadwiseProvider")
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        self.base_url = "https://readwise.io/api/v2/"
        
    def _get_api_key(self) -> str:
        settings = self.settings_service.get_all_settings()
        # UI saves it as source_readwise_api_key
        return settings.get("source_readwise_api_key") or settings.get("READWISE_API_KEY") or os.getenv("READWISE_API_KEY", "")

    @trace_external_call("readwise")
    def fetch_highlights(self, updated_after: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetches a list of highlights from Readwise.
        獲取 Readwise 畫線筆記清單。
        updated_after: ISO 8601 date string (e.g. '2024-01-01T00:00:00Z')
        """
        api_key = self._get_api_key()
        if not api_key:
            self.logger.warning("Readwise API key not found in settings or environment")
            return []

        headers = {"Authorization": f"Token {api_key}"}
        params = {}
        if updated_after:
            params["updated__gt"] = updated_after

        results = []
        next_page = f"{self.base_url}highlights/"
        
        try:
            while next_page:
                resp = requests.get(next_page, headers=headers, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                
                results.extend(data.get("results", []))
                next_page = data.get("next")
                params = {} # params are included in the next_page url returned by Readwise
                
        except Exception as e:
            self.logger.error(f"Failed to fetch Readwise highlights: {e}")
            
        return results

    @trace_external_call("readwise")
    def fetch_highlight_detail(self, highlight_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches the detail for a single highlight.
        取得單筆畫線的詳情。
        """
        api_key = self._get_api_key()
        if not api_key:
            return None
            
        headers = {"Authorization": f"Token {api_key}"}
        url = f"{self.base_url}highlights/{highlight_id}/"
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch detail for highlight {highlight_id}: {e}")
            return None
