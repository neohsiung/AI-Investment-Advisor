"""G4 tests for src/evaluation/sequential.py — pure statistics, seeded, no network, no DB.
G4 測試：純統計、固定種子、無網路、無資料庫。"""
import numpy as np
import pytest

from src.evaluation import sequential as sq

SIGMA = 0.01  # daily-ish return sd used in simulations / 模擬用的日報酬標準差


def _series(seed: int, n: int, mu: float, sigma: float = SIGMA):
    return np.random.default_rng(seed).normal(mu, sigma, n)


# ---- winsorise / sample guard ----
def test_winsorise_clips_at_20pct():
    out = sq.winsorise([0.5, -0.9, 0.01])
    assert list(out) == [0.2, -0.2, 0.01]


def test_min_sample_guard_blocks_decision():
    r = sq.confidence_sequence_lower_bound(np.full(29, 0.05), alpha=0.05, sigma=SIGMA)
    assert r.insufficient_sample and not r.loosen_ok
    r30 = sq.confidence_sequence_lower_bound(np.full(30, 0.05), alpha=0.05, sigma=SIGMA)
    assert not r30.insufficient_sample and r30.loosen_ok


def test_alpha_and_sigma_validated():
    for bad in (0.0, 1.0, -0.1):
        with pytest.raises(ValueError):
            sq.confidence_sequence_lower_bound([0.01] * 40, alpha=bad, sigma=SIGMA)
    with pytest.raises(ValueError):
        sq.confidence_sequence_lower_bound([0.01] * 40, alpha=0.05, sigma=0.0)


def test_alpha_spending_helper():
    assert sq.loosening_alpha(10) == pytest.approx(0.005)
    assert sq.loosening_alpha(0) == pytest.approx(0.05)  # floor of 1 trial


def test_nan_input_rejected():
    with pytest.raises(ValueError):
        sq.confidence_sequence_lower_bound([0.01] * 35 + [float("nan")], alpha=0.05, sigma=SIGMA)


# ---- confidence sequence ----
def test_zero_effect_loosening_rate_within_alpha():
    """1000 seeded zero-mean series, bound checked at EVERY step (anytime-valid): rate <= alpha."""
    alpha, hits = 0.05, 0
    for seed in range(1000):
        x = _series(seed, 252, 0.0)
        if sq.confidence_sequence_any_time_loosen(x, alpha=alpha, sigma=SIGMA):
            hits += 1
    assert hits / 1000 <= alpha


def test_positive_effect_detected():
    detected = sum(
        sq.confidence_sequence_any_time_loosen(_series(s, 252, 0.003), alpha=0.05, sigma=SIGMA)
        for s in range(100)
    )
    assert detected >= 90


def test_negative_effect_never_loosens():
    assert not any(
        sq.confidence_sequence_any_time_loosen(_series(s, 252, -0.002), alpha=0.05, sigma=SIGMA)
        for s in range(50)
    )


def test_smaller_alpha_is_more_conservative():
    x = _series(7, 120, 0.002)
    lo5 = sq.confidence_sequence_lower_bound(x, alpha=0.05, sigma=SIGMA).lower
    lo005 = sq.confidence_sequence_lower_bound(x, alpha=0.005, sigma=SIGMA).lower
    assert lo005 < lo5 < float(np.mean(x))


def test_deterministic_given_seed():
    a = sq.confidence_sequence_lower_bound(_series(3, 100, 0.001), alpha=0.05, sigma=SIGMA)
    b = sq.confidence_sequence_lower_bound(_series(3, 100, 0.001), alpha=0.05, sigma=SIGMA)
    assert a == b


def test_required_sample_size_monotone():
    n_easy = sq.required_sample_size(sigma=0.03, delta=0.01, alpha=0.05)
    n_hard = sq.required_sample_size(sigma=0.05, delta=0.01, alpha=0.05 / 40)
    assert 30 <= n_easy < n_hard


# ---- CUSUM ----
def test_cusum_false_alarm_spacing_about_two_years():
    """Under the null, mean run length to false alarm ~ 504 obs (2y of 252). Tolerance 25%."""
    h = sq.CUSUM_THRESHOLD
    lengths = sq.cusum_run_lengths(h=h, k=sq.CUSUM_K, n_sim=2000, cap=5000, seed=12345)
    assert 504 * 0.75 <= float(np.mean(lengths)) <= 504 * 1.25


def test_calibration_reproduces_threshold():
    h = sq.calibrate_cusum_threshold(target_arl=504, k=sq.CUSUM_K, n_sim=2000, cap=5000, seed=1)
    assert h == pytest.approx(sq.CUSUM_THRESHOLD, rel=0.1)


def test_cusum_alarms_on_downward_shift():
    rng = np.random.default_rng(5)
    x = np.concatenate([rng.normal(0.001, SIGMA, 100), rng.normal(0.001 - 1.5 * SIGMA, SIGMA, 60)])
    res = sq.cusum_alarm(x, baseline_mean=0.001, sigma=SIGMA)
    assert res.alarm and res.alarm_index is not None and res.alarm_index >= 100


def test_cusum_quiet_on_stable_series():
    res = sq.cusum_alarm(np.full(200, 0.001), baseline_mean=0.001, sigma=SIGMA)
    assert not res.alarm and res.statistic == 0.0


def test_cusum_ignores_upward_moves():
    assert not sq.cusum_alarm(np.full(200, 0.05), baseline_mean=0.0, sigma=SIGMA).alarm


# ---- windows ----
def test_21d_windows_pass():
    x = np.concatenate([np.full(21, 0.001)] * 3)
    r = sq.consecutive_window_check(x, window_len=21, n_windows=3)
    assert r.ok and r.n_windows == 3 and r.cumulative_monotone


def test_21d_fails_when_one_window_negative():
    x = np.concatenate([np.full(21, 0.002), np.full(21, -0.001), np.full(21, 0.002)])
    assert not sq.consecutive_window_check(x, window_len=21, n_windows=3).ok


def test_21d_fails_when_one_window_dominates():
    x = np.concatenate([np.full(21, 0.0001), np.full(21, 0.0001), np.full(21, 0.01)])
    r = sq.consecutive_window_check(x, window_len=21, n_windows=3, max_share=0.5)
    assert not r.ok and r.max_share > 0.5


def test_too_short_series_fails_not_raises():
    r = sq.consecutive_window_check(np.full(40, 0.001), window_len=21, n_windows=3)
    assert not r.ok and r.n_windows < 3


def test_63d_two_windows_positive():
    assert sq.consecutive_window_check(np.full(126, 0.001), window_len=63, n_windows=2, max_share=None).ok
    x = np.concatenate([np.full(63, 0.001), np.full(63, -0.001)])
    assert not sq.consecutive_window_check(x, window_len=63, n_windows=2, max_share=None).ok


def test_overlapping_ranges_rejected():
    x = np.full(100, 0.001)
    with pytest.raises(ValueError):
        sq.check_window_ranges(x, [(0, 21), (10, 31), (31, 52)])
    with pytest.raises(ValueError):
        sq.check_window_ranges(x, [(0, 21), (21, 40)])  # unequal length


def test_ranges_non_overlapping_ok():
    x = np.full(100, 0.001)
    assert sq.check_window_ranges(x, [(0, 21), (21, 42), (42, 63)]).ok


def test_non_contiguous_ranges_rejected():
    with pytest.raises(ValueError):
        sq.check_window_ranges(np.full(100, 0.001), [(0, 21), (30, 51), (51, 72)])
