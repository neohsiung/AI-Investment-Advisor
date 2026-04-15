
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
