"""
Benchmark parking: sizing is pure, buys only, respects the tradable cap and the active sleeve's cash; the
benchmark core is invisible to discretionary exits.
基準停泊：純計算、只買不賣、遵守可交易資本與主動部位現金；基準核心不被自由裁量出場邏輯觸碰。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.benchmark_parking_service import BenchmarkParkingService, plan_parking
from src.services.core_holdings import is_core


def _plan(**kw):
    base = dict(nlv=1661.37, cash=1661.37, tradable=1246.03, benchmark_value=0.0, other_positions_value=0.0,
                benchmark_weight_pct=70.0, max_order_usd=250.0, min_gap_usd=50.0)
    base.update(kw)
    return plan_parking(**base)


def test_all_cash_ramps_in_with_the_per_run_cap():
    p = _plan()
    assert p["action"] == "BUY" and p["amount_usd"] == 250.0
    assert p["target_value"] == pytest.approx(872.22, abs=0.01)


def test_never_exceeds_target_or_usable_cash():
    # target 872.22, already hold 800 -> gap 72.22 > band 50 -> buys 72.22 only
    p = _plan(benchmark_value=800.0)
    assert p["action"] == "BUY" and p["amount_usd"] == pytest.approx(72.22, abs=0.01)


def test_inside_band_holds():
    assert _plan(benchmark_value=840.0)["action"] == "HOLD"          # gap 32 < band 50
    assert _plan(benchmark_value=872.0)["action"] == "HOLD"
    assert _plan(benchmark_value=2000.0)["action"] == "HOLD"          # above target -> never sells


def test_active_sleeve_cash_and_untouchable_cash_are_reserved():
    # untouchable = nlv - tradable = 415.34; active budget = 30% of 1246.03 = 373.81 reserved
    p = _plan(cash=900.0)
    assert p["usable_cash"] == pytest.approx(900.0 - 415.34 - 373.81, abs=0.02)
    # active positions already fund part of the sleeve -> less reserve
    p2 = _plan(cash=900.0, other_positions_value=200.0)
    assert p2["usable_cash"] > p["usable_cash"]


def test_below_broker_minimum_holds():
    p = _plan(cash=790.0)                                              # usable ~$0.85
    assert p["action"] == "HOLD" and "minimum" in p["reason"]


def test_no_capital_holds():
    assert _plan(tradable=0.0)["action"] == "HOLD"
    assert _plan(nlv=0.0)["action"] == "HOLD"


def test_core_symbol_matching():
    assert is_core("SPY") and is_core("spy.US") and not is_core("AAPL")


def _svc(enabled, plan_account=(1661.37, 1661.37), spy_value=0.0, executor=None):
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, d=None: {"benchmark_parking_enabled": enabled}.get(k, d)
    broker = MagicMock()
    acc = MagicMock(total_equity=plan_account[0], available_cash=plan_account[1])
    broker.get_account = AsyncMock(return_value=acc)
    pos = []
    if spy_value:
        pos.append(MagicMock(symbol="SPY", market_value=spy_value))
    broker.get_positions = AsyncMock(return_value=pos)
    return BenchmarkParkingService("u", settings_service=settings, broker=broker, executor=executor)


@pytest.mark.asyncio
async def test_disabled_is_a_dry_run_and_never_calls_the_executor(monkeypatch):
    monkeypatch.setattr("src.services.capital_policy.tradable_capital", lambda uid, nlv, settings_repo=None: 1246.03)
    ex = MagicMock(); ex.execute_benchmark_parking = AsyncMock()
    res = await _svc(False, executor=ex).run()
    assert res["action"] == "BUY" and res["executed"] is False and "dry run" in res["reason"]
    ex.execute_benchmark_parking.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_executes_through_the_single_executor(monkeypatch):
    monkeypatch.setattr("src.services.capital_policy.tradable_capital", lambda uid, nlv, settings_repo=None: 1246.03)
    ex = MagicMock(); ex.execute_benchmark_parking = AsyncMock(return_value={"status": "success", "order_id": "o1"})
    res = await _svc(True, executor=ex).run()
    assert res["executed"] is True
    ex.execute_benchmark_parking.assert_awaited_once()
    assert ex.execute_benchmark_parking.await_args.args[1] == 250.0


@pytest.mark.asyncio
async def test_blocked_execution_is_reported_not_hidden(monkeypatch):
    monkeypatch.setattr("src.services.capital_policy.tradable_capital", lambda uid, nlv, settings_repo=None: 1246.03)
    ex = MagicMock(); ex.execute_benchmark_parking = AsyncMock(return_value={"status": "blocked", "reason": "risk gateway"})
    res = await _svc(True, executor=ex).run()
    assert res["executed"] is False and res["execution"]["reason"] == "risk gateway"
