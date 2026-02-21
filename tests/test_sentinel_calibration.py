import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from src.services.sentinel_service import SentinelService

@pytest.fixture
def mock_market_service():
    service = MagicMock()
    # Mock VIX history: normal distribution around 20 with some spikes
    vix_data = {
        "close": [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 30, 35, 20, 18, 17, 16, 15] * 14 # ~252 days
    }
    service.get_ohlcv.return_value = vix_data
    return service

@pytest.fixture
def sentinel_svc(mock_market_service):
    with patch('src.services.sentinel_service.AlchemySentinelRepository'), \
         patch('src.services.sentinel_service.SettingsService'), \
         patch('src.services.sentinel_service.InternetSearchService'), \
         patch('src.services.sentinel_service.TransactionService'), \
         patch('src.services.sentinel_service.CouncilService'):
        svc = SentinelService(market_service=mock_market_service)
        return svc

def test_calibrate_thresholds_logic(sentinel_svc, mock_market_service):
    # Manually trigger calibration since it's called in __init__
    sentinel_svc._calibrate_thresholds()
    
    # Check if update_threshold was called for VIX
    assert sentinel_svc.repo.update_threshold.call_count >= 2
    
    # Verify the calls
    calls = sentinel_svc.repo.update_threshold.call_args_list
    vix_high_call = next(c for c in calls if c[0][0] == "vix_high")
    vix_extreme_call = next(c for c in calls if c[0][0] == "vix_extreme")
    
    # In our mock data, 90th percentile of [15...35] should be around 25-30
    assert vix_high_call[0][1] > 15
    assert vix_extreme_call[0][1] > vix_high_call[0][1]
    
    print(f"Calibrated VIX High: {vix_high_call[0][1]}")
    print(f"Calibrated VIX Extreme: {vix_extreme_call[0][1]}")

def test_vix_anomaly_detection(sentinel_svc, mock_market_service):
    # Set up historical data for Z-score calculation
    # Mean: approx 20, Std: approx 5
    # Current VIX: 40 (Spike!)
    vix_data = {
        "close": [20] * 30 + [40]
    }
    mock_market_service.get_ohlcv.return_value = vix_data
    sentinel_svc.thresholds = {"vix_spike_sigma": 2.5}
    
    triggers = sentinel_svc._check_vix_anomaly()
    
    assert len(triggers) > 0
    assert "🔴 VIX Spike" in triggers[0]["text"]
    assert triggers[0]["value"] == 40
