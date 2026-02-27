"""
Test coverage for MarketDataService - Fixed to match actual implementation
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import pandas as pd
from src.services.market_data_service import MarketDataService

class TestMarketDataServiceFixed:
    """Test suite for MarketDataService with Provider mocks"""
    
    @pytest.fixture
    def mock_providers(self):
        """Mock the provider classes"""
        with patch('src.services.market_data_service.PolygonProvider') as MockPolygon, \
             patch('src.services.market_data_service.FMPProvider') as MockFMP, \
             patch('src.services.market_data_service.YFinanceProvider') as MockYF, \
             patch('src.services.market_data_service.FredProvider') as MockFred, \
             patch('src.services.market_data_service.InternetSearchService') as MockSearch:
            
            # Setup instances
            poly_instance = MockPolygon.return_value
            fmp_instance = MockFMP.return_value
            yf_instance = MockYF.return_value
            fred_instance = MockFred.return_value
            search_instance = MockSearch.return_value
            
            yield {
                'polygon': poly_instance,
                'fmp': fmp_instance,
                'yfinance': yf_instance,
                'fred': fred_instance,
                'search': search_instance
            }

    @pytest.fixture
    def service(self, mock_providers):
        """Create service with mocked providers"""
        return MarketDataService()
    
    def test_initialization(self, service):
        """Test service initializes correctly with providers"""
        assert service is not None
        assert service.polygon is not None
        assert service.fmp is not None
        assert service.yfinance is not None
        assert len(service.providers) == 6

    def test_get_current_prices_success_primary(self, service, mock_providers):
        """Test getting current prices from primary provider (Polygon)"""
        mock_providers['polygon'].fetch_current_prices.return_value = {'AAPL': 150.0}
        
        result = service.get_current_prices(['AAPL'])
        
        assert result == {'AAPL': 150.0}
        mock_providers['polygon'].fetch_current_prices.assert_called_once_with(['AAPL'])
        mock_providers['fmp'].fetch_current_prices.assert_not_called()

    def test_get_current_prices_failover(self, service, mock_providers):
        """Test failover to secondary provider"""
        # Primary fails or returns empty
        mock_providers['polygon'].fetch_current_prices.side_effect = Exception("API Error")
        # Secondary succeeds
        mock_providers['fmp'].fetch_current_prices.return_value = {'AAPL': 150.0}
        
        result = service.get_current_prices(['AAPL'])
        
        assert result == {'AAPL': 150.0}
        mock_providers['polygon'].fetch_current_prices.assert_called()
        mock_providers['fmp'].fetch_current_prices.assert_called()

    def test_get_current_prices_empty_list(self, service):
        """Test with empty ticker list"""
        result = service.get_current_prices([])
        assert result == {}

    def test_get_ohlcv_success(self, service, mock_providers):
        """Test fetching OHLCV data (defaults to YFinance)"""
        mock_df = pd.DataFrame({
            'Open': [100, 101, 102],
            'High': [105, 106, 107],
            'Low': [99, 100, 101],
            'Close': [103, 104, 105],
            'Volume': [1000, 1100, 1200]
        }, index=pd.date_range('2025-01-01', periods=3))
        
        # history_providers in service is [yfinance, polygon, fmp]
        mock_providers['yfinance'].fetch_history.return_value = mock_df
        
        result = service.get_ohlcv('AAPL', days=3)
        
        assert 'close' in result
        assert len(result['close']) == 3
        assert result['close'][2] == 105

    def test_get_technical_indicators(self, service, mock_providers):
        """Test calculating technical indicators"""
        # Create dummy price history with 200 days
        closes = list(range(100, 300))  # 200 data points
        mock_df = pd.DataFrame({
            'Close': closes,
            'Volume': [1000000] * 200
        }, index=pd.date_range('2024-01-01', periods=200))
        
        # get_technical_indicators checks [yfinance, polygon]
        mock_providers['yfinance'].fetch_history.return_value = mock_df
        
        result = service.get_technical_indicators('AAPL')
        
        assert 'rsi' in result
        assert 'macd' in result
        assert 'sma' in result
        assert isinstance(result['rsi'], (int, float))

    def test_get_news(self, service, mock_providers):
        """Test fetching news (defaults to FMP)"""
        # news_providers is [fmp, yfinance, polygon]
        mock_providers['fmp'].fetch_news.return_value = [
            {'title': 'Apple releases product', 'link': 'http://example.com/1'},
            {'title': 'Stock rises 5%', 'link': 'http://example.com/2'}
        ]
        
        result = service.get_news('AAPL')
        
        assert len(result) == 2
        assert 'Apple releases' in result[0]['title']
        
    def test_get_financials(self, service, mock_providers):
        """Test fetching financial data"""
        mock_providers['fmp'].fetch_info.return_value = {
            'market_cap': 2500000000000,
            'trailing_pe': 28.5,
            'sector': 'Technology'
        }
        
        result = service.get_financials('AAPL')
        
        assert result['market_cap'] == 2500000000000

    def test_get_yield_curve_inversion_fred(self, service, mock_providers):
        """Test yield curve inversion with FRED data (Priority)"""
        mock_providers['fred'].fred_service.get_macro_indicators.return_value = {
            "10Y2Y_Spread": {"value": -0.5, "trend": "Down"}
        }
        
        result = service.get_yield_curve_inversion()
        
        assert result['spread'] == -0.5
        assert result['inverted'] is True
        assert "FRED" in result['desc']

    def test_get_yield_curve_inversion_fallback(self, service, mock_providers):
        """Test yield curve inversion fallback to YFinance"""
        # FRED fails
        mock_providers['fred'].fred_service.get_macro_indicators.side_effect = Exception("API Fail")
        
        def fetch_history_side_effect(ticker, period=None, days=None):
            if ticker == '^TNX':  # 10Y
                return pd.DataFrame({'Close': [4.2]}, index=[datetime.now()])
            elif ticker == '^IRX':  # 3M
                return pd.DataFrame({'Close': [4.5]}, index=[datetime.now()])
            return pd.DataFrame()
        
        mock_providers['yfinance'].fetch_history.side_effect = fetch_history_side_effect
        
        result = service.get_yield_curve_inversion()
        
        assert result['spread'] == -0.3 # 4.2 - 4.5
        assert result['inverted'] is True
        assert "Yahoo" in result['desc']

    def test_get_macro_data(self, service, mock_providers):
        """Test macro data fetching (FRED + YFinance)"""
        mock_providers['fred'].fred_service.get_macro_indicators.return_value = {"GDP": {"value": 100}}
        mock_providers['yfinance'].fetch_current_prices.return_value = {'^VIX': 20.0}
        
        result = service.get_macro_data()
        
        assert result['economics']['GDP']['value'] == 100
        assert result['market_indicators']['^VIX'] == 20.0
