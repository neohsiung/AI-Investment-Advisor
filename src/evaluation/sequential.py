"""
Sequential-evidence statistics for the autonomy charter (milestone G4). Pure numpy, no I/O, no DB, no settings, 0-LLM.
自治章程用的序列證據統計（G4）。純 numpy、無 I/O、無資料庫、無設定、0-LLM。

A future Change Engine may LOOSEN a threshold only when five conditions hold (this module supplies 1-4's
statistics; condition 5, regime, is out of scope here):
  1. anytime-valid confidence-sequence lower bound of the mean return > 0, at alpha_i = 0.05 / N_cum;
  2. >= 3 consecutive non-overlapping 21-day windows positive, cumulative sum monotone, no window > 50% of total;
  3. >= 2 non-overlapping 63-day windows positive;
  4. >= 30 settled observations (MIN_SAMPLE).
Tightening needs one trigger: the one-sided CUSUM alarm below.
未來的變更引擎只有在五條件成立時才可放寬門檻；本模組提供其中的統計量。收緊只需 CUSUM 報警一個觸發。

Nothing here decides anything live; callers pass in the returns, alpha, and sigma.
本模組不做任何實盤決策；報酬、alpha、sigma 皆由呼叫端傳入。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np

MIN_SAMPLE = 30                 # minimum settled observations before any decision / 下決定前的最少已結算筆數
WINSOR_LIMIT = 0.20             # returns clipped to +-20% / 報酬截尾於 ±20%
BASE_ALPHA = 0.05               # family-wise level; alpha_i = BASE_ALPHA / N_cum / 整體顯著水準
CUSUM_K = 0.5                   # reference value in sd units (tuned to detect a 1-sd downward shift) / 參考值（偵測 1 個標準差的下移）
CUSUM_TARGET_ARL = 504          # ~2 years of 252 daily observations per false alarm / 約每兩年一次誤報
# Calibrated with calibrate_cusum_threshold(target_arl=504, k=0.5, n_sim=20000, cap=5000, seed=20261018).
# 以上述呼叫校準；test_cusum_false_alarm_spacing_about_two_years 以獨立種子複驗。
CUSUM_THRESHOLD = 4.42


def winsorise(returns: Sequence[float], limit: float = WINSOR_LIMIT) -> np.ndarray:
    """Clip returns to [-limit, +limit]. 將報酬截尾到 [-limit, +limit]。"""
    return np.clip(np.asarray(returns, dtype=float), -limit, limit)


def loosening_alpha(n_cum: int, base: float = BASE_ALPHA) -> float:
    """alpha_i = base / N_cum (Bonferroni over every trial charged so far; floor of 1 trial).
    alpha_i = base / N_cum（對累計試驗數做 Bonferroni；至少 1）。"""
    return base / max(1, int(n_cum))


def _check_alpha_sigma(alpha: float, sigma: float) -> None:
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0,1), got {alpha}")
    if not (sigma > 0.0) or not math.isfinite(sigma):
        raise ValueError(f"sigma must be a positive finite number, got {sigma}")


def _clean(returns: Sequence[float]) -> np.ndarray:
    x = np.asarray(returns, dtype=float)
    if x.ndim != 1:
        raise ValueError("returns must be one-dimensional")
    if not np.all(np.isfinite(x)):
        raise ValueError("returns contain NaN/inf; missing data must be dropped and counted by the caller")
    return winsorise(x)


# --------------------------------------------------------------------------------------------------
# 1. Normal-mixture confidence sequence / 常態混合信賴序列
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ConfidenceSequenceResult:
    n: int
    mean: float
    lower: float                 # anytime-valid lower bound of the mean / 隨時有效的均值下界
    alpha: float
    sigma: float
    insufficient_sample: bool    # n < MIN_SAMPLE: no decision allowed / 樣本不足，不得決策
    loosen_ok: bool              # lower > 0 AND enough sample / 下界 > 0 且樣本足夠


def _mixing_rho(sigma: float, alpha: float, target_n: int) -> float:
    """Mixing precision tuned so the boundary is tightest near target_n observations (Howard et al. 2021).
    調整混合精度，使邊界在 target_n 筆附近最緊。"""
    v = target_n * sigma ** 2
    a = 2.0 * math.log(1.0 / alpha)
    return v / (a + math.log1p(a))


def _boundary(v: np.ndarray, rho: float, alpha: float) -> np.ndarray:
    """Ville boundary for S_n with intrinsic time V_n = n*sigma^2 under a N(0, 1/rho) mixture:
    P(exists n: S_n >= sqrt((V+rho) * (2 log(1/alpha) + log((V+rho)/rho)))) <= alpha  (valid for sigma-sub-Gaussian steps).
    以 N(0,1/rho) 混合的 Ville 邊界；每步為 sigma-次高斯時成立。"""
    return np.sqrt((v + rho) * (2.0 * math.log(1.0 / alpha) + np.log((v + rho) / rho)))


def confidence_sequence_path(
    returns: Sequence[float], alpha: float, sigma: float, target_n: int = 252
) -> np.ndarray:
    """Lower bound of the mean after each observation (length len(returns)). 每筆之後的均值下界。"""
    _check_alpha_sigma(alpha, sigma)
    x = _clean(returns)
    if x.size == 0:
        return np.empty(0)
    n = np.arange(1, x.size + 1, dtype=float)
    rho = _mixing_rho(sigma, alpha, target_n)
    return (np.cumsum(x) - _boundary(n * sigma ** 2, rho, alpha)) / n


def confidence_sequence_lower_bound(
    returns: Sequence[float], alpha: float, sigma: float, target_n: int = 252
) -> ConfidenceSequenceResult:
    """Lower confidence-sequence bound for the mean return at the current sample size.

    sigma is the caller's sub-Gaussian variance proxy (std of the winsorised returns; <= 0.2 is a hard ceiling because
    of the clipping). Supplying a sigma smaller than the true sd voids the guarantee, so the caller should use an
    upper estimate. alpha is the per-trial level, normally loosening_alpha(N_cum).
    sigma 為呼叫端提供的次高斯變異代理（截尾後標準差；因截尾上限為 0.2）。低估 sigma 會使保證失效，請用偏大的估計。
    alpha 為單次試驗水準，通常為 loosening_alpha(N_cum)。
    """
    path = confidence_sequence_path(returns, alpha, sigma, target_n)
    n = int(path.size)
    if n == 0:
        return ConfidenceSequenceResult(0, 0.0, -math.inf, alpha, sigma, True, False)
    mean = float(np.mean(_clean(returns)))
    lower = float(path[-1])
    short = n < MIN_SAMPLE
    return ConfidenceSequenceResult(n, mean, lower, alpha, sigma, short, (not short) and lower > 0.0)


def confidence_sequence_any_time_loosen(
    returns: Sequence[float], alpha: float, sigma: float, target_n: int = 252
) -> bool:
    """True if the lower bound exceeded 0 at ANY step from MIN_SAMPLE on (what the zero-effect simulation measures).
    從 MIN_SAMPLE 起任一時點下界 > 0 即為 True（零效應模擬量的就是這個）。"""
    path = confidence_sequence_path(returns, alpha, sigma, target_n)
    return bool(path.size >= MIN_SAMPLE and np.any(path[MIN_SAMPLE - 1:] > 0.0))


def required_sample_size(sigma: float, delta: float, alpha: float, target_n: int = 252, max_n: int = 100_000) -> int:
    """Smallest n at which a TRUE mean of delta gives an expected lower bound > 0 (deterministic: S_n = n*delta).
    Planning aid only; sigma is an assumption unless measured. 規劃用；sigma 若未實測即為假設。"""
    _check_alpha_sigma(alpha, sigma)
    if delta <= 0:
        raise ValueError("delta must be positive")
    rho = _mixing_rho(sigma, alpha, target_n)
    n = np.arange(1, max_n + 1, dtype=float)
    ok = np.nonzero(n * delta > _boundary(n * sigma ** 2, rho, alpha))[0]
    if ok.size == 0:
        return max_n
    return max(MIN_SAMPLE, int(ok[0]) + 1)


# --------------------------------------------------------------------------------------------------
# 2. One-sided CUSUM (downward) / 單邊 CUSUM（偵測下移）
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CusumResult:
    alarm: bool
    alarm_index: Optional[int]   # first index at which the statistic exceeded h / 首次超過門檻的索引
    statistic: float             # statistic after the last observation / 最後一筆之後的統計量
    max_statistic: float
    threshold: float


def cusum_alarm(
    returns: Sequence[float],
    baseline_mean: float,
    sigma: float,
    k: float = CUSUM_K,
    h: float = CUSUM_THRESHOLD,
) -> CusumResult:
    """S_t = max(0, S_{t-1} + (baseline - x_t)/sigma - k); alarm when S_t > h. Detects a DOWNWARD shift only.
    S_t = max(0, S_{t-1} + (基準 - x_t)/sigma - k)；S_t > h 即報警。只偵測下移。"""
    _check_alpha_sigma(0.5, sigma)
    x = _clean(returns)
    s = peak = 0.0
    first: Optional[int] = None
    for i, v in enumerate(x):
        s = max(0.0, s + (baseline_mean - float(v)) / sigma - k)
        peak = max(peak, s)
        if first is None and s > h:
            first = i
    return CusumResult(first is not None, first, s, peak, h)


def _null_cusum_paths(k: float, n_sim: int, cap: int, seed: int) -> np.ndarray:
    """Running-max of the CUSUM statistic over n_sim iid N(0,1) null series. Shape (n_sim, cap).
    n_sim 條 iid N(0,1) 零假設序列上 CUSUM 統計量的累計最大值。"""
    rng = np.random.default_rng(seed)
    s = np.zeros(n_sim)
    run_max = np.empty((n_sim, cap))
    cur = np.zeros(n_sim)
    for t in range(cap):
        s = np.maximum(0.0, s + rng.standard_normal(n_sim) - k)
        cur = np.maximum(cur, s)
        run_max[:, t] = cur
    return run_max


def _run_lengths_from_paths(run_max: np.ndarray, h: float) -> np.ndarray:
    crossed = run_max > h
    first = np.where(crossed.any(axis=1), crossed.argmax(axis=1) + 1, run_max.shape[1])
    return first.astype(float)


def cusum_run_lengths(h: float, k: float = CUSUM_K, n_sim: int = 2000, cap: int = 5000, seed: int = 0) -> np.ndarray:
    """Simulated run lengths to first false alarm under the null (censored at cap). 零假設下首次誤報的模擬長度。"""
    return _run_lengths_from_paths(_null_cusum_paths(k, n_sim, cap, seed), h)


def calibrate_cusum_threshold(
    target_arl: float = CUSUM_TARGET_ARL,
    k: float = CUSUM_K,
    n_sim: int = 20000,
    cap: int = 5000,
    seed: int = 20261018,
) -> float:
    """Bisect h so the null average run length (ARL0) ~ target_arl, using common random numbers.
    Censoring at cap biases ARL0 slightly low; keep cap >= ~10x target. 以共同亂數二分搜尋 h 使 ARL0 ≈ 目標。"""
    run_max = _null_cusum_paths(k, n_sim, cap, seed)
    lo, hi = 0.5, 20.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if _run_lengths_from_paths(run_max, mid).mean() < target_arl:
            lo = mid
        else:
            hi = mid
    return round(0.5 * (lo + hi), 2)


# --------------------------------------------------------------------------------------------------
# 3. Consecutive non-overlapping window checks / 連續互不重疊窗口檢查
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class WindowCheckResult:
    ok: bool
    n_windows: int
    window_sums: Tuple[float, ...]
    all_positive: bool
    cumulative_monotone: bool    # cumulative sum at window ends strictly increasing / 窗口末累計和嚴格遞增
    max_share: float             # largest window's share of the total (nan when total <= 0) / 最大窗口占總和比
    share_ok: bool


def check_window_ranges(
    returns: Sequence[float],
    ranges: Sequence[Tuple[int, int]],
    max_share: Optional[float] = 0.5,
) -> WindowCheckResult:
    """Check explicit [start, end) ranges. Ranges must be equal-length, ordered, non-overlapping AND back-to-back
    (consecutive); otherwise ValueError, because evidence from overlapping windows is not independent.
    檢查明確的 [start, end) 區間。須等長、依序、互不重疊且首尾相接，否則 ValueError（重疊的窗口證據不獨立）。"""
    x = _clean(returns)
    rs = [(int(a), int(b)) for a, b in ranges]
    if not rs:
        raise ValueError("no ranges given")
    length = rs[0][1] - rs[0][0]
    if length <= 0:
        raise ValueError("empty window")
    for i, (a, b) in enumerate(rs):
        if b - a != length:
            raise ValueError("windows must have equal length")
        if a < 0 or b > x.size:
            raise ValueError("window outside the series")
        if i and a < rs[i - 1][1]:
            raise ValueError("windows overlap")
        if i and a != rs[i - 1][1]:
            raise ValueError("windows must be consecutive (back-to-back)")
    sums = tuple(float(x[a:b].sum()) for a, b in rs)
    cum = np.cumsum(sums)
    positive = all(s > 0 for s in sums)
    monotone = bool(np.all(np.diff(np.concatenate([[0.0], cum])) > 0))
    total = float(cum[-1])
    share = max(sums) / total if total > 0 else float("nan")
    share_ok = True if max_share is None else (total > 0 and share <= max_share)
    return WindowCheckResult(positive and monotone and share_ok, len(rs), sums, positive, monotone, share, share_ok)


def consecutive_window_check(
    returns: Sequence[float],
    window_len: int = 21,
    n_windows: int = 3,
    max_share: Optional[float] = 0.5,
) -> WindowCheckResult:
    """Take the most recent n_windows back-to-back windows of window_len and run check_window_ranges.
    Defaults are the 21-day rule (>=3 windows positive, cumulative sum monotone, no window > 50% of total);
    use window_len=63, n_windows=2, max_share=None for the 63-day rule. A too-short series FAILS (does not raise).
    取最近 n_windows 個首尾相接的窗口檢查。預設為 21 日規則；63 日規則用 window_len=63, n_windows=2, max_share=None。
    序列太短視為不通過（不丟例外）。"""
    x = _clean(returns)
    avail = x.size // window_len
    if avail < n_windows:
        return WindowCheckResult(False, avail, (), False, False, float("nan"), False)
    start = x.size - n_windows * window_len
    ranges = [(start + i * window_len, start + (i + 1) * window_len) for i in range(n_windows)]
    return check_window_ranges(x, ranges, max_share)
