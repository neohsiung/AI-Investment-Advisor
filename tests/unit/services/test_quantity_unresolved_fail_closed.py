"""
WP5c-a: the executor must FAIL CLOSED when it cannot resolve an order quantity.
Previously three silent fallbacks set `quantity = 1.0` ("sell 1 share" / "$1 buy").
WP5c-a：無法解析下單數量時執行器必須 fail-closed，不得再退回 quantity = 1.0。
"""
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.services.automated_trading_service import AutomatedTradingService

MOD = "src.services.automated_trading_service"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def allow_trading_protections():
    with patch("src.services.trading_protections_service.TradingProtectionsService") as m:
        m.return_value.check.return_value = None
        yield m


@pytest.fixture
def svc():
    repo = MagicMock()
    repo.get.side_effect = lambda u, k: {
        "ai_trading_enabled": "true", "auto_trade_threshold": "9", "auto_trade_min_threshold": "3",
    }.get(k)
    inter = AsyncMock()
    inter.request_approval.return_value = (True, "APPROVED")
    notif = AsyncMock()
    notif.notify_all.return_value = {}
    return AutomatedTradingService(settings_repo=repo, interaction_service=inter, notification_service=notif)


@pytest.fixture
def broker():
    b = MagicMock()
    b.get_name.return_value = "MockBroker"
    b.execute_order = AsyncMock(return_value={"status": "success", "order_id": "1"})
    pos = MagicMock()
    pos.symbol = "TSLA"
    pos.quantity = 5.0
    b.get_positions = AsyncMock(return_value=[pos])
    acct = MagicMock()
    acct.total_equity = 1000.0
    acct.available_cash = 500.0
    b.get_account = AsyncMock(return_value=acct)
    b.sync_history = AsyncMock(return_value=True)
    return b


def _assert_closed(res, cause, ticker, action, broker, notify, log):
    assert res["status"] == "error"
    assert res["reason"] == "quantity_unresolved"
    assert res["cause"] == cause
    assert res["ticker"] == ticker
    assert res["action"] == action
    broker.execute_order.assert_not_called()
    notify.assert_not_called()
    # logged at WARNING or above, naming the reason / 至少 WARNING 層級
    msgs = [c.args[0] for c in log.warning.call_args_list + log.error.call_args_list]
    assert any("quantity_unresolved" in m for m in msgs)


@pytest.mark.anyio
async def test_sell_price_unavailable_fails_closed(svc, broker):
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=broker), \
         patch(f"{MOD}.logger") as log, \
         patch.object(svc, "_get_current_price", new_callable=AsyncMock, return_value=None), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock) as notify:
        res = await svc.evaluate_and_execute_trade(
            "u", "TSLA", "SELL", delta_weight=-0.04, portfolio_value=1000.0,
            confidence_score=9, rationale="r")
    _assert_closed(res, "price_unavailable", "TSLA", "SELL", broker, notify, log)


@pytest.mark.anyio
async def test_weight_calc_exception_fails_closed(svc, broker):
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=broker), \
         patch(f"{MOD}.logger") as log, \
         patch.object(svc, "_get_current_price", new_callable=AsyncMock, side_effect=RuntimeError("boom")), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock) as notify:
        res = await svc.evaluate_and_execute_trade(
            "u", "TSLA", "SELL", delta_weight=-0.04, portfolio_value=1000.0,
            confidence_score=9, rationale="r")
    _assert_closed(res, "weight_calc_failed", "TSLA", "SELL", broker, notify, log)


@pytest.mark.anyio
async def test_buy_weight_calc_exception_fails_closed(svc):
    with patch(f"{MOD}.BrokerFactory.get_broker", side_effect=RuntimeError("no broker")), \
         patch(f"{MOD}.logger") as log, \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock) as notify:
        res = await svc.evaluate_and_execute_trade(
            "u", "AAPL", "BUY", delta_weight=0.02, portfolio_value=1000.0,
            confidence_score=9, rationale="r")
    assert res["status"] == "error" and res["reason"] == "quantity_unresolved"
    assert res["cause"] == "weight_calc_failed"
    notify.assert_not_called()


@pytest.mark.anyio
async def test_no_quantity_no_weights_fails_closed(svc, broker):
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=broker), \
         patch(f"{MOD}.logger") as log, \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock) as notify:
        res = await svc.evaluate_and_execute_trade("u", "AAPL", "BUY", confidence_score=9, rationale="r")
    _assert_closed(res, "quantity_missing", "AAPL", "BUY", broker, notify, log)


@pytest.mark.anyio
async def test_no_broker_with_weights_fails_closed(svc):
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=None), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock) as notify:
        res = await svc.evaluate_and_execute_trade(
            "u", "AAPL", "BUY", delta_weight=0.02, portfolio_value=1000.0, confidence_score=9, rationale="r")
    assert res["status"] == "error" and res["cause"] == "quantity_missing"
    notify.assert_not_called()


@pytest.mark.anyio
async def test_explicit_positive_quantity_unchanged(svc, broker):
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=broker), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        res = await svc.evaluate_and_execute_trade("u", "TSLA", "SELL", 2.0, 9, "r")
    assert res["status"] == "success"
    order = broker.execute_order.call_args[0][0]
    assert order.quantity == 2.0 and order.action.value == "SELL"


@pytest.mark.anyio
async def test_buy_delta_weight_unchanged(svc, broker):
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=broker), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        res = await svc.evaluate_and_execute_trade(
            "u", "AAPL", "BUY", delta_weight=0.02, portfolio_value=1000.0, confidence_score=9, rationale="r")
    assert res["status"] == "success"
    order = broker.execute_order.call_args[0][0]
    assert order.amount_usd >= 10.0
    assert order.action.value == "BUY"


@pytest.mark.anyio
async def test_sell_delta_weight_with_price_unchanged(svc, broker):
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=broker), \
         patch.object(svc, "_get_current_price", new_callable=AsyncMock, return_value=200.0), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        res = await svc.evaluate_and_execute_trade(
            "u", "TSLA", "SELL", delta_weight=-0.04, portfolio_value=1000.0, confidence_score=9, rationale="r")
    assert res["status"] == "success"
    assert broker.execute_order.call_args[0][0].quantity == 0.2


# ── Fractional-unit safety (eToro trades fractional units; no whole-share assumption) ──
# 碎股安全：不得引入任何取整到整股的邏輯。

def _frac_broker(symbol, held):
    b = MagicMock()
    b.get_name.return_value = "MockBroker"
    b.execute_order = AsyncMock(return_value={"status": "success", "order_id": "f"})
    pos = MagicMock()
    pos.symbol = symbol
    pos.quantity = held
    b.get_positions = AsyncMock(return_value=[pos])
    acct = MagicMock()
    acct.total_equity = 100000.0
    acct.available_cash = 50000.0
    b.get_account = AsyncMock(return_value=acct)
    b.sync_history = AsyncMock(return_value=True)
    return b


@pytest.mark.anyio
@pytest.mark.parametrize("qty", [0.18519, 0.0123, 0.29076])
async def test_explicit_fractional_sell_reaches_broker_unchanged(svc, qty):
    b = _frac_broker("TSLA", 0.5)
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=b), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        res = await svc.evaluate_and_execute_trade("u", "TSLA", "SELL", qty, 9, "r")
    assert res["status"] == "success"
    order = b.execute_order.call_args[0][0]
    assert order.action.value == "SELL"
    assert order.quantity == pytest.approx(qty, abs=0.0101)  # pre-existing 2dp floor (~L881) only
    assert 0 < order.quantity < 1.0


@pytest.mark.anyio
@pytest.mark.parametrize("price", [0.5, 200.0, 1000.0])
async def test_weight_sell_is_fractional_as_before(svc, price):
    b = _frac_broker("TSLA", 100.0)
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=b), \
         patch.object(svc, "_get_current_price", new_callable=AsyncMock, return_value=price), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        res = await svc.evaluate_and_execute_trade(
            "u", "TSLA", "SELL", delta_weight=-0.04, portfolio_value=1000.0, confidence_score=9, rationale="r")
    assert res["status"] == "success"
    order = b.execute_order.call_args[0][0]
    assert order.quantity == pytest.approx(40.0 / price, abs=0.005 + 1e-9)


@pytest.mark.anyio
@pytest.mark.parametrize("amount", [100.0, 12.34])
async def test_buy_usd_amount_untouched(svc, amount):
    b = _frac_broker("AAPL", 0.0)
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=b), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        res = await svc.evaluate_and_execute_trade("u", "AAPL", "BUY", amount, 9, "r")
    assert res["status"] == "success"
    order = b.execute_order.call_args[0][0]
    assert order.amount_usd <= amount + 1e-9  # only ever clamped down by pre-existing caps


@pytest.mark.anyio
@pytest.mark.parametrize("price", [0.5, 200.0, 65000.0])
@pytest.mark.parametrize("action", ["BUY", "SELL"])
async def test_quantity_none_fails_closed_regardless_of_price(svc, price, action):
    b = _frac_broker("TSLA", 0.29)
    with patch(f"{MOD}.BrokerFactory.get_broker", return_value=b), \
         patch.object(svc, "_get_current_price", new_callable=AsyncMock, return_value=price), \
         patch.object(svc, "_notify_via_api", new_callable=AsyncMock):
        res = await svc.evaluate_and_execute_trade("u", "TSLA", action, None, 9, "r")
    assert res["status"] == "error" and res["reason"] == "quantity_unresolved"
    b.execute_order.assert_not_called()
