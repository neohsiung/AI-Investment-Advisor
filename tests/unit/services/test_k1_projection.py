"""K1 clear-date projection: when does the rolling 30-day LLM cost ratio fall back under the threshold?
K1 預計解除日：30 天滾動 LLM 成本比率何時回到門檻以下？"""
from datetime import date, timedelta

import pytest

from src.services.k1_projection import project_k1_clear, trailing_average

TODAY = date(2026, 10, 20)


def _hist(per_day: dict):
    return {TODAY - timedelta(days=i): v for i, v in per_day.items()}


def test_trailing_average_uses_the_last_n_days_including_today():
    hist = {TODAY - timedelta(days=i): float(i) for i in range(10)}      # 0,1,...,9
    assert trailing_average(hist, TODAY, 7) == pytest.approx(3.0)         # days 0..6 -> mean 3


def test_zero_spend_clears_when_the_expensive_days_roll_out_of_the_window():
    # $9 spent 25 days ago, nothing since; NAV 1650, threshold 3% -> allowed 30d cost = 1650*0.03*30/365 = $4.07
    hist = _hist({25: 9.0})
    d = project_k1_clear(hist, TODAY, nav=1650.0, threshold_pct=3.0, monthly_subscription=0.0, rate_per_day=0.0)
    # the $9 day leaves the window (window = d-29 .. d) once d - 29 > today - 25, i.e. 5 days ahead
    assert d == TODAY + timedelta(days=5)


def test_rate_above_the_allowance_never_clears_within_the_horizon():
    hist = _hist({i: 0.5 for i in range(30)})
    assert project_k1_clear(hist, TODAY, 1650.0, 3.0, 0.0, rate_per_day=0.5, horizon=90) is None


def test_rate_below_the_allowance_clears_once_history_rolls_off():
    # history $0.5/day for 30 days (=15); future $0.10/day. allowance 4.07 -> need 30d sum <= 4.07.
    hist = _hist({i: 0.5 for i in range(30)})
    d = project_k1_clear(hist, TODAY, 1650.0, 3.0, 0.0, rate_per_day=0.10, horizon=90)
    # after k future days the window holds (30-k) old days at 0.5 and k new days at 0.1
    # allowance 4.0685; (30-k)*0.5 + k*0.1 <= 4.0685  ->  k >= 27.3  ->  28 days ahead
    assert d == TODAY + timedelta(days=28)


def test_subscription_cost_shrinks_the_allowance():
    hist = _hist({})
    with_sub = project_k1_clear(hist, TODAY, 1650.0, 3.0, monthly_subscription=3.0, rate_per_day=0.2, horizon=90)
    without = project_k1_clear(hist, TODAY, 1650.0, 3.0, monthly_subscription=0.0, rate_per_day=0.2, horizon=90)
    assert without is not None and (with_sub is None or with_sub >= without)


def test_already_under_the_threshold_is_clear_tomorrow():
    # callers only ask while K1 is in breach; if it is already fine the first day ahead qualifies
    assert project_k1_clear(_hist({i: 0.1 for i in range(30)}), TODAY, 1650.0, 3.0, 0.0, 0.1) == TODAY + timedelta(days=1)


def test_unusable_nav_raises_instead_of_guessing():
    with pytest.raises(ValueError):
        project_k1_clear({}, TODAY, nav=0.0, threshold_pct=3.0, monthly_subscription=0.0, rate_per_day=0.0)


def test_watchdog_k1_note_carries_the_projected_clear_date():
    from src.services.mission_watchdog_service import MissionWatchdogService
    hist = _hist({i: 0.5 for i in range(30)})
    svc = MissionWatchdogService("u", engine=object(), nav_usd=1650.0, llm_cost_30d_usd=15.0,
                                 monthly_subscription_usd=0.0, llm_daily_history=hist)
    k1 = next(r for r in svc.evaluate(today=TODAY)["criteria"] if r["id"] == "K1")
    assert k1["status"] == "breach"
    assert "projected clear" in k1["note"] and "beyond 90 days" in k1["note"]        # 0.5/day never clears
    assert k1["clears_on"] is None


def test_watchdog_k1_projection_is_skipped_when_the_total_was_injected_without_history():
    from src.services.mission_watchdog_service import MissionWatchdogService
    svc = MissionWatchdogService("u", engine=object(), nav_usd=1650.0, llm_cost_30d_usd=15.0, monthly_subscription_usd=0.0)
    k1 = next(r for r in svc.evaluate(today=TODAY)["criteria"] if r["id"] == "K1")
    assert "projected clear" not in k1["note"]
