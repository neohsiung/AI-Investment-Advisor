"""
Test coverage for MarketDataService - Fixed to match actual implementation
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import pandas as pd
from src.services.market_data_service import MarketDataService


class TestMarketDataServiceFixed:
    """Test suite for MarketDataService with correct mocking"""
    
    @pytest.fixture
    def mock_repository(self):
        """Create mock repository"""
        return Mock()
    
    @pytest.fixture
    def service(self, mock_repository):
        """Create service with mocked repository"""
        return MarketDataService(repository=mock_repository)
    
    def test_initialization(self):
        """Test service initializes correctly"""
        service = MarketDataService()
        assert service is not None
        assert service.repository is not None
    
    def test_get_current_prices_success(self, service, mock_repository):
        """Test getting current prices via repository"""
        mock_repository.fetch_current_prices.return_value = {
            'AAPL': 150.0,
            'TSLA': 250.0
        }
        
        result = service.get_current_prices(['AAPL', 'TSLA'])
        
        assert result == {'AAPL': 150.0, 'TSLA': 250.0}
        mock_repository.fetch_current_prices.assert_called_once_with(['AAPL', 'TSLA'])
    
    def test_get_current_prices_empty_list(self, service):
        """Test with empty ticker list"""
        result = service.get_current_prices([])
        assert result == {}
    
    def test_get_current_prices_handles_exception(self, service, mock_repository):
        """Test handles repository errors gracefully"""
        mock_repository.fetch_current_prices.side_effect = Exception("API Error")
        
        result = service.get_current_prices(['AAPL'])
        
        assert result == {}
    
    def test_get_ohlcv_success(self, service, mock_repository):
        """Test fetching OHLCV data"""
        mock_df = pd.DataFrame({
            'Open': [100, 101, 102],
            'High': [105, 106, 107],
            'Low': [99, 100, 101],
            'Close': [103, 104, 105],
            'Volume': [1000, 1100, 1200]
        }, index=pd.date_range('2025-01-01', periods=3))
        
        mock_repository.fetch_history.return_value = mock_df
        
        result = service.get_ohlcv('AAPL', days=3)
        
        assert 'close' in result
        assert len(result['close']) == 3
        assert result['close'][2] == 105
    
    def test_get_ohlcv_empty_data(self, service, mock_repository):
        """Test OHLCV with no data"""
        mock_repository.fetch_history.return_value = pd.DataFrame()
        
        result = service.get_ohlcv('INVALID')
        
        assert result == {}
    
    def test_get_technical_indicators(self, service, mock_repository):
        """Test calculating technical indicators"""
        # Create dummy price history with 200 days
        closes = list(range(100, 300))  # 200 data points
        mock_df = pd.DataFrame({
            'Close': closes,
            'Volume': [1000000] * 200
        }, index=pd.date_range('2024-01-01', periods=200))
        
        mock_repository.fetch_history.return_value = mock_df
        
        result = service.get_technical_indicators('AAPL')
        
        assert 'rsi' in result
        assert 'macd' in result
        assert 'sma' in result
        assert isinstance(result['rsi'], (int, float))
    
    def test_get_technical_indicators_insufficient_data(self, service, mock_repository):
        """Test indicators with insufficient data"""
        mock_df = pd.DataFrame({
            'Close': [100, 101, 102],
            'Volume': [1000, 1100, 1200]
        }, index=pd.date_range('2025-01-01', periods=3))
        
        mock_repository.fetch_history.return_value = mock_df
        
        result = service.get_technical_indicators('AAPL')
        
        assert result['rsi'] == 50  # Default value
        assert result['macd'] == 'neutral'
    
    def test_get_news(self, service, mock_repository):
        """Test fetching news from repository"""
        mock_repository.fetch_news.return_value = [
            {'title': 'Apple releases product', 'link': 'http://example.com/1'},
            {'title': 'Stock rises 5%', 'link': 'http://example.com/2'}
        ]
        
        result = service.get_news('AAPL')
        
        assert len(result) == 2
        assert 'Apple releases' in result[0]
        assert 'http://example.com' in result[0]
    
    def test_get_news_handles_exception(self, service, mock_repository):
        """Test news fetching handles errors"""
        mock_repository.fetch_news.side_effect = Exception("News API Error")
        
        result = service.get_news('AAPL')
        
        assert result == []
    
    def test_get_financials(self, service, mock_repository):
        """Test fetching financial data"""
        mock_repository.fetch_info.return_value = {
            'marketCap': 2500000000000,
            'trailingPE': 28.5,
            'forwardPE': 25.0,
            'sector': 'Technology'
        }
        
        result = service.get_financials('AAPL')
        
        assert result['market_cap'] == 2500000000000
        assert result['trailing_pe'] == 28.5
        assert result['sector'] == 'Technology'
    
    def test_get_macro_data(self, service, mock_repository):
        """Test fetching macro economic data"""
        def fetch_history_side_effect(ticker, period):
            if ticker == '^VIX':
                return pd.DataFrame({'Close': [15.5]}, index=[datetime.now()])
            elif ticker == '^TNX':
                return pd.DataFrame({'Close': [4.2]}, index=[datetime.now()])
            elif ticker == 'SPY':
                return pd.DataFrame({'Close': [450.0]}, index=[datetime.now()])
            return pd.DataFrame()
        
        mock_repository.fetch_history.side_effect = fetch_history_side_effect
        
        result = service.get_macro_data()
        
        assert '^VIX' in result
        assert '^TNX' in result
        assert 'SPY' in result
    
    def test_get_yield_curve_inversion(self, service, mock_repository):
        """Test yield curve inversion calculation"""
        def fetch_history_side_effect(ticker, period):
            if ticker == '^TNX':  # 10Y
                return pd.DataFrame({'Close': [4.2]}, index=[datetime.now()])
            elif ticker == '^IRX':  # 3M
                return pd.DataFrame({'Close': [4.5]}, index=[datetime.now()])
            return pd.DataFrame()
        
        mock_repository.fetch_history.side_effect = fetch_history_side_effect
        
        result = service.get_yield_curve_inversion()
        
        assert 'spread' in result
        assert 'inverted' in result
        assert result['inverted'] is True  # 4.2 - 4.5 = -0.3 (inverted)
    
    def test_get_market_context(self, service, mock_repository):
        """Test comprehensive market context"""
        mock_df = pd.DataFrame({
            'Open': [100],
            'High': [105],
            'Low': [99],
            'Close': [103],
            'Volume': [1000000]
        }, index=[datetime.now()])
        
        mock_repository.fetch_history.return_value = mock_df
        
        result = service.get_market_context(['AAPL'])
        
        assert 'AAPL' in result
        assert 'price_data' in result['AAPL']
        assert 'indicators' in result['AAPL']
