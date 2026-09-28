"""
Unit tests for OrderReconciliationService.
掛單對賬與撮合成交引擎單元測試。
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from src.services.order_reconciliation_service import OrderReconciliationService


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
