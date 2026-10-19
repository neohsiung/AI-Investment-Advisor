"""Regime proxy for loosening condition 5 (G6): pure functions, 'not measurable' when data is missing.
體制代理（放寬條件 5）：純函式，資料缺漏即為 not measurable。"""
import math
from datetime import date, timedelta

from src.evaluation.regime import RegimeCheck, regime_cell, regime_condition


def _trend(n, drift=0.001):
    return [100.0 * (1 + drift) ** i for i in range(n)]


def test_regime_cell_needs_252():
    assert regime_cell(_trend(251)) is None
    assert regime_cell(_trend(252)) is not None


def test_regime_cell_labels():
    up = regime_cell(_trend(300, 0.001))
    down = regime_cell(_trend(300, -0.001))
    assert up.startswith("up_") and down.startswith("down_")
    calm = _trend(300, 0.001)
    wild = list(calm)
    for i in range(len(wild) - 21, len(wild)):          # last 21 days whipsaw: vol above its 252d median
        wild[i] = wild[i] * (1.04 if i % 2 else 0.96)
    assert regime_cell(calm).endswith("lovol")
    assert regime_cell(wild).endswith("hivol")


def test_regime_cell_rejects_non_finite_or_non_positive():
    bad = _trend(300)
    bad[-3] = math.nan
    assert regime_cell(bad) is None
    bad[-3] = 0.0
    assert regime_cell(bad) is None


def _weeks(cells, start=date(2026, 1, 5)):
    return [(start + timedelta(days=7 * i), c) for i, c in enumerate(cells)]


def test_regime_condition_single_cell_ok():
    weeks = _weeks(["up_lovol"] * 4)
    decisions = [weeks[0][0] + timedelta(days=i) for i in range(3)]
    r = regime_condition(weeks, decisions)
    assert r == RegimeCheck(True, True, {"up_lovol": 3})


def test_regime_condition_two_cells_need_min_each():
    weeks = _weeks(["up_lovol", "up_lovol", "down_hivol", "down_hivol"])
    many = [weeks[0][0] + timedelta(days=i % 5) for i in range(12)]
    few = [weeks[2][0] + timedelta(days=i) for i in range(4)]
    assert regime_condition(weeks, many + few).ok is False
    enough = [weeks[2][0] + timedelta(days=i % 5) for i in range(11)]
    r = regime_condition(weeks, many + enough)
    assert r.measurable and r.ok


def test_regime_condition_none_cell_is_not_measurable():
    weeks = _weeks(["up_lovol", None, "up_lovol"])
    r = regime_condition(weeks, [weeks[0][0]])
    assert (r.measurable, r.ok) == (False, False)


def test_regime_condition_no_weeks_not_measurable():
    assert regime_condition([], [date(2026, 1, 5)]).measurable is False
