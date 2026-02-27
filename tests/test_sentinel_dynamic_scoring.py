import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.sentinel_service import SentinelService

@pytest.fixture
def mock_settings():
    svc = MagicMock()
    # Mock settings: emergency=10, hedge=5
    def mock_get(uid, key):
        if key == "emergency_liquidation_score": return 10
        if key == "auto_hedge_score": return 5
        return None
    svc.get.side_effect = mock_get
    return svc

@pytest.fixture
def sentinel_svc(mock_settings):
    with patch('src.services.sentinel_service.SettingsService', return_value=mock_settings):
        svc = SentinelService()
        svc.settings_service = mock_settings # Inject
        return svc

@pytest.mark.asyncio
async def test_sentinel_uses_dynamic_scores(sentinel_svc):
    # Mock necessary dependencies
    mock_auto_trade = AsyncMock()
    mock_tx_service = MagicMock()
    mock_tx_service.get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.services.automated_trading_service.AutomatedTradingService', return_value=mock_auto_trade):
        with patch('src.services.transaction_service.TransactionService', return_value=mock_tx_service):
            await sentinel_svc._trigger_emergency_protocol("user123", "Extreme Volatility")
            
    # Check calls to evaluate_and_execute_trade
    # 1. AAPL liquidation
    # 2. SQQQ hedge
    assert mock_auto_trade.evaluate_and_execute_trade.call_count >= 2
    
    calls = mock_auto_trade.evaluate_and_execute_trade.call_args_list
    
    # Verify AAPL call uses emergency_score=10
    aapl_call = next(c for c in calls if c.kwargs['ticker'] == 'AAPL')
    assert aapl_call.kwargs['confidence_score'] == 10
    
    # Verify SQQQ call uses hedge_score=5
    sqqq_call = next(c for c in calls if c.kwargs['ticker'] == 'SQQQ')
    assert sqqq_call.kwargs['confidence_score'] == 5
