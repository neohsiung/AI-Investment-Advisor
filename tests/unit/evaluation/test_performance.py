import math

import numpy as np
import pandas as pd
import pytest

from src.evaluation.performance import (
    backtest_weights, compute_performance, deflated_sharpe_ratio, expected_max_sharpe,
    purged_walk_forward_splits, turnover_cost, years_to_significance,
)


def _series(vals, start="2020-01-01"):
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)))


def test_identical_series_have_zero_excess():
    r = _series(np.random.default_rng(1).normal(0.0005, 0.01, 500))
    s = compute_performance(r, r)
    assert s.ann_excess_return == pytest.approx(0.0, abs=1e-12) and s.information_ratio == 0.0


def test_positive_constant_edge_gives_large_t():
    rng = np.random.default_rng(2)
    b = _series(rng.normal(0.0004, 0.01, 1000))
    s = compute_performance(b + 0.0005, b)
    assert s.ann_excess_return == pytest.approx(0.0005 * 252, rel=1e-6)
    assert s.t_stat_excess > 10          # zero tracking error noise -> huge t


def test_dsr_penalises_many_trials():
    kw = dict(sharpe_per_period=0.08, n_obs=1250, skew=0.0, kurt=3.0)
    one = deflated_sharpe_ratio(n_trials=1, **kw)
    many = deflated_sharpe_ratio(n_trials=200, **kw)
    assert one > many and one > 0.99 and many < 0.95


def test_expected_max_sharpe_grows_with_trials_and_is_zero_for_one():
    assert expected_max_sharpe(1, 0.001) == 0.0
    assert expected_max_sharpe(100, 0.001) > expected_max_sharpe(10, 0.001) > 0


def test_years_to_significance_matches_the_formula():
    assert years_to_significance(0.67, 3.0) == pytest.approx((3 / 0.67) ** 2)
    assert years_to_significance(0.3, 3.0) == pytest.approx(100.0)
    assert years_to_significance(-0.1) == math.inf


def test_walk_forward_splits_do_not_overlap_and_embargo_the_train_end():
    sp = purged_walk_forward_splits(1500, n_splits=4, embargo=5, min_train=252)
    assert len(sp) == 4
    for a, b in zip(sp, sp[1:]):
        assert a["test"].stop == b["test"].start
    for s in sp:
        assert s["train"].stop <= s["test"].start - 5
    with pytest.raises(ValueError):
        purged_walk_forward_splits(100, 4)


def test_backtest_has_no_lookahead_and_charges_costs():
    idx = pd.bdate_range("2021-01-01", periods=10)
    prices = pd.DataFrame({"A": [100, 100, 110, 110, 110, 110, 110, 110, 110, 110]}, index=idx, dtype=float)
    # decide to hold 100% A at day 1 (signal known at close of day 1); the +10% happens on day 2
    w = pd.DataFrame({"A": [0.0, 1.0] + [np.nan] * 8}, index=idx)
    gross = backtest_weights(prices, w, cost_bps=0.0, lag=1)
    assert gross.iloc[2] == pytest.approx(0.0)      # position only starts after the lag -> misses the jump
    assert gross.iloc[3] == pytest.approx(0.0)
    with pytest.raises(ValueError):
        backtest_weights(prices, w, cost_bps=0.0, lag=0)
    net = backtest_weights(prices, w, cost_bps=100.0, lag=1)       # 1% one-way cost on entry
    assert net.iloc[3] == pytest.approx(-0.01)


def test_turnover_cost_counts_both_legs_of_a_switch():
    idx = pd.bdate_range("2021-01-01", periods=3)
    w = pd.DataFrame({"A": [1.0, 0.0, 0.0], "B": [0.0, 1.0, 1.0]}, index=idx)
    c = turnover_cost(w, cost_bps=10.0)
    assert c.iloc[0] == pytest.approx(0.001) and c.iloc[1] == pytest.approx(0.002) and c.iloc[2] == 0.0


# ── strategies + runner ──────────────────────────────────────────────────────
def _panel(n=1500, seed=3, drift_a=0.0008):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    spy = 100 * np.cumprod(1 + rng.normal(0.0004, 0.010, n))
    a = 100 * np.cumprod(1 + rng.normal(drift_a, 0.015, n))
    b = 100 * np.cumprod(1 + rng.normal(0.0002, 0.015, n))
    return pd.DataFrame({"SPY": spy, "A": a, "B": b}, index=idx)


def test_momentum_tilt_uses_only_past_data():
    from src.evaluation.strategies import momentum_tilt
    p = _panel()
    w_full = momentum_tilt(p)
    cut = p.index[900]
    w_cut = momentum_tilt(p.loc[:cut])
    common = w_cut.dropna(how="all").index
    pd.testing.assert_frame_equal(w_full.loc[common], w_cut.loc[common])    # same decisions with/without the future


def test_weights_sum_to_one_on_rebalance_dates():
    from src.evaluation.strategies import momentum_tilt
    w = momentum_tilt(_panel()).dropna(how="all")
    assert np.allclose(w.sum(axis=1), 1.0)


def test_benchmark_only_has_zero_excess_before_costs():
    from src.evaluation.runner import evaluate_strategy
    from src.evaluation.strategies import benchmark_only
    res = evaluate_strategy(_panel(), benchmark_only, cost_bps=0.0)
    assert abs(res["full_sample"]["ann_excess_return"]) < 1e-3
    assert res["verdict"]["promotable"] is False


def test_costs_reduce_the_result():
    from src.evaluation.runner import evaluate_strategy
    from src.evaluation.strategies import momentum_tilt
    p = _panel()
    free = evaluate_strategy(p, momentum_tilt, cost_bps=0.0)["full_sample"]["ann_return"]
    paid = evaluate_strategy(p, momentum_tilt, cost_bps=50.0)["full_sample"]["ann_return"]
    assert paid < free


def test_noise_strategy_is_not_promotable_even_with_a_lucky_trial():
    from src.evaluation.runner import evaluate_strategy
    from src.evaluation.strategies import momentum_tilt
    res = evaluate_strategy(_panel(drift_a=0.0004), momentum_tilt, n_trials=50)
    assert res["verdict"]["promotable"] is False and res["verdict"]["n_trials"] == 50
