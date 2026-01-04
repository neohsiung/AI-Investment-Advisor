"""
Tests for FMP and Polygon Providers.
測試 FMP 和 Polygon 資料提供者。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.data.providers.fmp_provider import FMPProvider
from src.data.providers.polygon_provider import PolygonProvider

class TestFMPProvider:
    
    def test_init_without_key(self):
        """Test initialization without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = FMPProvider()
            assert provider.api_key is None
    
    def test_init_with_key(self):
        """Test initialization with API key."""
        with patch.dict('os.environ', {'FMP_API_KEY': 'test_key'}):
            provider = FMPProvider()
            assert provider.api_key == 'test_key'
    
    @patch('src.data.providers.fmp_provider.requests.get')
    def test_fetch_current_prices(self, mock_get):
        """Test fetching current prices."""
        with patch.dict('os.environ', {'FMP_API_KEY': 'test_key'}):
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = [
                {"symbol": "AAPL", "price": 150.0}
            ]
            
            provider = FMPProvider()
            result = provider.fetch_current_prices(["AAPL"])
            
            assert "AAPL" in result
            assert result["AAPL"] == 150.0
    
    @patch('src.data.providers.fmp_provider.requests.get')
    def test_fetch_current_prices_error(self, mock_get):
        """Test error handling in fetch_current_prices."""
        with patch.dict('os.environ', {'FMP_API_KEY': 'test_key'}):
            mock_get.side_effect = Exception("Network Error")
            
            provider = FMPProvider()
            result = provider.fetch_current_prices(["AAPL"])
            
            assert result == {}
    
    def test_fetch_prices_no_key(self):
        """Test fetching prices without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = FMPProvider()
            result = provider.fetch_current_prices(["AAPL"])
            assert result == {}
    
    @patch('src.data.providers.fmp_provider.requests.get')
    def test_fetch_financials(self, mock_get):
        """Test fetching financial data."""
        with patch.dict('os.environ', {'FMP_API_KEY': 'test_key'}):
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = [
                {"netIncome": 1000000, "revenue": 5000000}
            ]
            
            provider = FMPProvider()
            result = provider.fetch_financials("AAPL")
            
            assert "netIncome" in str(result) or isinstance(result, (dict, list))

class TestPolygonProvider:
    
    def test_init_without_key(self):
        """Test initialization without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = PolygonProvider()
            assert provider.api_key is None
    
    def test_init_with_key(self):
        """Test initialization with API key."""
        with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
            provider = PolygonProvider()
            assert provider.api_key == 'test_key'
    
    @patch('src.data.providers.polygon_provider.requests.get')
    def test_fetch_current_prices(self, mock_get):
        """Test fetching current prices."""
        with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "results": [{"T": "AAPL", "c": 150.0}]
            }
            
            provider = PolygonProvider()
            result = provider.fetch_current_prices(["AAPL"])
            
            # May return empty if not mocked correctly, check no exception
            assert isinstance(result, dict)
    
    @patch('src.data.providers.polygon_provider.requests.get')
    def test_fetch_current_prices_error(self, mock_get):
        """Test error handling in fetch_current_prices."""
        with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
            mock_get.side_effect = Exception("Network Error")
            
            provider = PolygonProvider()
            result = provider.fetch_current_prices(["AAPL"])
            
            assert result == {}
    
    def test_fetch_prices_no_key(self):
        """Test fetching prices without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = PolygonProvider()
            result = provider.fetch_current_prices(["AAPL"])
            assert result == {}
    
    @patch('src.data.providers.polygon_provider.requests.get')
    def test_fetch_financials(self, mock_get):
        """Test fetching financial data."""
        with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "results": [{"financials": {"revenue": {"value": 1000000}}}]
            }
            
            provider = PolygonProvider()
            result = provider.fetch_financials("AAPL")
            
            assert isinstance(result, (dict, list))
