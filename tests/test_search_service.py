
import unittest
import time
from unittest.mock import MagicMock, patch
from src.services.search_service import InternetSearchService

class TestInternetSearchService(unittest.TestCase):
    def setUp(self):
        self.service = InternetSearchService(cache_ttl=1) # 1 sec TTL for testing

    @patch('src.services.search_service.DDGS')
    def test_search_cache_hit(self, MockDDGS):
        # Mock Search
        mock_ddgs_instance = MockDDGS.return_value
        mock_ddgs_instance.text.return_value = [{'title': 'A', 'body': 'B', 'href': 'C'}]
        
        service = InternetSearchService(cache_ttl=10)
        
        # 1. First Call
        res1 = service.search_financial_context("query")
        
        # 2. Second Call (Immediate)
        res2 = service.search_financial_context("query")
        
        self.assertEqual(res1, res2)
        # Should be called once
        self.assertEqual(mock_ddgs_instance.text.call_count, 1)

    @patch('src.services.search_service.DDGS')
    def test_search_cache_expiry(self, MockDDGS):
        mock_ddgs_instance = MockDDGS.return_value
        mock_ddgs_instance.text.return_value = [{'title': 'A', 'body': 'B', 'href': 'C'}]
        
        service = InternetSearchService(cache_ttl=0.1)
        
        # 1. First Call
        service.search_financial_context("query")
        
        # Wait for expiry
        time.sleep(0.2)
        
        # 2. Second Call
        service.search_financial_context("query")
        
        # Should be called twice
        self.assertEqual(mock_ddgs_instance.text.call_count, 2)

    def test_get_ticker_moat(self):
        with patch.object(self.service, 'search_financial_context') as mock_search:
            self.service.get_ticker_moat_and_catalyst("AAPL")
            mock_search.assert_called_with("AAPL stock competitive advantage moat catalyst 2025 analysis", max_results=3)

if __name__ == '__main__':
    unittest.main()
