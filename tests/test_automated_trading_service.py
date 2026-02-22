import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.automated_trading_service import AutomatedTradingService
from src.domain.trading import OrderAction, OrderType

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock()
    # Default behavior: enabled, threshold 9
    def get_mock(user_id, key):
        if key == "ai_trading_enabled": return "true"
        if key == "auto_trade_threshold": return "9"
        return None
    repo.get.side_effect = get_mock
    return repo

@pytest.fixture
def mock_interaction_service():
    service = AsyncMock()
    service.request_approval.return_value = (True, "APPROVED")
    return service

@pytest.fixture
def mock_notification_service():
    service = AsyncMock()
    service.notify_all.return_value = {}
    return service

@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.get_name.return_value = "MockBroker"
    # Execute order returns a mock success status
    broker.execute_order.return_value = {"status": "success", "order_id": "123"}
    return broker

@pytest.fixture
def test_svc(mock_settings_repo, mock_interaction_service, mock_notification_service):
    return AutomatedTradingService(
        settings_repo=mock_settings_repo,
        interaction_service=mock_interaction_service,
        notification_service=mock_notification_service
    )

@pytest.mark.asyncio
async def test_auto_execute_when_score_above_threshold(test_svc, mock_broker):
    user_id = "test_user"
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker):
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "AAPL", "buy", 10.0, 9, "High momentum"
        )
        
    assert res["status"] == "success"
    mock_broker.execute_order.assert_called_once()
    
    # Check that notification was called indicating Auto-Approved
    test_svc.notification_service.notify_all.assert_called_once()
    call_args = test_svc.notification_service.notify_all.call_args[1]
    assert "Auto-Approved" in call_args["content"]

@pytest.mark.asyncio
async def test_require_approval_when_score_below_threshold(test_svc, mock_interaction_service, mock_broker):
    user_id = "test_user"
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker):
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "AAPL", "buy", 10.0, 8, "Moderate momentum"
        )
        
    # Interaction service should have been called
    mock_interaction_service.request_approval.assert_called_once()
    assert res["status"] == "success"
    
    test_svc.notification_service.notify_all.assert_called_once()
    call_args = test_svc.notification_service.notify_all.call_args[1]
    assert "User-Approved" in call_args["content"]

@pytest.mark.asyncio
async def test_rejection_or_timeout(test_svc, mock_interaction_service, mock_broker):
    user_id = "test_user"
    # Mocking interaction service to return False (rejected or timeout)
    mock_interaction_service.request_approval.return_value = (False, "REJECTED")
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker):
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "AAPL", "buy", 10.0, 8, "Moderate momentum"
        )
        
    # Should be rejected
    assert res["status"] == "rejected_or_timeout"
    mock_broker.execute_order.assert_not_called()
    
    # Notification for rejection should have been sent
    test_svc.notification_service.notify_all.assert_called_once()
    call_kwargs = test_svc.notification_service.notify_all.call_args[1]
    assert "Cancelled" in call_kwargs["title"] or "取消" in call_kwargs["title"]

@pytest.mark.asyncio
async def test_disabled_trading_returns_blocked(test_svc):
    # Set mock to disabled
    def get_mock(user_id, key):
        if key == "ai_trading_enabled": return "false"
        return "10"
    test_svc.settings_repo.get.side_effect = get_mock
    
    res = await test_svc.evaluate_and_execute_trade("u1", "TSLA", "buy", 1, 10, "test")
    
    assert res["status"] == "blocked"
