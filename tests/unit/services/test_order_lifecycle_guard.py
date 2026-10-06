"""
Comprehensive Unit Tests for E5 Dynamic Order Lifecycle Guard & Ghost Order Reconciliation Engine.
E5 動態訂單生命週期守衛、幽靈訂單非同步對賬自動重試與日內防磨損節流閥單元測試集。
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from src.services.order_reconciliation_service import OrderReconciliationService
from src.services.automated_trading_service import AutomatedTradingService
from src.services.order_inflight_lock_service import OrderInflightLockService, _LOCAL_LOCKS
from src.domain.trading import OrderAction, OrderType
from src.repositories.transaction_repository import AlchemyTransactionRepository, ENTRY_CATEGORY_SYNC_ADJUSTMENT


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clean_test_env():
    _LOCAL_LOCKS.clear()
    yield
    _LOCAL_LOCKS.clear()


@pytest.fixture
def mock_tx_repo():
    repo = MagicMock(spec=AlchemyTransactionRepository)
    repo.get_pending_transactions.return_value = []
    repo.update_transaction_status.return_value = True
    repo.repair_zero_price_transactions.return_value = 0
    repo.get_all_by_user.return_value = []
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
    broker.execute_order = AsyncMock(return_value={"status": "success", "order_id": "ord-100", "execution_status": "executed"})
    account = MagicMock()
    account.total_equity = 2000.0
    account.available_cash = 1000.0
    broker.get_account = AsyncMock(return_value=account)
    return broker


@pytest.fixture
def mock_notification_service():
    notif = AsyncMock()
    notif.notify_all.return_value = {}
    return notif


# ==============================================================================
# 1. Ghost Order Reconciliation Tests
# ==============================================================================

@pytest.mark.anyio
async def test_reconcile_unknown_status_increments_count(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """Test order with 'unknown' status increments unknown_reconcile_count and remains pending."""
    mock_tx_repo.get_pending_transactions.return_value = [
        {
            "id": "tx-unknown-1",
            "user_id": "user-1",
            "ticker": "TSM",
            "action": "BUY",
            "quantity": 2.0,
            "price": 180.0,
            "raw_data": {"order_status": "pending", "broker_order_id": "b-ord-1", "unknown_reconcile_count": 0},
            "created_at": datetime.now(),
        }
    ]
    mock_broker.get_order_status.return_value = {"status": "unknown"}

    service = OrderReconciliationService(
        user_id="user-1",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        res = await service.reconcile_pending_orders("user-1")

    assert res["status"] == "success"
    assert res["summary"]["still_pending"] == 1
    assert res["summary"]["filled"] == 0
    assert res["summary"]["cancelled"] == 0

    mock_tx_repo.update_transaction_status.assert_called_once()
    call_kwargs = mock_tx_repo.update_transaction_status.call_args[1]
    assert call_kwargs["new_status"] == "pending"
    assert call_kwargs["extra_raw"]["unknown_reconcile_count"] == 1


@pytest.mark.anyio
async def test_reconcile_unknown_status_cross_check_buy_fill(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """When unknown attempts hit retry limit, live position match infers FILLED."""
    mock_tx_repo.get_pending_transactions.return_value = [
        {
            "id": "tx-unknown-limit",
            "user_id": "user-1",
            "ticker": "MSFT",
            "action": "BUY",
            "quantity": 1.0,
            "price": 420.0,
            "raw_data": {"order_status": "pending", "broker_order_id": "b-ord-2", "unknown_reconcile_count": 4},
            "created_at": datetime.now(),
        }
    ]
    mock_broker.get_order_status.return_value = {"status": "unknown"}

    # Mock live position matching MSFT on broker
    pos = MagicMock()
    pos.symbol = "MSFT"
    pos.quantity = 1.0
    pos.current_price = 425.0
    mock_broker.get_positions.return_value = [pos]

    service = OrderReconciliationService(
        user_id="user-1",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    with patch.object(service, "_get_retry_limit", return_value=5), \
         patch("src.services.outcome_reflection_service.OutcomeReflectionService"), \
         patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        res = await service.reconcile_pending_orders("user-1")

    assert res["summary"]["filled"] == 1
    mock_tx_repo.update_transaction_status.assert_called_once()
    call_kwargs = mock_tx_repo.update_transaction_status.call_args[1]
    assert call_kwargs["new_status"] == "filled"
    assert call_kwargs["entry_category"] == "trade"
    assert call_kwargs["extra_raw"]["reconciled_via"] == "position_cross_check"


@pytest.mark.anyio
async def test_reconcile_unknown_status_exceeds_retry_limit_unresolved(mock_tx_repo, mock_lot_repo, mock_broker, mock_notification_service):
    """When unknown attempts hit retry limit and position check is inconclusive, mark UNRESOLVED and release lock."""
    mock_tx_repo.get_pending_transactions.return_value = [
        {
            "id": "tx-ghost",
            "user_id": "user-1",
            "ticker": "NVDA",
            "action": "BUY",
            "quantity": 5.0,
            "price": 120.0,
            "raw_data": {"order_status": "pending", "broker_order_id": "ghost-999", "unknown_reconcile_count": 5},
            "created_at": datetime.now(),
        }
    ]
    mock_broker.get_order_status.return_value = {"status": "unknown"}
    mock_broker.get_positions.return_value = []  # No NVDA position

    service = OrderReconciliationService(
        user_id="user-1",
        broker=mock_broker,
        tx_repo=mock_tx_repo,
        lot_repo=mock_lot_repo,
        notification_service=mock_notification_service,
    )

    # Pre-lock NVDA
    await service.lock_svc.acquire_lock("NVDA", user_id="user-1", order_id="ghost-999")
    assert await service.lock_svc.is_locked("NVDA", user_id="user-1")

    with patch.object(service, "_get_retry_limit", return_value=5), \
         patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()):
        res = await service.reconcile_pending_orders("user-1")

    assert res["summary"]["unresolved"] == 1
    assert res["summary"]["cancelled"] == 1

    call_kwargs = mock_tx_repo.update_transaction_status.call_args[1]
    assert call_kwargs["new_status"] == "unresolved"
    assert call_kwargs["entry_category"] == "sync_adjustment"

    # In-flight lock MUST be released
    assert not await service.lock_svc.is_locked("NVDA", user_id="user-1")
    mock_notification_service.notify_all.assert_called_once()


# ==============================================================================
# 2. Ticker In-Flight Lock Tests
# ==============================================================================

@pytest.mark.anyio
async def test_inflight_lock_blocks_duplicate_trade(mock_broker, mock_notification_service):
    """When a ticker has an active in-flight lock, new trades on that ticker are blocked."""
    settings_repo = MagicMock()
    settings_repo.get.side_effect = lambda u, k: "true" if k == "ai_trading_enabled" else None

    svc = AutomatedTradingService(
        settings_repo=settings_repo,
        notification_service=mock_notification_service,
    )

    lock_svc = OrderInflightLockService(user_id="user-1")
    await lock_svc.acquire_lock("TSLA", user_id="user-1", order_id="in-flight-1", action="BUY")

    with patch("src.services.trading_protections_service.TradingProtectionsService") as MockProt:
        MockProt.return_value.check.return_value = None
        res = await svc.evaluate_and_execute_trade("user-1", "TSLA", "BUY", quantity=10.0, confidence_score=9)

    assert res["status"] == "blocked"
    assert "in-flight" in res["reason"]


@pytest.mark.anyio
async def test_inflight_lock_released_on_immediate_fill(mock_broker, mock_notification_service):
    """When an order executes immediately (statusID=2 / executed), the in-flight lock is released."""
    settings_repo = MagicMock()
    def get_setting(u, k):
        if k == "ai_trading_enabled": return "true"
        if k == "auto_trade_threshold": return "7.5"
        return None
    settings_repo.get.side_effect = get_setting

    svc = AutomatedTradingService(
        settings_repo=settings_repo,
        notification_service=mock_notification_service,
    )

    mock_broker.execute_order = AsyncMock(return_value={"status": "success", "order_id": "ord-200", "execution_status": "executed"})

    with patch("src.services.automated_trading_service.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.trading_protections_service.TradingProtectionsService") as MockProt, \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        MockProt.return_value.check.return_value = None
        res = await svc.evaluate_and_execute_trade("user-1", "GOOGL", "BUY", quantity=15.0, confidence_score=9)

    assert res["status"] == "success"
    lock_svc = OrderInflightLockService(user_id="user-1")
    assert not await lock_svc.is_locked("GOOGL", user_id="user-1")


# ==============================================================================
# 3. Min Turnover Hurdle Tests
# ==============================================================================

@pytest.mark.anyio
async def test_min_turnover_hurdle_blocks_small_rebalance():
    """Delta weight < min_rebalance_hurdle_pct is skipped as churn noise."""
    settings_repo = MagicMock()
    settings_repo.get.side_effect = lambda u, k: "0.03" if k == "min_rebalance_hurdle_pct" else None

    svc = AutomatedTradingService(settings_repo=settings_repo)

    # 1% delta rebalance on existing position
    res = await svc.evaluate_and_execute_trade(
        user_id="user-1",
        ticker="AAPL",
        action="BUY",
        target_weight=0.15,
        current_weight=0.14,
        delta_weight=0.01,  # 1% < 3%
        portfolio_value=10000.0,
    )

    assert res["status"] == "skipped"
    assert "below min turnover hurdle" in res["reason"]


@pytest.mark.anyio
async def test_min_turnover_hurdle_allows_significant_rebalance(mock_broker):
    """Delta weight >= min_rebalance_hurdle_pct is allowed to evaluate."""
    settings_repo = MagicMock()
    def get_setting(u, k):
        if k == "min_rebalance_hurdle_pct": return "0.03"
        if k == "ai_trading_enabled": return "true"
        if k == "auto_trade_threshold": return "7.5"
        return None
    settings_repo.get.side_effect = get_setting

    svc = AutomatedTradingService(settings_repo=settings_repo)

    with patch("src.services.automated_trading_service.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.trading_protections_service.TradingProtectionsService") as MockProt, \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        MockProt.return_value.check.return_value = None
        # 5% delta rebalance
        res = await svc.evaluate_and_execute_trade(
            user_id="user-1",
            ticker="AAPL",
            action="BUY",
            target_weight=0.15,
            current_weight=0.10,
            delta_weight=0.05,  # 5% >= 3%
            portfolio_value=10000.0,
            confidence_score=9,
        )

    assert res["status"] == "success"


@pytest.mark.anyio
async def test_min_turnover_hurdle_exemptions():
    """Liquidation (target_weight=0) and safety exits bypass hurdle."""
    settings_repo = MagicMock()
    settings_repo.get.side_effect = lambda u, k: "0.05" if k == "min_rebalance_hurdle_pct" else None

    svc = AutomatedTradingService(settings_repo=settings_repo)

    # Full liquidation with delta_weight -0.01
    with patch("src.services.trading_protections_service.TradingProtectionsService") as MockProt, \
         patch.object(svc, "_request_approval_and_execute", new=AsyncMock(return_value={"status": "approved"})):
        MockProt.return_value.check.return_value = None
        res = await svc.evaluate_and_execute_trade(
            user_id="user-1",
            ticker="INTC",
            action="SELL",
            target_weight=0.0,
            current_weight=0.01,
            delta_weight=-0.01,
            portfolio_value=10000.0,
            confidence_score=8,
        )

    assert res["status"] != "skipped"


# ==============================================================================
# 4. Intraday Churn Throttler Tests
# ==============================================================================

@pytest.mark.anyio
async def test_intraday_churn_throttler_blocks_reverse_trade():
    """Opposite direction trade within 24h is blocked by churn throttler."""
    settings_repo = MagicMock()
    def get_setting(u, k):
        if k == "intraday_churn_cooldown_hours": return "24.0"
        if k == "ai_trading_enabled": return "true"
        return None
    settings_repo.get.side_effect = get_setting

    tx_repo = MagicMock()
    # Mock previous trade 3 hours ago: BUY META
    recent_tx = MagicMock()
    recent_tx.ticker = "META"
    recent_tx.action = "BUY"
    recent_tx.entry_category = "trade"
    recent_tx.trade_date = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    tx_repo.get_all_by_user.return_value = [recent_tx]

    svc = AutomatedTradingService(settings_repo=settings_repo, tx_repo=tx_repo)

    with patch("src.services.trading_protections_service.TradingProtectionsService") as MockProt:
        MockProt.return_value.check.return_value = None
        # Propose SELL META 3h after BUY META
        res = await svc.evaluate_and_execute_trade(
            user_id="user-1",
            ticker="META",
            action="SELL",
            quantity=1.0,
            confidence_score=8,
        )

    assert res["status"] == "blocked"
    assert "Intraday churn throttler" in res["reason"]


@pytest.mark.anyio
async def test_intraday_churn_throttler_allows_same_direction(mock_broker):
    """Same direction trade (BUY after BUY) is not blocked by flip-flop churn throttler."""
    settings_repo = MagicMock()
    def get_setting(u, k):
        if k == "intraday_churn_cooldown_hours": return "24.0"
        if k == "ai_trading_enabled": return "true"
        if k == "auto_trade_threshold": return "7.5"
        return None
    settings_repo.get.side_effect = get_setting

    tx_repo = MagicMock()
    # Mock previous trade 3 hours ago: BUY META
    recent_tx = MagicMock()
    recent_tx.ticker = "META"
    recent_tx.action = "BUY"
    recent_tx.entry_category = "trade"
    recent_tx.trade_date = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    tx_repo.get_all_by_user.return_value = [recent_tx]

    svc = AutomatedTradingService(settings_repo=settings_repo, tx_repo=tx_repo)

    with patch("src.services.automated_trading_service.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.trading_protections_service.TradingProtectionsService") as MockProt, \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        MockProt.return_value.check.return_value = None
        # Propose another BUY META
        res = await svc.evaluate_and_execute_trade(
            user_id="user-1",
            ticker="META",
            action="BUY",
            quantity=100.0,
            confidence_score=9,
        )

    assert res["status"] == "success"
