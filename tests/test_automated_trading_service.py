import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.automated_trading_service import AutomatedTradingService
from src.domain.trading import OrderAction, OrderType

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock()
    # Default behavior: enabled, threshold 9, min_threshold 3
    def get_mock(user_id, key):
        if key == "ai_trading_enabled": return "true"
        if key == "auto_trade_threshold": return "9"
        if key == "auto_trade_min_threshold": return "3"
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
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker), \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock) as mock_notify:
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "AAPL", "buy", 10.0, 9, "High momentum"
        )
        
    assert res["status"] == "success"
    mock_broker.execute_order.assert_called_once()
    
    # Check that notification was dispatched via HTTP API
    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args[1]
    assert "Auto-Approved" in call_kwargs["content"]

@pytest.mark.asyncio
async def test_require_approval_when_score_between_thresholds(test_svc, mock_interaction_service, mock_broker):
    """Score between min (3) and max (9) -> request approval via interaction service."""
    user_id = "test_user"
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker), \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock):
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "AAPL", "buy", 10.0, 5, "Moderate momentum"
        )
        
    # Interaction service should have been called
    mock_interaction_service.request_approval.assert_called_once()
    assert res["status"] == "success"

@pytest.mark.asyncio
async def test_rejection_or_timeout(test_svc, mock_interaction_service, mock_broker):
    user_id = "test_user"
    # Mocking interaction service to return False (rejected or timeout)
    mock_interaction_service.request_approval.return_value = (False, "REJECTED")
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker), \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock) as mock_notify:
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "AAPL", "buy", 10.0, 5, "Moderate momentum"
        )
        
    # Should be rejected
    assert res["status"] == "rejected_or_timeout"
    mock_broker.execute_order.assert_not_called()
    
    # Notification for rejection should have been sent via API
    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args[1]
    assert "取消" in call_kwargs["title"] or "Cancelled" in call_kwargs["title"]

@pytest.mark.asyncio
async def test_disabled_trading_returns_blocked(test_svc):
    # Set mock to disabled
    def get_mock(user_id, key):
        if key == "ai_trading_enabled": return "false"
        return "10"
    test_svc.settings_repo.get.side_effect = get_mock
    
    res = await test_svc.evaluate_and_execute_trade("u1", "TSLA", "buy", 1, 10, "test")
    
    assert res["status"] == "blocked"

# ──────────────────────────────────────────
# NEW: Min Threshold Tests
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_skip_when_score_below_min_threshold(test_svc, mock_broker):
    """Score below min_threshold (3) -> skip silently, no broker/notification calls."""
    user_id = "test_user"
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker) as mock_factory, \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock) as mock_notify:
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "AAPL", "buy", 10.0, 2, "Low confidence"
        )
    
    assert res["status"] == "skipped"
    assert "below minimum threshold" in res["reason"]
    
    # No broker or notification should be called
    mock_broker.execute_order.assert_not_called()
    mock_notify.assert_not_called()

@pytest.mark.asyncio
async def test_skip_when_score_equals_zero(test_svc, mock_broker):
    """Score 0 is below any reasonable min_threshold -> skip."""
    with patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock) as mock_notify:
        res = await test_svc.evaluate_and_execute_trade("u1", "TSLA", "buy", 1, 0, "No confidence")
    
    assert res["status"] == "skipped"
    mock_notify.assert_not_called()

@pytest.mark.asyncio
async def test_exact_min_threshold_triggers_approval(test_svc, mock_interaction_service, mock_broker):
    """Score exactly equal to min_threshold (3) -> should trigger approval, NOT skip."""
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker), \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock):
        res = await test_svc.evaluate_and_execute_trade("u1", "AAPL", "buy", 10.0, 3, "Borderline")
    
    mock_interaction_service.request_approval.assert_called_once()
    assert res["status"] == "success"

@pytest.mark.asyncio
async def test_notify_via_api_sends_http_post(test_svc):
    """Verify _notify_via_api dispatches HTTP POST with correct payload including LINE channel."""
    mock_response = MagicMock()
    mock_response.status_code = 202
    
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await test_svc._notify_via_api(
            user_id="test_user",
            title="Test Title",
            content="Test Content",
            category="approval"
        )
        
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        
        assert payload["user_id"] == "test_user"
        assert "line" in payload["channels"]
        assert payload["category"] == "approval"
