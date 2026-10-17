"""The strategy lab counts every variant once (multiple-testing ledger) and never promotes noise."""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from src.evaluation.strategies import momentum_tilt
from src.services.strategy_lab_service import StrategyLabService, expand_grid, params_hash


@pytest.fixture
def engine():
    e = create_engine("sqlite://")
    with e.begin() as c:
        c.execute(text("CREATE TABLE strategy_trials (params_hash VARCHAR(64) PRIMARY KEY, family VARCHAR(64) NOT NULL, "
                       "params_json TEXT NOT NULL, first_eval_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                       "last_eval_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, n_evals INTEGER NOT NULL DEFAULT 0, "
                       "last_metrics TEXT, last_verdict TEXT, status VARCHAR(24) NOT NULL DEFAULT 'rejected')"))
    return e


def _panel(n=1500, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    mk = lambda mu: 100 * np.cumprod(1 + rng.normal(mu, 0.012, n))
    return pd.DataFrame({"SPY": mk(0.0004), "A": mk(0.0003), "B": mk(0.0003), "C": mk(0.0003), "D": mk(0.0003), "E": mk(0.0003)}, index=idx)


FAMILIES = {"momentum_tilt": {"fn": momentum_tilt, "grid": {"top_k": [2, 3], "lookback": [63, 126], "benchmark_weight": [0.7]}}}


def test_grid_expansion_and_hash_are_stable():
    g = expand_grid({"a": [1, 2], "b": [3]})
    assert g == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]
    assert params_hash("f", {"x": 1, "y": 2}) == params_hash("f", {"y": 2, "x": 1})


def test_each_variant_is_counted_once_across_runs(engine):
    lab = StrategyLabService(engine=engine, families=FAMILIES)
    r1 = lab.run(_panel())
    assert r1["n_trials_total"] == 4 and r1["variants_evaluated"] == 4
    r2 = lab.run(_panel())
    assert r2["n_trials_total"] == 4                      # re-evaluating is not a new trial
    with engine.connect() as c:
        assert c.execute(text("SELECT MIN(n_evals) FROM strategy_trials")).scalar() == 2


def test_adding_variants_raises_n_for_everyone(engine):
    lab = StrategyLabService(engine=engine, families=FAMILIES)
    lab.run(_panel())
    bigger = {"momentum_tilt": {"fn": momentum_tilt, "grid": {"top_k": [2, 3, 5], "lookback": [63, 126, 252], "benchmark_weight": [0.7]}}}
    r = StrategyLabService(engine=engine, families=bigger).run(_panel())
    assert r["n_trials_total"] == 9                       # 4 old + 5 new distinct variants


def test_noise_is_never_promoted(engine):
    r = StrategyLabService(engine=engine, families=FAMILIES).run(_panel())
    assert r["shadow_candidates"] == []
    assert all(x["status"] in ("rejected", "error") for x in r["results"])


def test_failures_are_recorded_not_hidden(engine):
    bad = {"momentum_tilt": {"fn": lambda p, **k: (_ for _ in ()).throw(RuntimeError("boom")), "grid": {"top_k": [1]}}}
    r = StrategyLabService(engine=engine, families=bad).run(_panel())
    assert r["results"][0]["status"] == "error" and "boom" in r["results"][0]["error"]


# ── WP8a: quarterly trial budget (mission.budgets.max_hypothesis_trials_per_quarter) ──────────────────────────────
def test_quarter_bounds_are_calendar_quarters_in_utc():
    from datetime import datetime, timezone
    from src.services.strategy_lab_service import quarter_bounds
    s, e = quarter_bounds(datetime(2026, 11, 20, tzinfo=timezone.utc))
    assert (s, e) == (datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc))
    s, e = quarter_bounds(datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc))
    assert e == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_new_trials_stop_at_the_quarterly_cap_and_are_reported(engine):
    lab = StrategyLabService(engine=engine, families=FAMILIES, max_new_trials_per_quarter=3)
    r = lab.run(_panel())                                   # grid has 4 variants, budget 3
    assert r["variants_evaluated"] == 3
    assert r["trials_deferred"] == 1 and r["cap_reached"] is True
    assert lab.trial_count() == 3                           # the 4th was NOT registered (N is not inflated)


def test_the_cap_never_blocks_re_evaluating_existing_trials(engine):
    StrategyLabService(engine=engine, families=FAMILIES, max_new_trials_per_quarter=4).run(_panel())
    again = StrategyLabService(engine=engine, families=FAMILIES, max_new_trials_per_quarter=1).run(_panel())
    assert again["variants_evaluated"] == 4 and again["cap_reached"] is False and again["trials_deferred"] == 0


def test_an_earlier_quarters_trials_do_not_use_this_quarters_budget(engine):
    lab = StrategyLabService(engine=engine, families=FAMILIES, max_new_trials_per_quarter=4)
    lab.run(_panel())
    with engine.begin() as c:                               # pretend all four were first seen last year
        c.execute(text("UPDATE strategy_trials SET first_eval_at = '2025-01-15 00:00:00'"))
    assert lab.quarter_trial_count() == 0


def test_cap_defaults_to_the_mission_budget(engine):
    from src.config.mission import load_mission
    lab = StrategyLabService(engine=engine, families=FAMILIES)
    assert lab.max_new_trials_per_quarter == load_mission().budgets.max_hypothesis_trials_per_quarter


def test_cap_reached_is_logged_as_a_warning(engine):
    from unittest.mock import patch
    lab = StrategyLabService(engine=engine, families=FAMILIES, max_new_trials_per_quarter=1)
    with patch("src.services.strategy_lab_service.logger") as log:
        lab.run(_panel())
    assert any("cap" in str(c.args[0]).lower() for c in log.warning.call_args_list)
