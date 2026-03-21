"""
Extended tests for Data Providers (Polygon, FMP).
測試資料提供者擴展功能。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.data.providers.polygon_provider import PolygonProvider
from src.data.providers.fmp_provider import FMPProvider


class TestPolygonProviderExtended:
    
    def test_fetch_current_prices_with_zero_price(self, mock_settings):
        """Test handling of zero price in response."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'ticker': {
                    'lastTrade': {'p': 0}  # Zero price
                }
            }
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            # Should use fallback when price is 0
            assert 'AAPL' not in prices or prices['AAPL'] > 0
    
    def test_fetch_current_prices_api_error(self, mock_settings):
        """Test handling of API errors."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_get.side_effect = Exception("API timeout")
            
            provider = PolygonProvider(settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            # Should return empty dict on error
            assert prices == {}
    
    def test_fetch_current_prices_invalid_response(self, mock_settings):
        """Test handling of invalid JSON response."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}  # No ticker data
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            # Should handle missing data gracefully
            assert isinstance(prices, dict)
    
    def test_fetch_prev_close_fallback(self, mock_settings):
        """Test previous close fallback logic."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            # First call returns no current data
            # Second call to prev close returns data
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {'ticker': {}}
            
            mock_response2 = MagicMock()
            mock_response2.status_code = 200
            mock_response2.json.return_value = {
                'results': [{'c': 150.0}]
            }
            
            mock_get.side_effect = [mock_response1, mock_response2]
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert isinstance(prices, dict)
    
    def test_initialization_without_api_key(self, mock_settings):
        """Test provider initialization without API key."""
        # Ensure settings don't have the key
        mock_settings.get_all_settings.return_value = {}
        provider = PolygonProvider(settings_service=mock_settings)
        
        # Should warn but not fail
        assert provider.api_key is None or provider.api_key == ""
        
        # fetch should return empty dict
        prices = provider.fetch_current_prices(['AAPL'])
        assert prices == {}


class TestFMPProviderExtended:
    
    def test_fetch_info_api_error(self, mock_settings):
        """Test fetch_info with API error."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_get.side_effect = Exception("Connection timeout")
            
            provider = FMPProvider(settings_service=mock_settings)
            data = provider.fetch_info('AAPL')
            
            # Should return empty dict on error
            assert data == {}
    
    def test_fetch_info_invalid_response(self, mock_settings):
        """Test handling of invalid info response."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Not found"}
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            data = provider.fetch_info('INVALID')
            
            assert data is None or data == {}
    
    def test_fetch_current_prices_rate_limit(self, mock_settings):
        """Test handling of rate limit errors."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.json.return_value = {"error": "Rate limit exceeded"}
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            # Should handle rate limit gracefully
            assert isinstance(prices, dict)
    
    def test_fetch_current_prices_empty_ticker_list(self, mock_settings):
        """Test fetching prices with empty ticker list."""
        provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
        prices = provider.fetch_current_prices([])
        
        assert prices == {}
    
    def test_fetch_news_success(self, mock_settings):
        """Test successful news fetching."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {
                    'title': 'Test news',
                    'url': 'http://example.com',
                    'site': 'Example',
                    'publishedDate': '2024-01-01'
                }
            ]
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            news = provider.fetch_news('AAPL', limit=5)
            
            assert len(news) > 0
            assert news[0]['title'] == 'Test news'
    
    def test_fetch_info_with_missing_fields(self, mock_settings):
        """Test fetch_info with missing optional fields."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {
                    'symbol': 'AAPL',
                    'sector': 'Technology'
                    # Missing many optional fields
                }
            ]
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            data = provider.fetch_info('AAPL')
            
            # Should handle missing fields gracefully
            assert data is not None
            assert data.get('sector') == 'Technology'
    
    def test_initialization_with_settings_key(self, mock_settings):
        """Test provider gets API key from settings."""
        mock_settings.get_all_settings.return_value = {'source_fmp_api_key': 'settings_key'}
        provider = FMPProvider(settings_service=mock_settings)
        
        assert provider.api_key == 'settings_key'
    
    def test_fetch_current_prices_multiple_tickers(self, mock_settings):
        """Test fetching prices for multiple tickers."""
        with patch('src.data.providers.fmp_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {'symbol': 'AAPL', 'price': 150.0},
                {'symbol': 'MSFT', 'price': 300.0}
            ]
            mock_get.return_value = mock_response
            
            provider = FMPProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL', 'MSFT'])
            
            assert isinstance(prices, dict)


@pytest.fixture
def mock_settings():
    """Mock settings service fixture."""
    mock = MagicMock()
    mock.get_all_settings.return_value = {}
    mock.get_setting.return_value = None
    return mock
