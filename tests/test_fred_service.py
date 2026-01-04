"""
Tests for FRED Service (src/services/fred_service.py).
測試 FRED 總經數據服務。
"""
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime
from src.services.fred_service import FredService

class TestFredService:
    
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch('src.services.fred_service.Fred') as MockFred:
            service = FredService(api_key="test_key")
            MockFred.assert_called_once_with(api_key="test_key")
            assert service.client is not None
    
    def test_init_without_api_key(self):
        """Test initialization without API key."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('src.services.fred_service.Fred') as MockFred:
                service = FredService()
                assert service.client is None
    
    def test_init_from_env(self):
        """Test initialization from environment variable."""
        with patch.dict('os.environ', {'FRED_API_KEY': 'env_test_key'}):
            with patch('src.services.fred_service.Fred') as MockFred:
                service = FredService()
                MockFred.assert_called_once_with(api_key="env_test_key")
    
    def test_init_error_handling(self):
        """Test error handling during initialization."""
        with patch('src.services.fred_service.Fred') as MockFred:
            MockFred.side_effect = Exception("Init Error")
            service = FredService(api_key="test_key")
            assert service.client is None
    
    def test_get_macro_indicators_no_client(self):
        """Test get_macro_indicators without initialized client."""
        with patch.dict('os.environ', {}, clear=True):
            service = FredService()
            result = service.get_macro_indicators()
            assert result == {}
    
    def test_get_macro_indicators_success(self):
        """Test successful macro indicator retrieval."""
        with patch('src.services.fred_service.Fred') as MockFred:
            mock_client = MockFred.return_value
            
            # Create mock series response
            mock_series = pd.Series(
                [3.5, 3.4, 3.3],
                index=pd.to_datetime(['2025-01-01', '2024-12-01', '2024-11-01'])
            )
            mock_client.get_series.return_value = mock_series
            
            service = FredService(api_key="test_key")
            result = service.get_macro_indicators()
            
            # Should have data for all indicators
            assert len(result) > 0
            # Check structure
            for key, data in result.items():
                assert 'value' in data
                assert 'date' in data
                assert 'trend' in data
    
    def test_get_macro_indicators_trend_up(self):
        """Test trend detection when value increases."""
        with patch('src.services.fred_service.Fred') as MockFred:
            mock_client = MockFred.return_value
            
            # Current > Previous = Up trend
            mock_series = pd.Series(
                [4.0, 3.5],
                index=pd.to_datetime(['2025-01-01', '2024-12-01'])
            )
            mock_client.get_series.return_value = mock_series
            
            service = FredService(api_key="test_key")
            result = service.get_macro_indicators()
            
            # All should show "Up" trend
            for key, data in result.items():
                assert data['trend'] == "Up"
    
    def test_get_macro_indicators_trend_down(self):
        """Test trend detection when value decreases."""
        with patch('src.services.fred_service.Fred') as MockFred:
            mock_client = MockFred.return_value
            
            # Current < Previous = Down trend
            mock_series = pd.Series(
                [3.0, 3.5],
                index=pd.to_datetime(['2025-01-01', '2024-12-01'])
            )
            mock_client.get_series.return_value = mock_series
            
            service = FredService(api_key="test_key")
            result = service.get_macro_indicators()
            
            # All should show "Down" trend
            for key, data in result.items():
                assert data['trend'] == "Down"
    
    def test_get_macro_indicators_empty_series(self):
        """Test handling of empty series response."""
        with patch('src.services.fred_service.Fred') as MockFred:
            mock_client = MockFred.return_value
            mock_client.get_series.return_value = pd.Series(dtype=float)
            
            service = FredService(api_key="test_key")
            result = service.get_macro_indicators()
            
            # Should return empty dict when series is empty
            assert result == {}
    
    def test_get_macro_indicators_error_handling(self):
        """Test error handling during data fetch."""
        with patch('src.services.fred_service.Fred') as MockFred:
            mock_client = MockFred.return_value
            mock_client.get_series.side_effect = Exception("API Error")
            
            service = FredService(api_key="test_key")
            result = service.get_macro_indicators()
            
            # Should return empty dict on error
            assert result == {}
    
    def test_get_macro_indicators_single_datapoint(self):
        """Test handling when only one datapoint is available."""
        with patch('src.services.fred_service.Fred') as MockFred:
            mock_client = MockFred.return_value
            
            # Only one datapoint
            mock_series = pd.Series(
                [3.5],
                index=pd.to_datetime(['2025-01-01'])
            )
            mock_client.get_series.return_value = mock_series
            
            service = FredService(api_key="test_key")
            result = service.get_macro_indicators()
            
            # Should handle single datapoint gracefully
            for key, data in result.items():
                assert data['value'] == 3.5
                assert data['trend'] == "Down"  # current == prev, so not >
