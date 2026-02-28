import pytest
from unittest.mock import MagicMock, patch
from src.data.providers.fmp_provider import FMPProvider

@pytest.fixture
def fmp():
    return FMPProvider(api_key="mock_key")

def test_fetch_key_metrics(fmp):
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"peRatioTTM": 15.5, "symbol": "AAPL"}]
        
        metrics = fmp.fetch_key_metrics("AAPL")
        
        assert metrics["peRatioTTM"] == 15.5
        assert "symbol" in metrics
        mock_get.assert_called_once()
        assert "key-metrics-ttm" in mock_get.call_args[0][0]
        assert mock_get.call_args[1]["params"]["symbol"] == "AAPL"

def test_fetch_financial_ratios(fmp):
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"grossProfitMarginTTM": 0.45}]
        
        ratios = fmp.fetch_financial_ratios("AAPL")
        
        assert ratios["grossProfitMarginTTM"] == 0.45
        mock_get.assert_called_once()
        assert "ratios-ttm" in mock_get.call_args[0][0]
        assert mock_get.call_args[1]["params"]["symbol"] == "AAPL"

def test_fetch_key_metrics_fail(fmp):
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 404
        metrics = fmp.fetch_key_metrics("AAPL")
        assert metrics == {}

def test_fetch_financial_ratios_no_key():
    fmp_no_key = FMPProvider(api_key=None)
    # Monkeypatch likely already handled by init logic to warn
    # FMPProvider usually requires key or env var.
    # If init with None and no env, it warns.
    # Let's verify method returns empty if no key
    fmp_no_key.api_key = None # Force None
    assert fmp_no_key.fetch_financial_ratios("AAPL") == {}
