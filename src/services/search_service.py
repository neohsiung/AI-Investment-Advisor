"""
Search Service (Tavily Primary, DuckDuckGo Fallback)
搜尋服務 (Tavily 主要，DuckDuckGo 備援)
"""
from __future__ import annotations
import os
import time
import json
import asyncio
from typing import List, Dict, Tuple, Any, Optional, Callable
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.utils.cache import ResponseCache
from src.utils.circuit_breaker import circuit_breaker

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
        self._tavily_exhausted = False
        try:
            self.redis_cache = ResponseCache(ttl_hours=int(cache_ttl/3600))
        except Exception as e:
            self.redis_cache = None
            self.logger.warning(f"Redis cache init failed: {e}")
        
        # Initialize Settings
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        
        # Initialize Tavily (Primary)
        self.tavily_client = None
        # Priority: DB
        tavily_api_key = settings.get("source_tavily_api_key")
        tavily_enabled = str(settings.get("source_tavily_enabled", "true")).lower() == "true"
        
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

    @circuit_breaker(name="InternetSearch", failure_threshold=3, recovery_timeout=60)
    async def search_financial_context(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        """
        Search for financial context. Tries Tavily first, then DuckDuckGo.
        搜尋財經相關資訊。優先使用 Tavily，若失敗則使用 DuckDuckGo。
        """
        # Check Memory Cache
        if query in self.cache:
            ts, cached_results = self.cache[query]
            if time.time() - ts < self.cache_ttl:
                self.logger.info(f"Using memory cached results for: {query}")
                return cached_results
            else:
                del self.cache[query]

        # Check Redis Cache
        if self.redis_cache:
            cached_val = self.redis_cache.get("InternetSearch", query)
            if cached_val:
                try:
                    cached_results = json.loads(cached_val)
                    self.logger.info(f"Using Redis cached results for: {query}")
                    return cached_results
                except Exception as e:
                    self.logger.warning(f"Failed to parse Redis cache: {e}")

        self.logger.info(f"Searching web for: {query}")
        results = []

        # Try Tavily (Primary)
        if self.tavily_client and not self._tavily_exhausted:
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
                error_msg = str(e).lower()
                self.logger.warning(f"Tavily search failed: {error_msg}. Falling back to DuckDuckGo.")
                if any(k in error_msg for k in ["exceeds your plan", "limit", "429", "too many requests", "exhausted", "insufficient_balance"]):
                    self.logger.error("Tavily API quota exhausted. Disabling Tavily for this session.")
                    self._tavily_exhausted = True

        # Fallback to DuckDuckGo
        if self.ddgs:
            results = await self._search_duckduckgo(query, max_results)
        
        if results:
            self.cache[query] = (time.time(), results)
            if self.redis_cache:
                try:
                    self.redis_cache.set("InternetSearch", query, json.dumps(results))
                except (TypeError, ValueError):
                    pass
        return results

    async def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """
        DuckDuckGo fallback search with retry logic.
        DuckDuckGo 備援搜尋，降低重試次數避免阻塞 Dashboard。
        """
        retries = 1 # 降低重試次數，避免超時 (Reduce retries to avoid timeout)
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
                # 取得更詳細的錯誤名稱以防 str(e) 為空
                self.logger.warning(f"DuckDuckGo attempt {attempt+1} failed: {type(e).__name__} - {e}")
                
                # 若已達最後一次重試，不需要再 sleep
                if attempt < retries:
                    await asyncio.sleep(1) # 縮短等待時間 (Shorten wait time)

        if not results:
            self.logger.warning(f"DuckDuckGo search failed after retries. Last Error: {type(last_error).__name__} - {last_error}")
        return results

    @staticmethod
    async def _scrape_url(url: str, max_length: int = 2000) -> Optional[str]:
        """
        Lightweight URL scraper using local Playwright Scraper Service.
        Calls advisor_prod_scraper:3000 for JS-rendered content extraction.
        使用本地 Playwright Scraper 服務，調用 advisor_prod_scraper:3000 提取 JS 渲染內容。
        """
        import urllib.request
        import urllib.parse
        import json
        
        scraper_url = "http://advisor_prod_scraper:3000/scrape-raw"
        
        try:
            payload = {
                "url": url,
                "max_length": max_length
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                scraper_url, 
                data=data, 
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            if not scraper_url.lower().startswith(('http://', 'https://')):
                raise ValueError("Only http and https schemes are allowed for scraper_url")
            
            with urllib.request.urlopen(req, timeout=25) as response:  # nosec B310
                result = json.loads(response.read().decode('utf-8'))
                
                title = result.get("title", "") or ""
                plaintext = result.get("plaintext", "") or ""
                
                # Combine title + content for richer context
                if title and plaintext:
                    combined = f"{title}\n\n{plaintext}"
                else:
                    combined = plaintext or title
                
                return combined[:max_length] if len(combined) > max_length else combined
                
        except Exception as e:
            # Fallback to basic requests if scraper service fails
            try:
                import requests
                from bs4 import BeautifulSoup
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                
                main_tag = soup.find("main") or soup.find("article") or soup.find("div", class_=lambda x: x and "content" in x.lower())
                content = main_tag.get_text(separator="\n") if main_tag else soup.get_text(separator="\n")
                
                lines = [line.strip() for line in content.splitlines() if line.strip()]
                cleaned_text = " ".join(lines)
                
                return cleaned_text[:max_length] if len(cleaned_text) > max_length else cleaned_text
            except:
                return None

    async def get_ticker_moat_and_catalyst(self, ticker: str) -> List[Dict[str, str]]:
        """
        Convenience method to fetch Moat and Catalyst info for a ticker.
        快速取得特定股票的競爭優勢與催化劑資訊。
        """
        query = f"{ticker} stock competitive advantage moat catalyst 2025 analysis"
        return await self.search_financial_context(query, max_results=3)
