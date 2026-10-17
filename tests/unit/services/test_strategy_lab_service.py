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
