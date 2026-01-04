
import unittest
import time
from unittest.mock import MagicMock, patch
from src.services.search_service import InternetSearchService

class TestInternetSearchService(unittest.TestCase):
    """
    Test cases for InternetSearchService.
    測試 InternetSearchService 的各項功能。
    """
    
    def test_search_cache_hit(self):
        """Test that cache is used for repeated queries."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            service = InternetSearchService(cache_ttl=10)
            
            # Mock internal ddgs
            service.ddgs = MagicMock()
            service.ddgs.text.return_value = [{'title': 'A', 'body': 'B', 'href': 'C'}]
            service.tavily_client = None  # Force DuckDuckGo path
            
            # 1. First Call
            res1 = service.search_financial_context("query")
            
            # 2. Second Call (Immediate)
            res2 = service.search_financial_context("query")
            
            self.assertEqual(res1, res2)
            # Should be called once (second is cached)
            self.assertEqual(service.ddgs.text.call_count, 1)

    def test_search_cache_expiry(self):
        """Test that cache expires after TTL."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            service = InternetSearchService(cache_ttl=0.1)
            
            service.ddgs = MagicMock()
            service.ddgs.text.return_value = [{'title': 'A', 'body': 'B', 'href': 'C'}]
            service.tavily_client = None
            
            # 1. First Call
            service.search_financial_context("query")
            
            # Wait for expiry
            time.sleep(0.2)
            
            # 2. Second Call
            service.search_financial_context("query")
            
            # Should be called twice (cache expired)
            self.assertEqual(service.ddgs.text.call_count, 2)

    def test_get_ticker_moat(self):
        """Test convenience method for ticker moat search."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            service = InternetSearchService()
            with patch.object(service, 'search_financial_context') as mock_search:
                service.get_ticker_moat_and_catalyst("AAPL")
                mock_search.assert_called_with("AAPL stock competitive advantage moat catalyst 2025 analysis", max_results=3)

    def test_tavily_primary(self):
        """Test that Tavily is used when available."""
        with patch.dict('os.environ', {'TAVILY_API_KEY': 'test_key'}):
            service = InternetSearchService()
            
            # Mock the tavily client after initialization
            mock_client = MagicMock()
            mock_client.search.return_value = {
                "results": [{"title": "T1", "url": "U1", "content": "C1"}]
            }
            service.tavily_client = mock_client
            
            res = service.search_financial_context("test query")
            
            mock_client.search.assert_called_once()
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["title"], "T1")

if __name__ == '__main__':
    unittest.main()
