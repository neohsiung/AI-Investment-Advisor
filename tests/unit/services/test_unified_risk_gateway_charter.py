"""G7: the charter halt inside UnifiedRiskGatewayService.evaluate_trade_risk. / 章程停機接進風控閘門。"""
from unittest.mock import patch

import pytest

from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService

pytestmark = [pytest.mark.real_charter_gate, pytest.mark.asyncio]
BLOCK = (False, "charter frozen: watchdog breach ['K1']")


async def _eval(action, strategy="batch_cash_deployment"):
    return await UnifiedRiskGatewayService(user_id="u").evaluate_trade_risk(
        ticker="NVDA", action=action, amount_usd=100.0, current_price=100.0, strategy_name=strategy,
        confidence_score=9.0)


async def test_frozen_blocks_nonsafety_buy_with_charter_halt():
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK):
        res = await _eval("BUY")
    assert res.allowed is False and res.primary_blocker == "CharterHalt"
    assert len(res.reasons) == 1 and res.reasons[0].startswith("[Charter] charter frozen: watchdog breach ['K1']")
    assert "not on the frozen exit whitelist" in res.reasons[0]
    assert res.guard_details["charter_halt"]["passed"] is False


async def test_frozen_blocks_a_non_whitelisted_sell_with_charter_halt():
    """ADR-005: the gateway now runs the charter gate for SELL too (it used to be BUY only)."""
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK):
        res = await _eval("SELL", "rebalance_diversification")
    assert res.allowed is False and res.primary_blocker == "CharterHalt"
    assert res.guard_details["charter_halt"]["passed"] is False


async def test_frozen_blocks_an_unnamed_sell():
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK):
        res = await _eval("SELL", None)
    assert res.allowed is False and res.primary_blocker == "CharterHalt"


@pytest.mark.parametrize("action", ["BUY", "SELL"])
async def test_whitelisted_exit_skips_the_charter_gate(action):
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK) as gate:
        res = await _eval(action, "stop_loss")
    assert res.primary_blocker != "CharterHalt"
    gate.assert_not_called()


async def test_whitelisted_hedge_buy_skips_the_charter_gate():
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK) as gate:
        res = await _eval("BUY", "emergency_hedge")
    assert res.primary_blocker != "CharterHalt"
    gate.assert_not_called()


async def test_benchmark_parking_buy_is_blocked_while_frozen():
    """Decision 2026-10-30: benchmark_parking may not buy during a freeze."""
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK):
        res = await _eval("BUY", "benchmark_parking")
    assert res.allowed is False and res.primary_blocker == "CharterHalt"


async def test_unreadable_state_marks_an_allowed_sell_in_guard_details():
    with patch("src.services.charter_state_service.trading_allowed",
               return_value=(False, "charter_state unreadable: OperationalError")):
        res = await _eval("SELL", "rebalance_diversification")
    assert res.primary_blocker != "CharterHalt"
    assert res.guard_details["charter_halt"]["passed"] is True
    assert res.guard_details["charter_halt"]["marker"] == "charter_unreadable_sell_allowed"


async def test_unreadable_state_blocks_nonsafety_buy():
    with patch("src.services.charter_state_service.get_db_engine", side_effect=RuntimeError("no db")):
        res = await _eval("BUY")
    assert res.allowed is False and res.primary_blocker == "CharterHalt" and "unreadable" in res.reasons[0]
