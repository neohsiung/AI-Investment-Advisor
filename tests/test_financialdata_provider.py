import pytest
from unittest.mock import MagicMock, patch
from src.data.providers.financialdata_provider import FinancialDataProvider
from src.services.settings_service import SettingsService

@pytest.fixture
def mock_settings():
    service = MagicMock(spec=SettingsService)
    service.get_all_settings.return_value = {"financialdata_api_key": "test_key"}
    return service

def test_financialdata_init(mock_settings):
    provider = FinancialDataProvider(settings_service=mock_settings)
    assert provider.api_key == "test_key"
    assert provider.base_url == "https://financialdata.net/api/v1"

@patch("requests.get")
def test_fetch_current_prices(mock_get, mock_settings):
    provider = FinancialDataProvider(settings_service=mock_settings)
    
    # Mock response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"close": 150.5, "symbol": "AAPL"}]
    mock_get.return_value = mock_resp
    
    prices = provider.fetch_current_prices(["AAPL"])
    assert prices["AAPL"] == 150.5
    mock_get.assert_called_once()

@patch("requests.get")
def test_fetch_insider_trading(mock_get, mock_settings):
    provider = FinancialDataProvider(settings_service=mock_settings)
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"full_name": "John Doe", "transaction_type": "Purchase"}]
    mock_get.return_value = mock_resp
    
    insider = provider.fetch_insider_trading("AAPL")
    assert len(insider) == 1
    assert insider[0]["full_name"] == "John Doe"

@patch("requests.get")
def test_fetch_etf_holdings(mock_get, mock_settings):
    provider = FinancialDataProvider(settings_service=mock_settings)
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"symbol": "AAPL", "weight": 0.07}]
    mock_get.return_value = mock_resp
    
    holdings = provider.fetch_etf_holdings("SPY")
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "AAPL"
