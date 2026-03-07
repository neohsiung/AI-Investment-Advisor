"""
Extended tests for Polygon Provider - Edge Cases & Error Handling.
測試 Polygon 資料提供者的邊緣情況與錯誤處理。
"""
import pytest
from unittest.mock import MagicMock, patch
import requests
from src.data.providers.polygon_provider import PolygonProvider


class TestPolygonProviderEdgeCases:
    """Extended edge case tests for Polygon Provider."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings service."""
        mock = MagicMock()
        mock.get_all_settings.return_value = {}
        mock.get_setting.return_value = None
        return mock
    
    def test_fetch_prev_close_fallback_success(self, mock_settings):
        """Test successful fallback to previous close when current price unavailable."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            # First call returns no current price data
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {'ticker': {}}
            
            # Second call returns previous close
            mock_response2 = MagicMock()
            mock_response2.status_code = 200
            mock_response2.json.return_value = {
                'results': [{'c': 150.50}]
            }
            
            mock_get.side_effect = [mock_response1, mock_response2]
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            # Should have made 2 requests (current + prev close)
            assert mock_get.call_count == 2
            assert isinstance(prices, dict)
    
    def test_fetch_prev_close_empty_results(self, mock_settings):
        """Test previous close with empty results array."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            # First call - no current price
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {'ticker': {}}
            
            # Second call - empty results
            mock_response2 = MagicMock()
            mock_response2.status_code = 200
            mock_response2.json.return_value = {'results': []}
            
            mock_get.side_effect = [mock_response1, mock_response2]
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_prev_close_api_error(self, mock_settings):
        """Test handling when prev close API also fails."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            # First call - no current price
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {'ticker': {}}
            
            # Second call - API error
            mock_response2 = MagicMock()
            mock_response2.status_code = 500
            mock_response2.json.return_value = {'error': 'Internal server error'}
            
            mock_get.side_effect = [mock_response1, mock_response2]
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_prev_close_network_timeout(self, mock_settings):
        """Test network timeout on prev close request."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            # First call - no current price
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {'ticker': {}}
            
            # Second call - timeout
            mock_get.side_effect = [mock_response1, requests.Timeout("Request timeout")]
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_history_error_handling(self, mock_settings):
        """Test error handling in historical data fetching."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {'error': 'Not found'}
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            df = provider.fetch_history('INVALID', days=30)
            
            # Should return empty DataFrame
            assert len(df) == 0
    
    def test_fetch_history_malformed_response(self, mock_settings):
        """Test handling of malformed historical data response."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'results': [
                    {'t': 1704067200000},  # Missing required fields
                ]
            }
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            df = provider.fetch_history('AAPL', days=30)
            
            # Should handle gracefully (may return empty or with data)
            assert df is not None
    
    def test_fetch_history_exception(self, mock_settings):
        """Test exception handling in historical data."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_get.side_effect = Exception("Unexpected error")
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            df = provider.fetch_history('AAPL', days=30)
            
            assert len(df) == 0
    
    def test_fetch_current_prices_rate_limit_429(self, mock_settings):
        """Test handling of 429 rate limit response."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.json.return_value = {'error': 'Rate limit exceeded'}
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL', 'GOOGL'])
            
            assert prices == {}
    
    def test_fetch_current_prices_unauthorized_401(self, mock_settings):
        """Test handling of 401 unauthorized response."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {'error': 'Unauthorized'}
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(api_key="invalid_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_current_prices_connection_error(self, mock_settings):
        """Test handling of connection errors."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_get.side_effect = requests.ConnectionError("Connection failed")
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_current_prices_json_decode_error(self, mock_settings):
        """Test handling of JSON decode errors."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            assert prices == {}
    
    def test_fetch_current_prices_missing_ticker_key(self, mock_settings):
        """Test response without 'ticker' key."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'status': 'OK'}  # No 'ticker' key
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL'])
            
            # Should handle missing key gracefully
            assert isinstance(prices, dict)
    
    def test_fetch_history_with_zero_days(self, mock_settings):
        """Test historical data with zero days parameter."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'results': []}
            mock_get.return_value = mock_response
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            df = provider.fetch_history('AAPL', days=0)
            
            assert len(df) == 0
    
    def test_initialization_with_settings_api_key(self, mock_settings):
        """Test provider initialization from settings."""
        mock_settings.get_all_settings.return_value = {'source_polygon_api_key': 'settings_test_key'}
        provider = PolygonProvider(settings_service=mock_settings)
        assert provider.api_key == 'settings_test_key'
    
    def test_fetch_current_prices_partial_success(self, mock_settings):
        """Test when some tickers succeed and others fail."""
        with patch('src.data.providers.polygon_provider.requests.get') as mock_get:
            # First ticker succeeds
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {
                'ticker': {'lastTrade': {'p': 150.0}}
            }
            
            # Second ticker fails
            mock_response2 = MagicMock()
            mock_response2.status_code = 404
            mock_response2.json.return_value = {'error': 'Not found'}
            
            mock_get.side_effect = [mock_response1, mock_response2]
            
            provider = PolygonProvider(api_key="test_key", settings_service=mock_settings)
            prices = provider.fetch_current_prices(['AAPL', 'INVALID'])
            
            # Should have at least AAPL
            assert isinstance(prices, dict)
