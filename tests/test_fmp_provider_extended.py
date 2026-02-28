"""
Extended tests for FMP Provider - Edge Cases & Missing Coverage.
測試 FMP 資料提供者的邊緣情況與缺失覆蓋。
"""
import pytest
from unittest.mock import MagicMock, patch
import requests
from src.data.providers.fmp_provider import FMPProvider


class TestFMPProviderExtended:
    """Extended tests for FMP Provider missing coverage areas."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings service."""
        mock = MagicMock()
        mock.get_all_settings.return_value = {}
        mock.get_setting.return_value = None
        return mock
    
    def test_fetch_news_with_empty_response(self, mock_settings):
        """Test news fetching with empty array response."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []  # Empty news array
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            news = provider.fetch_news('AAPL', limit=5)
            
            assert news == []
    
    def test_fetch_news_api_error_500(self, mock_settings):
        """Test news API returning 500 error."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {'error': 'Internal error'}
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            news = provider.fetch_news('AAPL', limit=5)
            
            assert news == []
    
    def test_fetch_news_network_exception(self, mock_settings):
        """Test news fetching with network exception."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_get.side_effect = requests.ConnectionError("Network error")
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            news = provider.fetch_news('AAPL', limit=5)
            
            assert news == []
    
    def test_fetch_info_with_empty_array(self, mock_settings):
        """Test info fetching returns empty array."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []  # Empty array
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            info = provider.fetch_info('INVALID')
            
            assert info == {} or info is None
    
    def test_fetch_info_invalid_ticker_404(self, mock_settings):
        """Test info for invalid ticker returns 404."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {'error': 'Ticker not found'}
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            info = provider.fetch_info('NOTREAL')
            
            assert info == {} or info is None
    
    def test_fetch_info_network_timeout(self, mock_settings):
        """Test info fetching with timeout."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_get.side_effect = requests.Timeout("Request timeout")
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            info = provider.fetch_info('AAPL')
            
            assert info == {}
    
    def test_fetch_info_exception(self, mock_settings):
        """Test info fetching with general exception."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_get.side_effect = Exception("Unexpected error")
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            info = provider.fetch_info('AAPL')
            
            assert info == {}
    
    def test_fetch_current_prices_api_403_forbidden(self, mock_settings):
        """Test current prices with 403 forbidden response."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.json.return_value = {'error': 'Forbidden - Legacy endpoint'}
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_current_prices_malformed_json(self, mock_settings):
        """Test current prices with malformed JSON response."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_current_prices_missing_price_field(self, mock_settings):
        """Test current prices when 'price' field is missing."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {'symbol': 'AAPL'}  # Missing 'price' field
            ]
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            # Should handle gracefully
            assert isinstance(prices, dict)
    
    def test_fetch_history_returns_empty_dataframe(self, mock_settings):
        """Test that fetch_history returns empty DataFrame (not implemented)."""
        provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
        df = provider.fetch_history('AAPL', period='1y')
        
        # FMP history is not implemented, should return empty DF
        assert len(df) == 0
    
    def test_initialization_without_api_key_from_env(self, mock_settings):
        """Test initialization gets API key from environment."""
        with patch.dict('os.environ', {'FMP_API_KEY': 'env_fmp_key'}):
            provider = FMPProvider(settings_service=mock_settings)
            assert provider.api_key == 'env_fmp_key'
    
    def test_fetch_news_without_api_key(self, mock_settings):
        """Test fetch_news without API key returns empty list."""
        with patch.dict('os.environ', {}, clear=True):
            provider = FMPProvider(api_key=None, settings_service=mock_settings)
            news = provider.fetch_news('AAPL', limit=5)
            
            assert news == []
    
    def test_fetch_info_without_api_key(self, mock_settings):
        """Test fetch_info without API key returns empty dict."""
        with patch.dict('os.environ', {}, clear=True):
            provider = FMPProvider(api_key=None, settings_service=mock_settings)
            info = provider.fetch_info('AAPL')
            
            assert info == {}
    
    def test_fetch_current_prices_empty_ticker_list(self, mock_settings):
        """Test fetch_current_prices with empty ticker list."""
        provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
        prices = provider.fetch_current_prices([])
        
        assert prices == {}
    
    def test_fetch_news_with_missing_fields_in_items(self, mock_settings):
        """Test news fetching when items have missing fields."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {'title': 'News 1'},  # Missing url, site, publishedDate
                {'url': 'http://example.com'},  # Missing title
            ]
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            news = provider.fetch_news('AAPL', limit=5)
            
            # Should handle missing fields gracefully
            assert len(news) == 2
            assert news[0]['title'] == 'News 1'
            assert news[0]['link'] is None
    
    def test_fetch_current_prices_connection_error(self, mock_settings):
        """Test fetch_current_prices with connection error."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_get.side_effect = requests.ConnectionError("Failed to connect")
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL', 'GOOGL'])
            
            assert prices == {}
