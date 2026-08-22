import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.automated_trading_service import AutomatedTradingService
from src.domain.trading import OrderAction, OrderType

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture(autouse=True)
def allow_trading_protections():
    """
    Isolate these tests from TradingProtectionsService.

    2026-08-02: protections now fail CLOSED — an internal error blocks the BUY
    instead of allowing it. These tests exercise confidence-threshold branching
    against an in-memory SQLite with no `decision_outcomes` table, so without
    this stub every BUY would legitimately be blocked. Fail-closed behaviour
    itself is covered in tests/unit/services/test_protections_fail_closed.py.
    2026-08-02：風控改為 fail-closed；本檔測的是信心度分支，故隔離風控相依。
    """
    with patch('src.services.trading_protections_service.TradingProtectionsService') as MockProt:
        MockProt.return_value.check.return_value = None
        yield MockProt

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
    broker.execute_order = AsyncMock(return_value={"status": "success", "order_id": "123"})
    broker.get_positions = AsyncMock(return_value=[])
    
    # Mock account for position sizing guards
    account = MagicMock()
    account.total_equity = 1000.0
    account.available_cash = 500.0
    broker.get_account = AsyncMock(return_value=account)
    
    broker.sync_history = AsyncMock(return_value=True)
    
    return broker

@pytest.fixture
def test_svc(mock_settings_repo, mock_interaction_service, mock_notification_service):
    return AutomatedTradingService(
        settings_repo=mock_settings_repo,
        interaction_service=mock_interaction_service,
        notification_service=mock_notification_service
    )

@pytest.mark.anyio
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
    # 2026-08-11: the card was rewritten (src/services/decision_card.py), so
    # the literal "Auto-Approved" label is gone. Assert on what the card must
    # now convey instead: that it executed without asking, and what the score
    # was measured against — an auto-executed trade is the only record the
    # user gets of a decision they were never consulted on.
    # 2026-08-11：卡片已改寫，原本的 "Auto-Approved" 字樣不再存在。改為斷言卡片
    # 現在必須傳達的內容：未經詢問即執行，以及分數對照的門檻。
    content = call_kwargs["content"]
    assert "自動執行" in content
    assert "分數 9.0/10" in content
    assert "自動門檻 9.0" in content

@pytest.mark.anyio
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

@pytest.mark.anyio
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

@pytest.mark.anyio
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

@pytest.mark.anyio
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

@pytest.mark.anyio
async def test_skip_when_score_equals_zero(test_svc, mock_broker):
    """Score 0 is below any reasonable min_threshold -> skip."""
    with patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock) as mock_notify:
        res = await test_svc.evaluate_and_execute_trade("u1", "TSLA", "buy", 1, 0, "No confidence")
    
    assert res["status"] == "skipped"
    mock_notify.assert_not_called()

@pytest.mark.anyio
async def test_exact_min_threshold_triggers_approval(test_svc, mock_interaction_service, mock_broker):
    """Score exactly equal to min_threshold (3) -> should trigger approval, NOT skip."""
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker), \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock):
        res = await test_svc.evaluate_and_execute_trade("u1", "AAPL", "buy", 10.0, 3, "Borderline")
    
    mock_interaction_service.request_approval.assert_called_once()
    assert res["status"] == "success"

@pytest.mark.anyio
async def test_notify_via_direct_service(test_svc, mock_notification_service):
    """Verify _notify_via_api dispatches via direct NotificationService."""
    with patch('src.services.notification_settings_manager.NotificationSettingsManager.get_active_notification_channels', return_value=["telegram"]):
        await test_svc._notify_via_api(
            user_id="test_user",
            title="Test Title",
            content="Test Content",
            category="approval"
        )
        
        mock_notification_service.notify_all.assert_called_once()
        call_kwargs = mock_notification_service.notify_all.call_args[1]
        
        assert call_kwargs["user_id"] == "test_user"
        assert "telegram" in call_kwargs["channels"]
        assert call_kwargs["category"] == "approval"

# ──────────────────────────────────────────
# SELL Position Sizing Guard Tests (v7.0)
# ──────────────────────────────────────────

@pytest.fixture
def mock_position():
    """Create a mock position with symbol and quantity attributes."""
    pos = MagicMock()
    pos.symbol = "TSLA"
    pos.quantity = 0.5
    return pos

@pytest.fixture
def mock_broker_with_positions(mock_position):
    broker = MagicMock()
    broker.get_name.return_value = "MockBroker"
    broker.execute_order = AsyncMock(return_value={"status": "success", "order_id": "456"})
    broker.get_positions = AsyncMock(return_value=[mock_position])
    broker.get_account = AsyncMock() # Empty mock
    return broker

@pytest.mark.anyio
async def test_sell_guard_clamps_quantity_to_actual_holding(test_svc, mock_broker_with_positions):
    """SELL quantity > actual holding → quantity clamped to actual holding (0.5)."""
    user_id = "test_user"
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker_with_positions), \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock):
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "TSLA", "sell", 1.0, 9, "Reduce TSLA exposure"
        )
    
    assert res["status"] == "success"
    # Verify the order was executed with clamped quantity (0.5, not 1.0)
    call_args = mock_broker_with_positions.execute_order.call_args
    order = call_args[0][0] if call_args[0] else call_args[1].get('order')
    assert order.quantity == 0.5

@pytest.mark.anyio
async def test_sell_guard_skips_when_no_holding(test_svc):
    """SELL with 0 actual holding → skip trade entirely."""
    user_id = "test_user"
    
    broker = MagicMock()
    broker.get_name.return_value = "MockBroker"
    broker.get_positions = AsyncMock(return_value=[])  # No positions
    broker.get_account = AsyncMock()
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=broker):
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "TSLA", "sell", 1.0, 9, "Exit TSLA"
        )
    
    assert res["status"] == "skipped"
    assert "No active position" in res["reason"]
    broker.execute_order.assert_not_called()

@pytest.mark.anyio
async def test_sell_guard_passthrough_when_within_holding(test_svc, mock_broker_with_positions):
    """SELL quantity <= actual holding → no clamping needed."""
    user_id = "test_user"
    
    with patch('src.services.automated_trading_service.BrokerFactory.get_broker', return_value=mock_broker_with_positions), \
         patch.object(test_svc, '_notify_via_api', new_callable=AsyncMock):
        res = await test_svc.evaluate_and_execute_trade(
            user_id, "TSLA", "sell", 0.3, 9, "Partial reduce"
        )
    
    assert res["status"] == "success"
    call_args = mock_broker_with_positions.execute_order.call_args
    order = call_args[0][0] if call_args[0] else call_args[1].get('order')
    assert order.quantity == 0.3

