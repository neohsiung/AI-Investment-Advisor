import pytest
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.market_data_service import MarketDataService

@pytest.fixture
def mock_settings_service():
    service = MagicMock()
    # Default to enabled and having keys
    service.get_setting.side_effect = lambda key, default=None: True if "enabled" in key else "test_key"
    return service

@pytest.fixture
def market_data_service(mock_settings_service):
    return MarketDataService(user_id="test_user", settings_service=mock_settings_service)

def test_is_provider_enabled(market_data_service, mock_settings_service):
    # Test yahoo_finance (always enabled)
    mock_provider = MagicMock()
    mock_provider.id = "yahoo_finance"
    assert market_data_service._is_provider_enabled(mock_provider) is True

    # Test enabled with key
    mock_provider.id = "polygon"
    mock_settings_service.get_setting.side_effect = lambda key, default=None: True if "enabled" in key else "key_val"
    assert market_data_service._is_provider_enabled(mock_provider) is True

    # Test disabled
    mock_settings_service.get_setting.side_effect = lambda key, default=None: False if "enabled" in key else "key_val"
    assert market_data_service._is_provider_enabled(mock_provider) is False

    # Test enabled but no key
    mock_settings_service.get_setting.side_effect = lambda key, default=None: True if "enabled" in key else None
    assert market_data_service._is_provider_enabled(mock_provider) is False

@pytest.mark.asyncio
async def test_get_current_prices(market_data_service):
    # Mock providers
    market_data_service.polygon.fetch_current_prices = MagicMock(return_value={"AAPL": 150.0})
    market_data_service.tiingo.fetch_current_prices = MagicMock(return_value={"MSFT": 300.0})
    
    # Disable others to avoid noise
    with patch.object(market_data_service, '_is_provider_enabled', side_effect=lambda p: p.id in ["polygon", "tiingo"]):
        prices = await market_data_service.get_current_prices(["AAPL", "MSFT"])
        assert prices["AAPL"] == 150.0
        assert prices["MSFT"] == 300.0
        
@pytest.mark.asyncio
async def test_get_price_from_search(market_data_service):
    market_data_service.search_service.search_financial_context = AsyncMock(return_value=[
        {"snippet": "The current price of AAPL is $155.50", "title": "AAPL Stock"}
    ])
    
    price = await market_data_service.get_price_from_search("AAPL")
    assert price == 155.50

def test_get_ohlcv(market_data_service):
    mock_df = pd.DataFrame({
        "Open": [100, 101],
        "High": [105, 106],
        "Low": [95, 96],
        "Close": [102, 103],
        "Volume": [1000, 1100]
    }, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    
    market_data_service.polygon.fetch_history = MagicMock(return_value=mock_df)
    
    with patch.object(market_data_service, '_is_provider_enabled', return_value=True):
        data = market_data_service.get_ohlcv("AAPL", days=2)
        assert data["close"] == [102, 103]
        assert data["date"] == ["2024-01-01", "2024-01-02"]

def test_get_technical_indicators(market_data_service):
    # Create enough data for indicators (need > 26 for some)
    dates = pd.date_range(start="2023-01-01", periods=100)
    mock_df = pd.DataFrame({
        "Open": [100] * 100,
        "High": [110] * 100,
        "Low": [90] * 100,
        "Close": [105] * 100,
        "Volume": [5000] * 100
    }, index=dates)
    
    market_data_service.polygon.fetch_history = MagicMock(return_value=mock_df)
    
    with patch.object(market_data_service, '_is_provider_enabled', return_value=True):
        indicators = market_data_service.get_technical_indicators("AAPL")
        assert "rsi" in indicators
        assert "macd" in indicators
        assert indicators["rsi"] == 50 # Constant price means RSI 50 (or similar)

def test_get_macro_data(market_data_service):
    market_data_service.fred.fred_service.get_macro_indicators = MagicMock(return_value={"GDP": {"value": 2.5}})
    market_data_service.yfinance.fetch_current_prices = MagicMock(return_value={"^VIX": 15.0})
    
    with patch.object(market_data_service, '_is_provider_enabled', return_value=True):
        macro = market_data_service.get_macro_data()
        assert macro["economics"]["GDP"]["value"] == 2.5
        assert macro["market_indicators"]["^VIX"] == 15.0

def test_get_yield_curve_inversion(market_data_service):
    market_data_service.fred.fred_service.get_macro_indicators = MagicMock(return_value={"10Y2Y_Spread": {"value": -0.5}})
    
    with patch.object(market_data_service, '_is_provider_enabled', return_value=True):
        yc = market_data_service.get_yield_curve_inversion()
        assert yc["inverted"] is True
        assert yc["spread"] == -0.5

def test_get_news(market_data_service):
    mock_news = [{"title": "News 1", "url": "http://example.com"}]
    market_data_service.tiingo.fetch_news = MagicMock(return_value=mock_news)
    
    with patch.object(market_data_service, '_is_provider_enabled', return_value=True):
        news = market_data_service.get_news("AAPL")
        assert news == mock_news

def test_get_financials(market_data_service):
    mock_info = {"market_cap": 2000000000000, "pe_ratio": 30}
    market_data_service.fmp.fetch_info = MagicMock(return_value=mock_info)
    
    with patch.object(market_data_service, '_is_provider_enabled', return_value=True):
        info = market_data_service.get_financials("AAPL")
        assert info == mock_info
