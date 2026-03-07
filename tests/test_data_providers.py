"""
Tests for FMP and Polygon Providers.
測試 FMP 和 Polygon 資料提供者。
"""
import pytest
from unittest.mock import MagicMock, patch
import os
from src.data.providers.fmp_provider import FMPProvider
from src.data.providers.polygon_provider import PolygonProvider

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    # Ensure get_all_settings returns a real dict or a mock that behaves like one
    settings.get_all_settings.return_value = {}
    settings.get_setting.return_value = None
    return settings

class TestFMPProvider:
    
    def test_init_without_key(self, mock_settings):
        """Test initialization without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = FMPProvider(settings_service=mock_settings)
            assert provider.api_key is None
    
    def test_init_with_key(self, mock_settings):
        """Test initialization with API key from settings."""
        mock_settings.get_all_settings.return_value = {'source_fmp_api_key': 'test_key'}
        provider = FMPProvider(settings_service=mock_settings)
        assert provider.api_key == 'test_key'
    
    @patch('src.data.providers.fmp_provider.requests.get')
    def test_fetch_current_prices(self, mock_get, mock_settings):
        """Test fetching current prices."""
        mock_settings.get_all_settings.return_value = {'source_fmp_api_key': 'test_key'}
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"symbol": "AAPL", "price": 150.0}
        ]
        
        provider = FMPProvider(settings_service=mock_settings)
        result = provider.fetch_current_prices(["AAPL"])
        assert "AAPL" in result
        assert result["AAPL"] == 150.0
    
    @patch('src.data.providers.fmp_provider.requests.get')
    def test_fetch_current_prices_error(self, mock_get, mock_settings):
        """Test error handling in fetch_current_prices."""
        mock_settings.get_all_settings.return_value = {'source_fmp_api_key': 'test_key'}
        mock_get.side_effect = Exception("Network Error")
        
        provider = FMPProvider(settings_service=mock_settings)
        result = provider.fetch_current_prices(["AAPL"])
        assert result == {}
    
    def test_fetch_prices_no_key(self, mock_settings):
        """Test fetching prices without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = FMPProvider(settings_service=mock_settings)
            result = provider.fetch_current_prices(["AAPL"])
            assert result == {}
    
    @patch('src.data.providers.fmp_provider.requests.get')
    def test_fetch_info(self, mock_get, mock_settings):
        """Test fetching financial data."""
        mock_settings.get_all_settings.return_value = {'source_fmp_api_key': 'test_key'}
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"mktCap": 1000000, "sector": "Tech"}
        ]
        
        provider = FMPProvider(settings_service=mock_settings)
        result = provider.fetch_info("AAPL")
        assert result["market_cap"] == 1000000

class TestPolygonProvider:
    
    def test_init_without_key(self, mock_settings):
        """Test initialization without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = PolygonProvider(settings_service=mock_settings)
            assert provider.api_key is None
    
    def test_init_with_key(self, mock_settings):
        """Test initialization with API key from settings."""
        mock_settings.get_all_settings.return_value = {'source_polygon_api_key': 'test_key'}
        provider = PolygonProvider(settings_service=mock_settings)
        assert provider.api_key == 'test_key'
    
    @patch('src.data.providers.polygon_provider.requests.get')
    def test_fetch_current_prices(self, mock_get, mock_settings):
        """Test fetching current prices."""
        mock_settings.get_all_settings.return_value = {'source_polygon_api_key': 'test_key'}
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "results": [{"ticker": "AAPL", "session": {"price": 150.0}}]
        }
        
        provider = PolygonProvider(settings_service=mock_settings)
        result = provider.fetch_current_prices(["AAPL"])
        assert result["AAPL"] == 150.0
    
    @patch('src.data.providers.polygon_provider.requests.get')
    def test_fetch_current_prices_error(self, mock_get, mock_settings):
        """Test error handling in fetch_current_prices."""
        mock_settings.get_all_settings.return_value = {'source_polygon_api_key': 'test_key'}
        mock_get.side_effect = Exception("Network Error")
        
        provider = PolygonProvider(settings_service=mock_settings)
        result = provider.fetch_current_prices(["AAPL"])
        assert result == {}
    
    def test_fetch_prices_no_key(self, mock_settings):
        """Test fetching prices without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = PolygonProvider(settings_service=mock_settings)
            result = provider.fetch_current_prices(["AAPL"])
            assert result == {}
    
    @patch('src.data.providers.polygon_provider.requests.get')
    def test_fetch_info(self, mock_get, mock_settings):
        """Test fetching financial data."""
        mock_settings.get_all_settings.return_value = {'source_polygon_api_key': 'test_key'}
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "results": {"market_cap": 1000000}
        }
        
        provider = PolygonProvider(settings_service=mock_settings)
        result = provider.fetch_info("AAPL")
        assert result["market_cap"] == 1000000
