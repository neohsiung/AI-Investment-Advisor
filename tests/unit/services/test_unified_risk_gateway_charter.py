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
    assert res.reasons == ["[Charter] charter frozen: watchdog breach ['K1']"]
    assert res.guard_details["charter_halt"]["passed"] is False


async def test_sell_is_not_affected():
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK) as gate:
        res = await _eval("SELL", "momentum")
    assert res.primary_blocker != "CharterHalt" and "charter_halt" not in res.guard_details
    gate.assert_not_called()


async def test_safety_control_buy_skips_the_charter_gate():
    with patch("src.services.charter_state_service.trading_allowed", return_value=BLOCK) as gate:
        res = await _eval("BUY", "benchmark_parking")
    assert res.primary_blocker != "CharterHalt"
    gate.assert_not_called()


async def test_unreadable_state_blocks_nonsafety_buy():
    with patch("src.services.charter_state_service.get_db_engine", side_effect=RuntimeError("no db")):
        res = await _eval("BUY")
    assert res.allowed is False and res.primary_blocker == "CharterHalt" and "unreadable" in res.reasons[0]
