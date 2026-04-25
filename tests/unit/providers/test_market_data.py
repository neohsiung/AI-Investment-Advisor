"""
Test coverage for MarketDataService - Fixed to match actual implementation
Updated for v9.0 Asynchronous standards.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime
import pandas as pd
from src.services.market_data_service import MarketDataService

class TestMarketDataServiceFixed:
    """Test suite for MarketDataService with Provider mocks"""
    
    @pytest.fixture
    def mock_providers(self):
        """Mock the provider classes"""
        with patch('src.services.market_data_service.PolygonProvider') as MockPolygon, \
             patch('src.services.market_data_service.TiingoProvider') as MockTiingo, \
             patch('src.services.market_data_service.FMPProvider') as MockFMP, \
             patch('src.services.market_data_service.YFinanceProvider') as MockYF, \
             patch('src.services.market_data_service.FredProvider') as MockFred, \
             patch('src.services.market_data_service.InternetSearchService') as MockSearch:
            
            # Setup instances
            poly_instance = MockPolygon.return_value
            poly_instance.id = "polygon"
            tiingo_instance = MockTiingo.return_value
            tiingo_instance.id = "tiingo"
            fmp_instance = MockFMP.return_value
            fmp_instance.id = "fmp"
            yf_instance = MockYF.return_value
            yf_instance.id = "yahoo_finance"
            fred_instance = MockFred.return_value
            fred_instance.id = "fred"
            search_instance = MockSearch.return_value
            # Search methods are async
            search_instance.search_financial_context = AsyncMock()
            
            yield {
                'polygon': poly_instance,
                'tiingo': tiingo_instance,
                'fmp': fmp_instance,
                'yfinance': yf_instance,
                'fred': fred_instance,
                'search': search_instance
            }

    @pytest.fixture
    def service(self, mock_providers):
        """Create service with mocked providers"""
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "true"
        return MarketDataService(settings_service=mock_settings)
    
    def test_initialization(self, service):
        """Test service initializes correctly with providers"""
        assert service is not None
        assert service.polygon is not None
        assert service.fmp is not None
        assert service.yfinance is not None
        assert len(service.providers) >= 6

    @pytest.mark.asyncio
    async def test_get_current_prices_success_primary(self, service, mock_providers):
        """Test getting current prices from primary provider (Polygon)"""
        mock_providers['polygon'].fetch_current_prices.return_value = {'AAPL': 150.0}
        
        result = await service.get_current_prices(['AAPL'])
        
        assert result == {'AAPL': 150.0}
        mock_providers['polygon'].fetch_current_prices.assert_called_once_with(['AAPL'])

    @pytest.mark.asyncio
    async def test_get_current_prices_failover(self, service, mock_providers):
        """Test failover to secondary provider"""
        # Primary fails or returns empty
        mock_providers['polygon'].fetch_current_prices.side_effect = Exception("API Error")
        # Secondary succeeds
        mock_providers['fmp'].fetch_current_prices.return_value = {'AAPL': 150.0}
        
        result = await service.get_current_prices(['AAPL'])
        
        assert result == {'AAPL': 150.0}
        assert mock_providers['polygon'].fetch_current_prices.called
        assert mock_providers['fmp'].fetch_current_prices.called

    @pytest.mark.asyncio
    async def test_get_current_prices_empty_list(self, service):
        """Test with empty ticker list"""
        result = await service.get_current_prices([])
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
        
        mock_providers['yfinance'].fetch_history.return_value = mock_df
        
        result = service.get_ohlcv('AAPL', days=3)
        
        assert 'close' in result
        assert len(result['close']) == 3
        assert result['close'][2] == 105

    def test_get_technical_indicators(self, service, mock_providers):
        """Test calculating technical indicators"""
        closes = list(range(100, 300))  # 200 data points
        mock_df = pd.DataFrame({
            'Close': closes,
            'Volume': [1000000] * 200
        }, index=pd.date_range('2024-01-01', periods=200))
        
        mock_providers['yfinance'].fetch_history.return_value = mock_df
        
        result = service.get_technical_indicators('AAPL')
        
        assert 'rsi' in result
        assert 'macd' in result
        assert 'sma' in result
        assert isinstance(result['rsi'], (int, float))

    def test_get_news(self, service, mock_providers):
        """Test fetching news (defaults to Tiingo in v9.0)"""
        mock_providers['tiingo'].fetch_news.return_value = [
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
        mock_fred_svc = MagicMock()
        mock_providers['fred'].fred_service = mock_fred_svc
        mock_fred_svc.get_macro_indicators.return_value = {
            "10Y2Y_Spread": {"value": -0.5, "trend": "Down"}
        }
        
        result = service.get_yield_curve_inversion()
        
        assert result['spread'] == -0.5
        assert result['inverted'] is True
        assert "FRED" in result['desc']

    def test_get_macro_data(self, service, mock_providers):
        """Test macro data fetching (FRED + YFinance)"""
        mock_fred_svc = MagicMock()
        mock_providers['fred'].fred_service = mock_fred_svc
        mock_fred_svc.get_macro_indicators.return_value = {"GDP": {"value": 100}}
        mock_providers['yfinance'].fetch_current_prices.return_value = {'^VIX': 20.0}
        
        result = service.get_macro_data()
        
        assert result['economics']['GDP']['value'] == 100
        assert result['market_indicators']['^VIX'] == 20.0

    @pytest.mark.asyncio
    async def test_get_current_prices_final_fallback_search(self, service, mock_providers):
        """Test final fallback to internet search when all providers fail"""
        mock_providers['polygon'].fetch_current_prices.return_value = {}
        mock_providers['fmp'].fetch_current_prices.side_effect = Exception("Fail")
        mock_providers['yfinance'].fetch_current_prices.side_effect = Exception("Fail")
        
        # Search succeeds
        mock_providers['search'].search_financial_context.return_value = [
            {'title': 'AAPL Stock', 'snippet': 'AAPL is currently trading at $155.50 USD.'}
        ]
        
        result = await service.get_current_prices(['AAPL'])
        assert result == {'AAPL': 155.5}

    @pytest.mark.asyncio
    async def test_get_price_from_search(self, service, mock_providers):
        """Test parsing price from search snippet"""
        mock_providers['search'].search_financial_context.return_value = [
            {'title': 'AAPL Stock', 'snippet': 'AAPL is currently at 160.00 USD'}
        ]
        price = await service.get_price_from_search('AAPL')
        assert price == 160.0

    @pytest.mark.asyncio
    async def test_get_price_from_search_failure(self, service, mock_providers):
        mock_providers['search'].search_financial_context.side_effect = Exception("Search Fail")
        price = await service.get_price_from_search('AAPL')
        assert price == 0.0

    def test_get_market_context(self, service, mock_providers):
        """Test fetching full market context (Sync with internal loop)"""
        closes = list(range(100, 300))
        mock_df_ta = pd.DataFrame({'Close': closes, 'Volume': [1000] * 200}, index=pd.date_range('2024-01-01', periods=200))
        mock_providers['yfinance'].fetch_history.return_value = mock_df_ta
        
        mock_providers['fmp'].fetch_info.return_value = {'market_cap': 100}
        # Web Intelligence success
        mock_providers['search'].search_financial_context.return_value = [{'title': 'moat'}]
        
        result = service.get_market_context(['AAPL'], enrich=True)
        assert 'AAPL' in result
        assert 'price_data' in result['AAPL']
        assert 'web_intelligence' in result['AAPL']

    def test_get_web_intelligence(self, service, mock_providers):
        """Test fetching web intelligence (Sync wrapper)"""
        mock_providers['search'].search_financial_context.return_value = [{'title': 'Intel', 'snippet': 'moat'}]
        result = service.get_web_intelligence('AAPL')
        assert len(result) == 1
        assert result[0]['title'] == 'Intel'

    def test_get_ohlcv_provider_exception(self, service, mock_providers):
        mock_providers['polygon'].fetch_history.side_effect = Exception("Fail")
        mock_df = pd.DataFrame({
            'Open': [100], 'High': [105], 'Low': [95], 'Close': [100], 'Volume': [1000]
        }, index=[pd.Timestamp.now()])
        mock_providers['yfinance'].fetch_history.return_value = mock_df
        res = service.get_ohlcv('AAPL')
        assert 'close' in res

    def test_get_technical_indicators_provider_exception(self, service, mock_providers):
        mock_providers['polygon'].fetch_history.side_effect = Exception("Fail")
        closes = list(range(100, 300))
        mock_providers['yfinance'].fetch_history.return_value = pd.DataFrame({'Close': closes, 'Volume': [10] * 200}, index=pd.date_range('2024-01-01', periods=200))
        res = service.get_technical_indicators('AAPL')
        assert 'rsi' in res
