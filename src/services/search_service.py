
import logging
from duckduckgo_search import DDGS
import time
from src.utils.logger import setup_logger

class InternetSearchService:
    def __init__(self, cache_ttl=86400): # 24 hours TTL
        self.logger = setup_logger("InternetSearch")
        self.ddgs = DDGS()
        self.cache = {} # Dict[query, (timestamp, results)]
        self.cache_ttl = cache_ttl

    def search_financial_context(self, query, max_results=3):
        """
        Search for financial context with strict constraints and caching.
        搜尋財經相關背景資訊，並具備嚴格限制與快取機制。
        
        Args:
            query (str): The search query. 搜尋關鍵字。
            max_results (int): Limit results. 限制結果數量。
        Returns:
            list: List of result dictionaries. 結果列表。
        """
        # Check Cache
        if query in self.cache:
            ts, cached_results = self.cache[query]
            if time.time() - ts < self.cache_ttl:
                self.logger.info(f"Using cached search results for: {query}")
                return cached_results
            else:
                del self.cache[query] # Expired

        try:
            self.logger.info(f"Searching web for: {query}")
            results = list(self.ddgs.text(query, max_results=max_results, timelimit='y'))
            
            if not results:
                self.logger.warning(f"No results found for {query}")
                return []
                
            filtered = []
            for r in results:
                filtered.append({
                    "title": r.get("title"),
                    "link": r.get("href"),
                    "snippet": r.get("body")
                })
            
            # Save to Cache
            self.cache[query] = (time.time(), filtered)
            
            return filtered

        except Exception as e:
            self.logger.error(f"Search failed for {query}: {e}")
            return []

    def get_ticker_moat_and_catalyst(self, ticker):
        """
        Convenience method to fetch Moat and Catalyst info for a ticker.
        """
        query = f"{ticker} stock competitive advantage moat catalyst 2025 analysis"
        return self.search_financial_context(query, max_results=3)
