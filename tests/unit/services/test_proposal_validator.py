"""WP4: pure proposal validator. / 純函式提案驗證器（未接線）。"""
import ast
import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config.mission import load_mission
from src.services import proposal_validator as pv
from src.services.proposal_validator import ValidationContext, ValidationResult, validate
from src.services.strategy_registry import StrategyRegistry

SRC = Path(pv.__file__)
SAFETY = frozenset({"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit", "macro_volatility_hedge"})


def _gw_ok(*a, **k):
    return SimpleNamespace(allowed=True, reasons=[], guard_details={})


def _ctx(**over):
    base = dict(
        tradable_capital_usd=1000.0, usable_cash_usd=500.0, mission=load_mission(),
        held_positions={"AAPL": 3.0}, paired_buys=[],
        research_lookup=lambda t: (7.0, 1.0), max_research_age_days=3.0,
        gateway_check=_gw_ok, benchmark_parking_available=True,
        per_order_cap_usd=80.0, min_order_usd=10.0, safety_exit_names=SAFETY,
        position_values_usd={"AAPL": 300.0},
    )
    base.update(over)
    return ValidationContext(**base)


def _p(**over):
    p = {"ticker": "MSFT", "direction": "BUY", "source": "event", "rationale": "x"}
    p.update(over)
    return p


def test_buy_approved_numeric():
    r = validate(_p(), _ctx())
    assert r.approved and r.reason == "approved"
    assert isinstance(r.amount_usd, float) and isinstance(r.score, float)
    assert r.strategy_name == "proposal_event"
    pct = load_mission().promotion.max_initial_live_weight_pct
    assert r.amount_usd == pytest.approx(min(1000.0 * pct / 100.0, 80.0, 500.0))


def test_buy_limited_by_cash():
    r = validate(_p(), _ctx(usable_cash_usd=25.0, per_order_cap_usd=1e9))
    assert r.approved and r.amount_usd == pytest.approx(25.0)


def test_result_frozen():
    r = validate(_p(), _ctx())
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.approved = False  # type: ignore[misc]


@pytest.mark.parametrize("over,reason", [
    ({"direction": "HOLD"}, "invalid_direction"),
    ({"direction": None}, "invalid_direction"),
    ({"ticker": ""}, "invalid_ticker"),
    ({"ticker": "  "}, "invalid_ticker"),
    ({"ticker": None}, "invalid_ticker"),
    ({"ticker": "CASH"}, "reserved_symbol"),
    ({"ticker": "usd"}, "reserved_symbol"),
    ({"ticker": "GLOBAL"}, "reserved_symbol"),
    ({"ticker": "MARKET"}, "reserved_symbol"),
    ({"source": "llm"}, "invalid_source"),
    ({"source": None}, "invalid_source"),
])
def test_schema_rejects(over, reason):
    r = validate(_p(**over), _ctx())
    assert not r.approved and r.reason == reason
    assert r.amount_usd is None and r.score is None


def test_non_dict_proposal():
    assert validate("BUY", _ctx()).reason == "invalid_proposal"  # type: ignore[arg-type]


@pytest.mark.parametrize("key", ["quantity", "qty", "score", "confidence", "amount", "amount_usd", "size", "weight"])
def test_llm_supplied_size_rejected(key):
    r = validate(_p(**{key: 5}), _ctx())
    assert not r.approved and r.reason == "llm_supplied_size"


def test_llm_supplied_size_nested_and_case():
    assert validate(_p(llm={"Confidence": 9}), _ctx()).reason == "llm_supplied_size"


@pytest.mark.parametrize("cap", [0.0, -5.0, None, float("nan")])
def test_capital_disabled(cap):
    r = validate(_p(), _ctx(tradable_capital_usd=cap))
    assert not r.approved and r.reason == "capital_disabled"


def test_missing_score():
    assert validate(_p(), _ctx(research_lookup=lambda t: None)).reason == "missing_score"


def test_lookup_raises_is_missing_score():
    def boom(t):
        raise RuntimeError("db down")
    assert validate(_p(), _ctx(research_lookup=boom)).reason == "missing_score"


def test_stale_score():
    assert validate(_p(), _ctx(research_lookup=lambda t: (7.0, 4.0))).reason == "stale_score"


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -0.1, 10.1, "7", True])
def test_invalid_score(bad):
    assert validate(_p(), _ctx(research_lookup=lambda t: (bad, 1.0))).reason == "invalid_score"


def test_invalid_age_is_stale():
    assert validate(_p(), _ctx(research_lookup=lambda t: (7.0, float("nan")))).reason == "stale_score"


def test_never_approved_with_score_none():
    for lk in (lambda t: None, lambda t: (None, 0.0)):
        assert not validate(_p(), _ctx(research_lookup=lk)).approved
    with pytest.raises(ValueError):
        ValidationResult(True, "approved", 10.0, "proposal_event", None)
    with pytest.raises(ValueError):
        ValidationResult(True, "approved", None, "proposal_event", 5.0)


def test_sell_not_held():
    assert validate(_p(direction="SELL", ticker="NVDA"), _ctx()).reason == "not_held"


def test_sell_with_paired_buy_approved():
    buys = [{"ticker": "MSFT", "delta_amount": 500.0, "delta_weight": 1.0}]
    r = validate(_p(direction="SELL", ticker="AAPL"), _ctx(paired_buys=buys))
    assert r.approved and isinstance(r.amount_usd, float) and r.score == 7.0
    assert r.planned_buys == ()


def test_sell_without_pair_auto_plans_benchmark():
    r = validate(_p(direction="SELL", ticker="AAPL"), _ctx())
    assert r.approved
    assert len(r.planned_buys) == 1
    b = r.planned_buys[0]
    assert b["ticker"] == load_mission().objective.benchmark
    assert b["delta_amount"] == pytest.approx(r.amount_usd)


def test_sell_without_pair_no_parking_rejected():
    r = validate(_p(direction="SELL", ticker="AAPL"), _ctx(benchmark_parking_available=False))
    assert r.reason == "no_replacement_plan"


def test_sell_underfunded_pair_rejected_without_parking():
    buys = [{"ticker": "MSFT", "delta_amount": 1.0}]
    r = validate(_p(direction="SELL", ticker="AAPL"), _ctx(paired_buys=buys, benchmark_parking_available=False))
    assert r.reason == "no_replacement_plan"


def test_sell_daily_cap_reason_is_prefixed():
    r = validate(_p(direction="SELL", ticker="AAPL"), _ctx(sold_today_count=99))
    assert not r.approved and r.reason == "sell_guard_daily_sell_count_cap"


def test_safety_exit_bypasses_pairing():
    p = _p(direction="SELL", ticker="AAPL", source="safety", exit_name="stop_loss")
    r = validate(p, _ctx(benchmark_parking_available=False))
    assert r.approved and r.strategy_name == "proposal_safety" and r.planned_buys == ()


def test_safety_exit_not_in_names_needs_pairing():
    p = _p(direction="SELL", ticker="AAPL", source="safety", exit_name="take_profit")
    assert validate(p, _ctx(benchmark_parking_available=False)).reason == "no_replacement_plan"


def test_non_safety_source_with_safety_name_needs_pairing():
    p = _p(direction="SELL", ticker="AAPL", source="event", exit_name="stop_loss")
    assert validate(p, _ctx(benchmark_parking_available=False)).reason == "no_replacement_plan"


def test_safety_exit_still_needs_score_capital_and_holding():
    p = _p(direction="SELL", ticker="AAPL", source="safety", exit_name="stop_loss")
    assert validate(p, _ctx(research_lookup=lambda t: None)).reason == "missing_score"
    assert validate(p, _ctx(tradable_capital_usd=0.0)).reason == "capital_disabled"
    assert validate(dict(p, ticker="NVDA"), _ctx()).reason == "not_held"


def test_below_min_order():
    assert validate(_p(), _ctx(usable_cash_usd=5.0)).reason == "below_min_order"
    assert validate(_p(), _ctx(usable_cash_usd=0.0)).reason == "below_min_order"


def test_gateway_blocked_and_args():
    seen = {}

    def gw(ticker, direction, amount_usd, strategy_name, score):
        seen.update(locals())
        return SimpleNamespace(allowed=False, reasons=["nope"])
    r = validate(_p(), _ctx(gateway_check=gw))
    assert r.reason == "gateway_blocked"
    assert seen["strategy_name"] == "proposal_event" and seen["score"] == 7.0 and seen["direction"] == "BUY"


def test_gateway_exception_fails_closed():
    def gw(*a, **k):
        raise RuntimeError("boom")
    r = validate(_p(), _ctx(gateway_check=gw))
    assert not r.approved and r.reason == "gateway_error"


@pytest.mark.parametrize("res", [
    SimpleNamespace(allowed=True, reasons=[], _degraded_guards=["cash_anchor"]),
    SimpleNamespace(allowed=True, reasons=[], guard_details={"_degraded_guards": ["x"]}),
])
def test_gateway_degraded_rejects(res):
    r = validate(_p(), _ctx(gateway_check=lambda *a, **k: res))
    assert r.reason == "gateway_degraded"


def test_gateway_empty_degraded_ok():
    res = SimpleNamespace(allowed=True, reasons=[], _degraded_guards=[], guard_details={"_degraded_guards": []})
    assert validate(_p(), _ctx(gateway_check=lambda *a, **k: res)).approved


@pytest.mark.parametrize("source", ["event", "strategy", "rotation", "parking", "manual", "safety"])
def test_strategy_name_never_safety_or_tactical(source):
    r = validate(_p(source=source), _ctx())
    assert r.strategy_name == f"proposal_{source}"
    assert not StrategyRegistry.is_safety_control(r.strategy_name)
    assert r.strategy_name != "tactical_factor_rotation"


def test_rejections_also_carry_proposal_name():
    assert validate(_p(ticker="CASH"), _ctx()).strategy_name.startswith("proposal_")


# ---- structural guards ----
_ALLOWED_NUMERIC_ASSIGN = {"SCORE_MIN", "SCORE_MAX", "MIN_ORDER_USD_DEFAULT", "PCT_DENOMINATOR"}


def test_no_mission_numbers_as_literals():
    m = load_mission().model_dump()
    nums = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            nums.add(float(o))
    walk({k: v for k, v in m.items() if k != "version"})
    nums -= {0.0, 1.0, -1.0}
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    skip = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(isinstance(t, ast.Name) and t.id in _ALLOWED_NUMERIC_ASSIGN for t in targets):
                skip.update(id(x) for x in ast.walk(n))
    hits = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
            and id(n) not in skip and float(n.value) in nums]
    assert not hits, f"mission numbers copied as literals: {hits}"


def test_no_forbidden_imports():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    mods = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mods.append(n.module or "")
            mods += [f"{n.module}.{a.name}" for a in n.names]
    bad = [m for m in mods if any(s in m.lower() for s in
           ("automated_trading", "broker", "etoro", "llm", "risk_gateway", "litellm", "sqlalchemy", "requests", "httpx"))]
    assert not bad, bad
