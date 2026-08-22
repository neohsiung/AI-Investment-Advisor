
import unittest
import time
from unittest.mock import MagicMock, patch
from src.services.search_service import InternetSearchService

class TestInternetSearchService(unittest.IsolatedAsyncioTestCase):
    """
    Test cases for InternetSearchService.
    測試 InternetSearchService 的各項功能。
    """
    
    async def test_search_cache_hit(self):
        """Test that cache is used for repeated queries."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            with patch('src.services.search_service.SettingsService'):
                service = InternetSearchService(user_id="test_user", cache_ttl=10)
            
            # Mock internal ddgs
            service.ddgs = MagicMock()
            service.ddgs.text.return_value = [{'title': 'A', 'body': 'B', 'href': 'C'}]
            service.tavily_client = None  # Force DuckDuckGo path
            
            # 1. First Call
            res1 = await service.search_financial_context("query", max_results=3)
            
            # 2. Second Call (Immediate)
            res2 = await service.search_financial_context("query", max_results=3)
            
            self.assertEqual(res1, res2)
            # Should be called once (second is cached)
            self.assertEqual(service.ddgs.text.call_count, 1)

    async def test_search_cache_expiry(self):
        """Test that cache expires after TTL."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            with patch('src.services.search_service.SettingsService'):
                service = InternetSearchService(user_id="test_user", cache_ttl=0.1)
            
            service.ddgs = MagicMock()
            service.ddgs.text.return_value = [{'title': 'A', 'body': 'B', 'href': 'C'}]
            service.tavily_client = None
            
            # 1. First Call
            await service.search_financial_context("query", max_results=3)
            
            # Wait for expiry
            time.sleep(0.2)
            
            # 2. Second Call
            await service.search_financial_context("query", max_results=3)
            
            # Should be called twice (cache expired)
            self.assertEqual(service.ddgs.text.call_count, 2)

    async def test_get_ticker_moat(self):
        """Test convenience method for ticker moat search."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            with patch('src.services.search_service.SettingsService'):
                service = InternetSearchService(user_id="test_user")
            
            # Must also patch search_financial_context with AsyncMock or properly mock it
            from unittest.mock import AsyncMock
            with patch.object(service, 'search_financial_context', new_callable=AsyncMock) as mock_search:
                await service.get_ticker_moat_and_catalyst("AAPL")
                mock_search.assert_called_with("AAPL stock competitive advantage moat catalyst 2025 analysis", max_results=3)

    async def test_tavily_primary(self):
        """Test that Tavily is used when available."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': 'test_key'}):
            with patch('src.services.search_service.SettingsService'):
                service = InternetSearchService(user_id="test_user")
            
            # Mock the tavily client after initialization
            mock_client = MagicMock()
            mock_client.search.return_value = {
                "results": [{"title": "T1", "url": "U1", "content": "C1"}]
            }
            service.tavily_client = mock_client
            
            res = await service.search_financial_context("test query")
            
            mock_client.search.assert_called_once()
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["title"], "T1")

if __name__ == '__main__':
    unittest.main()


class TestSearchBackendAvailability(unittest.IsolatedAsyncioTestCase):
    """
    The DuckDuckGo fallback was dead in production from httpx 0.28 until
    2026-08-13: duckduckgo-search 3.9.3 passed httpx's removed `proxies` kwarg,
    so `DDGS()` raised `TypeError` on construction 457 times per 6h. Tavily was
    the only backend, while the class docstring, the log line and the fallback
    branch all said otherwise. These tests pin the two things that made it
    invisible: a real DDGS must be constructible, and a service with no backend
    at all must say so at error level.
    此備援自 httpx 0.28 起即失效，而程式與日誌都聲稱備援存在。
    """

    def _service(self, **kwargs):
        with patch('src.services.search_service.SettingsService'):
            return InternetSearchService(user_id="test_user", **kwargs)

    def test_ddgs_is_actually_constructible(self):
        """Regression: `DDGS()` used to raise TypeError against modern httpx.
        Construction only — no network call."""
        from ddgs import DDGS
        self.assertIsNotNone(DDGS())

    def test_fallback_is_wired_up_after_init(self):
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            service = self._service()
        self.assertIsNotNone(
            service.ddgs,
            "DuckDuckGo fallback failed to initialize — Tavily would be the only backend",
        )

    def test_no_usable_backend_is_reported_at_error_level(self):
        """Zero backends means every search returns [] , which a caller cannot
        tell apart from 'nothing found'. That must not be a warning."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}), \
             patch('src.services.search_service.SettingsService'), \
             patch('ddgs.DDGS', side_effect=RuntimeError("ddgs broken")), \
             patch('src.services.search_service.setup_logger') as logger_factory:
            logger = MagicMock()
            logger_factory.return_value = logger
            service = InternetSearchService(user_id="test_user")

        self.assertIsNone(service.ddgs)
        self.assertIsNone(service.tavily_client)
        self.assertTrue(
            any("NO usable backend" in str(c) for c in logger.error.call_args_list),
            f"expected an error-level report, got: {logger.error.call_args_list}",
        )
