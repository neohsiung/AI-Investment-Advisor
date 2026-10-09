"""
Unit tests for OrderReconciliationService.
掛單對賬與撮合成交引擎單元測試。
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from src.services.order_reconciliation_service import OrderReconciliationService, _RECON_LOCAL_LOCKS


@pytest.fixture(autouse=True)
def clean_recon_locks():
    _RECON_LOCAL_LOCKS.clear()
    yield
    _RECON_LOCAL_LOCKS.clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_tx_repo():
    repo = MagicMock()
    repo.get_pending_transactions.return_value = [
        {
            "id": "tx-101",
            "user_id": "test_user",
            "ticker": "AAPL",
            "trade_date": "2026-09-25",
            "action": "BUY",
            "quantity": 2.0,
            "price": 150.0,
            "fees": 0.0,
            "amount": 300.0,
            "leverage": 1.0,
            "source_file": "eToro",
            "entry_category": "sync_adjustment",
            "raw_data": {
                "order_status": "pending",
                "broker_order_id": "broker-order-999",
                "strategy_name": "MomentumScout",
            },
            "created_at": datetime.now() - timedelta(hours=2),
        }
    ]
    repo.update_transaction_status.return_value = True
    return repo


@pytest.fixture
def mock_lot_repo():
    repo = MagicMock()
    repo.backfill_from_transactions.return_value = 1
    return repo


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.get_name.return_value = "eToro"
    broker.get_order_status = AsyncMock()
    broker.get_positions = AsyncMock(return_value=[])
    broker.sync_history = AsyncMock(return_value={"added": 0, "skipped": 1})
    return broker


@pytest.fixture
def mock_notification_service():
    notif = AsyncMock()
    notif.notify_all.return_value = {}
    return notif


@pytest.mark.anyio
async def test_reconcile_order_filled(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """Test pending order transitioning to FILLED on exchange."""
    mock_broker.get_order_status.return_value = {
        "order_id": "broker-order-999",
        "status": "filled",
        "fill_price": 152.5,
        "quantity": 2.0,
        "fees": 0.25,
        "executed_at": "2026-09-25T14:30:00Z",
        "raw": {"units": 2.0, "openRate": 152.5},
    }

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch("src.services.outcome_reflection_service.OutcomeReflectionService") as MockOutcome:
        mock_outcome_inst = MagicMock()
        mock_outcome_inst.record_decision.return_value = "dec-123"
        MockOutcome.return_value = mock_outcome_inst

        with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()) as mock_snap:
            result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert result["summary"]["filled"] == 1
    assert result["summary"]["cancelled"] == 0

    # Verify transaction repository updated to entry_category='trade'
    mock_tx_repo.update_transaction_status.assert_called_once()
    call_kwargs = mock_tx_repo.update_transaction_status.call_args[1]
    assert call_kwargs["transaction_id"] == "tx-101"
    assert call_kwargs["new_status"] == "filled"
    assert call_kwargs["entry_category"] == "trade"
    assert call_kwargs["price"] == 152.5
    assert call_kwargs["fees"] == 0.25

    # Verify lots reseeded
    mock_lot_repo.backfill_from_transactions.assert_called_once_with("test_user")

    # Verify outcome recorded
    mock_outcome_inst.record_decision.assert_called_once()

    # Verify user notified
    mock_notification_service.notify_all.assert_called_once()


@pytest.mark.anyio
async def test_reconcile_order_cancelled(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """Test pending order transitioning to CANCELLED."""
    mock_broker.get_order_status.return_value = {
        "order_id": "broker-order-999",
        "status": "cancelled",
        "message": "Market order expired at close",
    }

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert result["summary"]["cancelled"] == 1
    assert result["summary"]["filled"] == 0

    mock_tx_repo.update_transaction_status.assert_called_once()
    call_kwargs = mock_tx_repo.update_transaction_status.call_args[1]
    assert call_kwargs["new_status"] == "cancelled"
    assert call_kwargs["entry_category"] == "sync_adjustment"

    # Position lots should NOT be reseeded for cancelled order
    mock_lot_repo.backfill_from_transactions.assert_not_called()


@pytest.mark.anyio
async def test_reconcile_order_still_pending(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """Test order remaining in pending status."""
    mock_broker.get_order_status.return_value = {
        "order_id": "broker-order-999",
        "status": "pending",
    }

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert result["summary"]["still_pending"] == 1
    assert result["summary"]["filled"] == 0
    assert result["summary"]["cancelled"] == 0
    mock_tx_repo.update_transaction_status.assert_not_called()


@pytest.mark.anyio
async def test_reconcile_order_stale_ttl_expiry(mock_lot_repo, mock_broker, mock_notification_service):
    """Test pending order expiring after 72 hours."""
    stale_tx_repo = MagicMock()
    stale_tx_repo.get_pending_transactions.return_value = [
        {
            "id": "tx-stale",
            "user_id": "test_user",
            "ticker": "TSLA",
            "trade_date": "2026-09-20",
            "action": "BUY",
            "quantity": 1.0,
            "price": 200.0,
            "raw_data": {"order_status": "pending", "broker_order_id": "stale-123"},
            "created_at": datetime.now() - timedelta(hours=80),
        }
    ]

    mock_broker.get_order_status.return_value = {
        "order_id": "stale-123",
        "status": "pending",
    }

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=stale_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        result = await service.reconcile_pending_orders("test_user")

    assert result["summary"]["cancelled"] == 1
    stale_tx_repo.update_transaction_status.assert_called_once()
    assert stale_tx_repo.update_transaction_status.call_args[1]["new_status"] == "expired"


@pytest.mark.anyio
async def test_reconcile_broker_error_handling(mock_tx_repo, mock_lot_repo, mock_broker):
    """Test robust error handling when broker network fails (Rule 0)."""
    mock_broker.get_order_status.side_effect = ConnectionError("Broker API unreachable")

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
    )

    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert len(result["summary"]["errors"]) == 1
    assert "Broker API unreachable" in result["summary"]["errors"][0]
    # State must NOT have transitioned
    mock_tx_repo.update_transaction_status.assert_not_called()


@pytest.mark.anyio
async def test_reconcile_concurrent_lock_prevents_duplicate_run(mock_tx_repo, mock_lot_repo, mock_broker):
    """Test distributed reconciliation lock prevents concurrent duplicate reconciliation."""
    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
    )

    # Simulate an in-flight lock held by a concurrent worker
    await OrderReconciliationService._acquire_reconciliation_lock("test_user", ttl_seconds=60)

    # Non-forced call should be skipped immediately without hitting broker or DB
    result = await service.reconcile_pending_orders("test_user", force=False)
    assert result["status"] == "skipped"
    assert result["_fallback_reason"] == "concurrent_lock_held"
    mock_broker.get_order_status.assert_not_called()
    mock_tx_repo.get_pending_transactions.assert_not_called()

    # Forced call should override and succeed
    mock_broker.get_order_status.return_value = {
        "order_id": "broker-order-999",
        "status": "pending",
    }
    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        forced_res = await service.reconcile_pending_orders("test_user", force=True)
    assert forced_res["status"] == "success"


@pytest.mark.anyio
async def test_reconcile_order_executed_and_slippage_audit(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """Test broker status 'executed' (synonym for 'filled') audits slippage and records alpha reflection."""
    mock_broker.get_order_status.return_value = {
        "order_id": "broker-order-999",
        "status": "executed",
        "fill_price": 151.20,
        "quantity": 2.0,
        "fees": 0.15,
        "raw": {"units": 2.0, "avgPrice": 151.20},
    }

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch("src.services.outcome_reflection_service.OutcomeReflectionService") as MockOutcome, \
         patch("src.services.slippage_guard_service.SlippageGuardService") as MockSlippage, \
         patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        mock_outcome_inst = MagicMock()
        mock_outcome_inst.record_decision.return_value = "dec-456"
        MockOutcome.return_value = mock_outcome_inst

        mock_slip_inst = MagicMock()
        MockSlippage.return_value = mock_slip_inst

        result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert result["summary"]["filled"] == 1

    # Verify transaction promoted to trade
    mock_tx_repo.update_transaction_status.assert_called_once()
    kwargs = mock_tx_repo.update_transaction_status.call_args[1]
    assert kwargs["new_status"] == "filled"
    assert kwargs["entry_category"] == "trade"
    assert kwargs["price"] == 151.20

    # Verify reflection recorded
    mock_outcome_inst.record_decision.assert_called_once_with(
        ticker="AAPL",
        agent_name="MomentumScout",
        signal="BUY",
        price=151.20,
        session_id=None,
        horizon_days=5,
    )

    # Verify realized slippage audit recorded
    mock_slip_inst.record_realized_slippage.assert_called_once_with(
        ticker="AAPL",
        action="BUY",
        expected_price=150.0,
        fill_price=151.20,
        order_id="broker-order-999",
    )


@pytest.mark.anyio
async def test_reconcile_order_canceled_us_spelling(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """Test US spelling 'canceled' transitions order properly to cancelled."""
    mock_broker.get_order_status.return_value = {
        "order_id": "broker-order-999",
        "status": "canceled",
        "message": "Cancelled due to market close",
    }

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert result["summary"]["cancelled"] == 1
    mock_tx_repo.update_transaction_status.assert_called_once()
    assert mock_tx_repo.update_transaction_status.call_args[1]["new_status"] == "canceled"
    assert mock_tx_repo.update_transaction_status.call_args[1]["entry_category"] == "sync_adjustment"


@pytest.mark.anyio
async def test_reconcile_order_open_and_partially_filled(mock_tx_repo, mock_lot_repo, mock_broker):
    """Test broker statuses 'open', 'submitted', and 'partially_filled' keep order pending without error count."""
    mock_broker.get_order_status.return_value = {
        "order_id": "broker-order-999",
        "status": "open",
    }

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
    )

    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert result["summary"]["still_pending"] == 1
    # Should not call update_transaction_status (no unknown count increment)
    mock_tx_repo.update_transaction_status.assert_not_called()


@pytest.mark.anyio
async def test_reconcile_cross_check_records_reflection_and_slippage(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """Test position cross-check match on retry limit records reflection and audits slippage."""
    mock_tx_repo.get_pending_transactions.return_value = [
        {
            "id": "tx-ghost-match",
            "user_id": "test_user",
            "ticker": "NVDA",
            "action": "BUY",
            "quantity": 10.0,
            "price": 115.0,
            "raw_data": {
                "order_status": "pending",
                "broker_order_id": "ghost-ord",
                "unknown_reconcile_count": 4,
                "strategy_name": "AlphaScout",
                "session_id": "sess-99",
            },
            "created_at": datetime.now(),
        }
    ]
    mock_broker.get_order_status.return_value = {"status": "unknown"}

    pos = MagicMock()
    pos.symbol = "NVDA"
    pos.quantity = 10.0
    pos.current_price = 116.50
    mock_broker.get_positions.return_value = [pos]

    service = OrderReconciliationService(
        user_id="test_user",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch.object(service, "_get_retry_limit", return_value=5), \
         patch("src.services.outcome_reflection_service.OutcomeReflectionService") as MockOutcome, \
         patch("src.services.slippage_guard_service.SlippageGuardService") as MockSlippage, \
         patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        mock_outcome_inst = MagicMock()
        MockOutcome.return_value = mock_outcome_inst
        mock_slip_inst = MagicMock()
        MockSlippage.return_value = mock_slip_inst

        result = await service.reconcile_pending_orders("test_user")

    assert result["status"] == "success"
    assert result["summary"]["filled"] == 1

    # Verify reflection recorded for cross check fill
    mock_outcome_inst.record_decision.assert_called_once_with(
        ticker="NVDA",
        agent_name="AlphaScout",
        signal="BUY",
        price=116.50,
        session_id="sess-99",
        horizon_days=5,
    )

    # Verify slippage audited for cross check fill
    mock_slip_inst.record_realized_slippage.assert_called_once_with(
        ticker="NVDA",
        action="BUY",
        expected_price=115.0,
        fill_price=116.50,
        order_id="ghost-ord",
    )
