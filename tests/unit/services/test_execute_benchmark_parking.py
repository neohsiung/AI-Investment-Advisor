"""The executor's benchmark-parking entry point: kill switch, risk gateway, fail-closed, single order path."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.automated_trading_service import AutomatedTradingService


def _svc(enabled="true"):
    svc = AutomatedTradingService.__new__(AutomatedTradingService)
    svc.settings_repo = MagicMock()
    svc.settings_repo.get.side_effect = lambda uid, key: {"ai_trading_enabled": enabled}.get(key)
    svc._execute_trade = AsyncMock(return_value={"status": "success", "order_id": "o1"})
    return svc


def _gateway(allowed=True, reasons=None, raises=None):
    gw = MagicMock()
    if raises:
        gw.evaluate_trade_risk = AsyncMock(side_effect=raises)
    else:
        gw.evaluate_trade_risk = AsyncMock(return_value=MagicMock(allowed=allowed, reasons=reasons or []))
    return gw


@pytest.mark.asyncio
async def test_blocked_when_trading_disabled():
    svc = _svc(enabled="false")
    res = await svc.execute_benchmark_parking("u", 100.0, "x")
    assert res["status"] == "blocked"
    svc._execute_trade.assert_not_called()


@pytest.mark.asyncio
async def test_below_minimum_is_skipped():
    svc = _svc()
    assert (await svc.execute_benchmark_parking("u", 5.0, "x"))["status"] == "skipped"
    svc._execute_trade.assert_not_called()


@pytest.mark.asyncio
async def test_risk_gateway_error_fails_closed():
    svc = _svc()
    with patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService", return_value=_gateway(raises=RuntimeError("boom"))):
        res = await svc.execute_benchmark_parking("u", 100.0, "x")
    assert res["status"] == "blocked" and "boom" in res["reason"]
    svc._execute_trade.assert_not_called()


@pytest.mark.asyncio
async def test_risk_gateway_block_is_respected():
    svc = _svc()
    with patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService", return_value=_gateway(allowed=False, reasons=["calendar blackout"])):
        res = await svc.execute_benchmark_parking("u", 100.0, "x")
    assert res["status"] == "blocked" and "calendar blackout" in res["reason"]


@pytest.mark.asyncio
async def test_success_places_one_market_buy_of_the_benchmark():
    svc = _svc()
    with patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService", return_value=_gateway()):
        res = await svc.execute_benchmark_parking("u", 123.456, "park")
    assert res["status"] == "success"
    order = svc._execute_trade.await_args.args[1]
    assert order.symbol == "SPY" and order.action.value == "BUY" and order.amount_usd == pytest.approx(123.456)
    assert order.strategy_name == "benchmark_parking"
