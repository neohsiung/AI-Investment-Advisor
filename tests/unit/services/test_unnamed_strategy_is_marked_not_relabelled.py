"""A missing strategy name is recorded as missing, never relabelled as a strategy (plan P6, section 1.3).

Write side: ``transactions.raw_data.strategy_name`` and the in-flight lock payload hold None when no name was given.
Read side: the learning ledger (``decision_outcomes.agent_name`` is NOT NULL) gets the explicit marker
``UNNAMED_LEDGER_LABEL`` plus a warning, so the sample is kept and the gap is visible.
Sentinel: an exit trigger without a name is still sent (a sell must not be dropped) with strategy_name=None and an error log.
缺策略名就如實記為缺，不補成某個策略；學習帳本讀取端改用明確標記並警告；Sentinel 缺名賣單照送並記 error。
"""
import ast
import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain import strategy_names as sn
from src.services.order_inflight_lock_service import OrderInflightLockService, _LOCAL_LOCKS
from src.services.order_reconciliation_service import OrderReconciliationService, _RECON_LOCAL_LOCKS

ROOT = Path(__file__).resolve().parents[3]
LEDGER_FILES = (
    "src/services/automated_trading_service.py",
    "src/services/order_reconciliation_service.py",
    "src/services/order_inflight_lock_service.py",
)


@pytest.fixture(autouse=True)
def _clean():
    _LOCAL_LOCKS.clear()
    _RECON_LOCAL_LOCKS.clear()
    yield
    _LOCAL_LOCKS.clear()
    _RECON_LOCAL_LOCKS.clear()


def test_missing_strategy_name_is_not_relabelled_in_ledger_modules():
    """No ledger module may carry the old default label as a string literal (the marker lives in the domain)."""
    for rel in LEDGER_FILES:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and n.value == sn.UNNAMED_LEDGER_LABEL]
        assert not hits, f"{rel} still hard-codes {sn.UNNAMED_LEDGER_LABEL!r} at lines {hits}"


@pytest.mark.asyncio
async def test_missing_strategy_name_is_not_relabelled_in_lock_payload():
    with patch("src.infrastructure.cache.redis_client.get_redis", side_effect=Exception("Redis down")):
        svc = OrderInflightLockService(user_id="user_123")
        assert await svc.acquire_lock("TSM", order_id="o1", action="BUY") is True
        info = await svc.get_lock_info("TSM")
    assert info["strategy_name"] is None


@pytest.mark.asyncio
async def test_missing_strategy_name_is_not_relabelled_in_transaction_row():
    from src.domain.trading import Order, OrderAction, OrderType
    from src.services.automated_trading_service import AutomatedTradingService

    svc = AutomatedTradingService.__new__(AutomatedTradingService)
    broker = MagicMock()
    broker.get_name.return_value = "eToro"
    order = Order(symbol="AAPL", action=OrderAction.SELL, quantity=1.0, price=10.0, order_type=OrderType.MARKET)
    repo = MagicMock()
    with patch("src.repositories.transaction_repository.AlchemyTransactionRepository", return_value=repo):
        await svc._record_order_transaction(
            user_id="u", order=order, result={"order_id": "b1"}, broker=broker, execution_status="pending",
            confidence_score=8, rationale="r", approval_type="auto", strategy_name=None)
    raw = repo.add.call_args.kwargs["raw_data"]
    assert "strategy_name" in raw and raw["strategy_name"] is None


def _recon(raw_data):
    tx_repo = MagicMock()
    tx_repo.get_pending_transactions.return_value = [{
        "id": "tx-1", "user_id": "u", "ticker": "AAPL", "trade_date": "2026-09-25", "action": "BUY",
        "quantity": 2.0, "price": 150.0, "fees": 0.0, "amount": 300.0, "leverage": 1.0, "source_file": "eToro",
        "entry_category": "sync_adjustment", "raw_data": raw_data, "created_at": datetime.now() - timedelta(hours=2),
    }]
    broker = MagicMock()
    broker.get_name.return_value = "eToro"
    broker.get_order_status = AsyncMock(return_value={
        "order_id": "b-1", "status": "filled", "fill_price": 152.5, "quantity": 2.0, "fees": 0.0,
        "executed_at": "2026-09-25T14:30:00Z", "raw": {}})
    broker.get_positions = AsyncMock(return_value=[])
    broker.sync_history = AsyncMock(return_value={})
    notif = AsyncMock()
    notif.notify_all.return_value = {}
    return OrderReconciliationService(user_id="u", broker=broker, tx_repo=tx_repo, lot_repo=MagicMock(),
                                      notification_service=notif)


@pytest.mark.asyncio
async def test_unnamed_outcome_is_recorded_not_dropped(caplog):
    svc = _recon({"order_status": "pending", "broker_order_id": "b-1", "strategy_name": None})
    with patch("src.services.outcome_reflection_service.OutcomeReflectionService") as Outcome, \
         patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()), \
         patch("src.services.order_reconciliation_service.logger") as log:
        Outcome.return_value.record_decision.return_value = "dec-1"
        result = await svc.reconcile_pending_orders("u")
    assert result["summary"]["filled"] == 1
    Outcome.return_value.record_decision.assert_called_once()
    assert Outcome.return_value.record_decision.call_args.kwargs["agent_name"] == sn.UNNAMED_LEDGER_LABEL
    assert any("strategy" in str(c.args[0]).lower() for c in log.warning.call_args_list), "gap must be warned"


@pytest.mark.asyncio
async def test_named_outcome_keeps_its_name_and_does_not_warn():
    svc = _recon({"order_status": "pending", "broker_order_id": "b-1", "strategy_name": "stop_loss"})
    with patch("src.services.outcome_reflection_service.OutcomeReflectionService") as Outcome, \
         patch("src.services.analytics_service.update_daily_snapshot", new=AsyncMock()), \
         patch("src.services.order_reconciliation_service.logger") as log:
        Outcome.return_value.record_decision.return_value = "dec-1"
        await svc.reconcile_pending_orders("u")
    assert Outcome.return_value.record_decision.call_args.kwargs["agent_name"] == "stop_loss"
    assert not any("unnamed" in str(c.args[0]).lower() for c in log.warning.call_args_list)


@pytest.mark.asyncio
async def test_nameless_exit_trigger_is_still_sent_with_none_and_logged():
    from src.services.sentinel_service import SentinelService
    s = SentinelService.__new__(SentinelService)
    s.user_id = "u"
    s._acquire_cooldown = AsyncMock(return_value=True)
    s._clear_position_peak_and_stop = AsyncMock()
    auto = MagicMock()
    auto.evaluate_and_execute_trade = AsyncMock(return_value={"status": "executed"})
    trigger = {"action": "trigger_exit", "ticker": "AAPL", "sell_quantity": 2.0, "current_price": 10.0,
               "composite_score": 7.0, "rationale": "x"}
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=auto), \
         patch("src.services.sentinel_service.logger") as log:
        await s._handle_position_exits([trigger])
    auto.evaluate_and_execute_trade.assert_called_once()
    assert auto.evaluate_and_execute_trade.call_args.kwargs["strategy_name"] is None
    log.error.assert_called()


def test_every_trigger_exit_dict_in_sentinel_names_its_strategy():
    """Guard (green today): every ``{"action": "trigger_exit", ...}` literal carries a strategy_name key."""
    tree = ast.parse((ROOT / "src/services/sentinel_service.py").read_text(encoding="utf-8"))
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            pairs = {k.value: v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant)}
            a = pairs.get("action")
            if isinstance(a, ast.Constant) and a.value == "trigger_exit" and "strategy_name" not in pairs:
                bad.append(n.lineno)
    assert not bad, f"trigger_exit dicts without strategy_name at lines {bad}"
