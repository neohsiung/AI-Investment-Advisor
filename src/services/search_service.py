"""
Search Service (Tavily Primary, DuckDuckGo Fallback)
搜尋服務 (Tavily 主要，DuckDuckGo 備援)
"""
from __future__ import annotations
import os
import time
from typing import List, Dict, Any, Optional, Tuple
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService

class InternetSearchService:
    """
    Internet Search Service with Tavily as primary and DuckDuckGo as fallback.
    網路搜尋服務：Tavily 為主要引擎，DuckDuckGo 為備援。
    """
    def __init__(self, cache_ttl: int = 86400, user_id: str = None, settings_service: SettingsService = None):
        """
        Initialize the search service.
        初始化搜尋服務。
        """
        self.logger = setup_logger("InternetSearch")
        self.cache: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
        self.cache_ttl = cache_ttl
        
        # Initialize Settings
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        
        # Initialize Tavily (Primary)
        self.tavily_client = None
        # Priority: DB -> Env
        tavily_api_key = settings.get("source_tavily_api_key") or os.getenv("TAVILY_API_KEY")
        tavily_enabled = settings.get("source_tavily_enabled", "true") == "true"
        
        if tavily_api_key and tavily_enabled:
            try:
                from tavily import TavilyClient
                self.tavily_client = TavilyClient(api_key=tavily_api_key)
                self.logger.info("Tavily Search initialized successfully.")
            except ImportError:
                self.logger.warning("tavily-python not installed. Run: pip install tavily-python")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Tavily: {e}")
        else:
            self.logger.warning("TAVILY_API_KEY not found. Falling back to DuckDuckGo.")
        
        # Initialize DuckDuckGo (Fallback)
        self.ddgs = None
        try:
            from duckduckgo_search import DDGS
            self.ddgs = DDGS()
        except ImportError:
            self.logger.warning("duckduckgo-search not installed.")
        except Exception as e:
            self.logger.warning(f"Failed to initialize DuckDuckGo: {e}")

    def search_financial_context(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        """
        Search for financial context. Tries Tavily first, then DuckDuckGo.
        搜尋財經相關資訊。優先使用 Tavily，若失敗則使用 DuckDuckGo。
        """
        # Check Cache
        if query in self.cache:
            ts, cached_results = self.cache[query]
            if time.time() - ts < self.cache_ttl:
                self.logger.info(f"Using cached search results for: {query}")
                return cached_results
            else:
                del self.cache[query]

        self.logger.info(f"Searching web for: {query}")
        results = []

        # Try Tavily (Primary)
        if self.tavily_client:
            try:
                response = self.tavily_client.search(query=query, max_results=max_results)
                if response and "results" in response:
                    for r in response["results"]:
                        results.append({
                            "title": r.get("title"),
                            "link": r.get("url"),
                            "snippet": r.get("content", "")
                        })
                    if results:
                        self.cache[query] = (time.time(), results)
                        return results
            except Exception as e:
                self.logger.warning(f"Tavily search failed: {e}. Falling back to DuckDuckGo.")

        # Fallback to DuckDuckGo
        if self.ddgs:
            results = self._search_duckduckgo(query, max_results)
        
        if results:
            self.cache[query] = (time.time(), results)
        return results

    def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """
        DuckDuckGo fallback search with retry logic.
        DuckDuckGo 備援搜尋，含重試邏輯。
        """
        retries = 2
        results = []
        last_error = None

        for attempt in range(retries + 1):
            try:
                gen = self.ddgs.text(query, max_results=max_results)
                if gen:
                    raw_results = list(gen)
                    for r in raw_results:
                        results.append({
                            "title": r.get("title"),
                            "link": r.get("href"),
                            "snippet": r.get("body", r.get("snippet", ""))
                        })
                if results:
                    break
            except Exception as e:
                last_error = e
                self.logger.warning(f"DuckDuckGo attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1))

        if not results:
            self.logger.warning(f"DuckDuckGo search failed after retries. Last Error: {last_error}")
        return results

    def get_ticker_moat_and_catalyst(self, ticker: str) -> List[Dict[str, str]]:
        """
        Convenience method to fetch Moat and Catalyst info for a ticker.
        快速取得特定股票的競爭優勢與催化劑資訊。
        """
        query = f"{ticker} stock competitive advantage moat catalyst 2025 analysis"
        return self.search_financial_context(query, max_results=3)
