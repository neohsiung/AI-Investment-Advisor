import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.etoro_service import EtoroService
from src.domain.trading import Order, OrderAction

@pytest.fixture
def service():
    with patch('src.services.etoro_service.os.path.exists', return_value=False):
        svc = EtoroService(base_url="http://mock-etoro", mode="demo")
        # Mock repos directly on service
        svc.transaction_repo = MagicMock()
        svc.settings_repo = MagicMock()
        svc.risk_manager.transaction_repo = svc.transaction_repo
        svc.risk_manager.settings_repo = svc.settings_repo
        
        # Default Settings
        def mock_get(uid, k, default=None):
            if k == "ai_trading_enabled": return "true"
            if k == "ai_max_daily_trades": return "10"
            return default
        svc.risk_manager.settings_repo.get.side_effect = mock_get
        
        # Aggressively mock all network-calling instance methods
        svc.get_history = AsyncMock(return_value=[])
        svc.get_positions = AsyncMock(return_value=[])
        svc.get_watchlists = AsyncMock(return_value=[])
        svc.get_account = AsyncMock(return_value=None)
        svc._fetch_portfolio_raw = AsyncMock(return_value={}) 
        svc._fetch_history_raw = AsyncMock(return_value=[])
        
        return svc

def test_check_constraints_ok(service):
    # Mock transaction count on RiskManager
    service.risk_manager._get_daily_trade_count = MagicMock(return_value=5)
    service.risk_manager._is_circuit_breaker_triggered = MagicMock(return_value=False)
    
    # Test directly on Risk Manager
    result = service.risk_manager.check_constraints("user1")
    assert result is True

def test_check_constraints_max_daily(service):
    # Mock on RiskManager
    service.risk_manager._get_daily_trade_count = MagicMock(return_value=10)
    result = service.risk_manager.check_constraints("user1")
    assert result is False

def test_circuit_breaker_trigger(service):
    # Mock on RiskManager
    service.risk_manager._get_daily_trade_count = MagicMock(return_value=5)
    service.risk_manager._is_circuit_breaker_triggered = MagicMock(return_value=True)
    
    result = service.risk_manager.check_constraints("user1")
    assert result is False
    
    # Check disable
    service.settings_repo.set.assert_called_with("user1", "ai_trading_enabled", "false")

@pytest.mark.asyncio
async def test_sync_history_logic(service):
    # We need to test the REAL logic of sync_history, so we un-mock it
    from src.services.etoro_service import EtoroService
    real_sync = EtoroService.sync_history
    
    # Mock dependencies of sync_history
    service.get_history = AsyncMock(return_value=[
        {
            "instrumentId": "1", 
            "openTimestamp": "2025-01-01T10:00:00", 
            "isBuy": True, 
            "units": 100, 
            "openRate": 150,
            "leverage": 1,
            "fees": 0
        }
    ])
    service.get_watchlists = AsyncMock(return_value={})
    service.transaction_repo.get_all_by_user.return_value = []
    service._id_to_symbol = {"1": "AAPL"}
    
    # Test Sync
    res = await real_sync(service, "user1")
    assert res['added'] == 1
    service.transaction_repo.add.assert_called_once()
    
@pytest.mark.asyncio
async def test_execute_order_wraps_risk_logic(service):
    # We need real logic for execute_order
    from src.services.etoro_service import EtoroService
    real_exec = EtoroService.execute_order
    
    # Mock dependencies
    service.risk_manager.check_constraints = MagicMock(return_value=False)
    service.get_history = AsyncMock(return_value=[])
    service.get_positions = AsyncMock(return_value=[])
    service._fetch_portfolio_raw = AsyncMock(return_value={}) 
    
    service.user_id = "test_user"
    order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=100)
    
    res = await real_exec(service, order)
    assert res['status'] == 'failed'
    assert "Risk Manager" in res['reason']
