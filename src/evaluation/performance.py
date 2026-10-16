"""
Honest performance statistics for strategy evaluation (pure numpy/pandas, no I/O, 0-LLM).
誠實的策略績效統計（純 numpy/pandas、無 I/O、0-LLM）。

Everything here is measured NET of costs and RELATIVE to a benchmark, with a multiple-testing correction
(Deflated Sharpe Ratio, Bailey & Lopez de Prado 2014). It replaces the old evaluators that used full-sample
quantiles, no costs and no benchmark (mission: kill criterion K7).
一切以『扣成本』與『相對基準』衡量，並做多重檢定校正（Deflated Sharpe）；取代舊評估器（全樣本分位數、無成本、無基準）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from statistics import NormalDist
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


@dataclass
class PerformanceStats:
    n_obs: int
    ann_return: float
    ann_benchmark_return: float
    ann_excess_return: float
    tracking_error: float
    information_ratio: float
    t_stat_excess: float
    sharpe: float
    max_drawdown: float
    skew: float
    kurtosis: float

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def _max_drawdown(returns: pd.Series) -> float:
    curve = (1.0 + returns).cumprod()
    peak = curve.cummax()
    return float(((curve / peak) - 1.0).min()) if len(curve) else 0.0


def compute_performance(returns: pd.Series, benchmark: pd.Series, periods_per_year: int = 252) -> PerformanceStats:
    """Net-of-cost strategy returns vs benchmark returns (aligned daily). / 扣成本後策略報酬 vs 基準報酬。"""
    df = pd.concat([returns.rename("r"), benchmark.rename("b")], axis=1).dropna()
    n = len(df)
    if n < 30:
        raise ValueError(f"need >= 30 aligned observations, got {n}")
    r, b = df["r"], df["b"]
    ex = r - b
    ann = lambda x: float((1.0 + x).prod() ** (periods_per_year / len(x)) - 1.0)
    te = float(ex.std(ddof=1) * math.sqrt(periods_per_year))
    ann_ex = float(ex.mean() * periods_per_year)
    ir = ann_ex / te if te > 0 else 0.0
    t_stat = float(ex.mean() / (ex.std(ddof=1) / math.sqrt(n))) if ex.std(ddof=1) > 0 else 0.0
    sd = float(r.std(ddof=1))
    sharpe = float(r.mean() / sd * math.sqrt(periods_per_year)) if sd > 0 else 0.0
    return PerformanceStats(
        n_obs=n, ann_return=ann(r), ann_benchmark_return=ann(b), ann_excess_return=ann_ex,
        tracking_error=te, information_ratio=ir, t_stat_excess=t_stat, sharpe=sharpe,
        max_drawdown=_max_drawdown(r), skew=float(ex.skew()), kurtosis=float(ex.kurt() + 3.0),
    )


def expected_max_sharpe(n_trials: int, var_sharpe_trials: float) -> float:
    """E[max SR] across n independent trials of a zero-skill strategy (per-period units).
    n 次獨立試驗中、零技能策略的期望最大夏普（每期單位）。"""
    if n_trials <= 1:
        return 0.0
    sd = math.sqrt(max(var_sharpe_trials, 0.0))
    return sd * ((1.0 - EULER_GAMMA) * _N.inv_cdf(1.0 - 1.0 / n_trials)
                 + EULER_GAMMA * _N.inv_cdf(1.0 - 1.0 / (n_trials * math.e)))


def deflated_sharpe_ratio(
    sharpe_per_period: float, n_obs: int, skew: float, kurt: float,
    n_trials: int, var_sharpe_trials: Optional[float] = None,
) -> float:
    """Probability that the true Sharpe exceeds what the best of `n_trials` zero-skill trials would show.
    `sharpe_per_period` is NOT annualised. Returns a probability in [0, 1]; promotion needs > 0.95.
    若 var_sharpe_trials 未提供，以 1/n_obs（夏普估計量在虛無假設下的變異數近似）代替。
    真實 Sharpe 超過『n_trials 次零技能試驗中最佳者』的機率；晉升需 > 0.95。"""
    if n_obs < 30:
        raise ValueError("need >= 30 observations")
    v = var_sharpe_trials if var_sharpe_trials is not None else 1.0 / n_obs
    sr0 = expected_max_sharpe(max(1, int(n_trials)), v)
    denom = 1.0 - skew * sharpe_per_period + (kurt - 1.0) / 4.0 * sharpe_per_period ** 2
    if denom <= 0:
        return 0.0
    z = (sharpe_per_period - sr0) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return float(_N.cdf(z))


def years_to_significance(information_ratio: float, t_target: float = 3.0) -> float:
    """Years of live data needed for the excess-return t-stat to reach t_target: T = (t / IR)^2.
    實盤要累積多少年，超額報酬的 t 值才達 t_target：T = (t / IR)^2。"""
    if information_ratio <= 0:
        return math.inf
    return (t_target / information_ratio) ** 2


def purged_walk_forward_splits(n: int, n_splits: int, embargo: int = 5, min_train: int = 252) -> List[Dict[str, range]]:
    """Expanding-window splits: train [0, a), purge+embargo gap, test [b, c). Test windows never overlap.
    擴展視窗切分：訓練 [0,a)，空窗（purge/embargo），測試 [b,c)；各測試窗互不重疊。"""
    if n < min_train + n_splits * 20:
        raise ValueError("series too short for the requested splits")
    test_len = (n - min_train) // n_splits
    out = []
    for i in range(n_splits):
        start = min_train + i * test_len
        end = start + test_len if i < n_splits - 1 else n
        out.append({"train": range(0, max(0, start - embargo)), "test": range(start, end)})
    return out


def turnover_cost(weights: pd.DataFrame, cost_bps: float) -> pd.Series:
    """Cost per day as a fraction of NAV: sum(|dw|) * cost_bps/1e4 (one-way). / 每日成本（占淨值比例）。"""
    dw = weights.diff().abs()
    dw.iloc[0] = weights.iloc[0].abs()          # entering the first positions costs too
    return dw.sum(axis=1) * (cost_bps / 1e4)


def backtest_weights(prices: pd.DataFrame, weights: pd.DataFrame, cost_bps: float, lag: int = 1) -> pd.Series:
    """Daily net return of target weights. A signal computed from data up to the close of day t is traded at the
    close of day t+lag and first earns the return of day t+lag+1 (lag >= 1: no look-ahead, not even same-close
    execution). `weights` rows are target weights (columns = prices columns), forward-filled between rebalance
    dates. / 訊號用到 t 日收盤的資料，於 t+lag 日收盤成交，最早賺到 t+lag+1 日的報酬（不允許同一收盤價成交）。"""
    if lag < 1:
        raise ValueError("lag must be >= 1 (no look-ahead)")
    rets = prices.pct_change().fillna(0.0)
    w = weights.reindex(prices.index).ffill().fillna(0.0)[prices.columns]
    held = w.shift(lag + 1).fillna(0.0)
    gross = (held * rets).sum(axis=1)
    return gross - turnover_cost(held, cost_bps)
