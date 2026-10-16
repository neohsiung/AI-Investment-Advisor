"""
Baseline strategies for the evaluation pipeline. Each returns target weights using ONLY data up to the
rebalance date (no look-ahead); execution lag and costs are applied by performance.backtest_weights.
評估管線的基準策略；每個只用到再平衡日當天以前的資料，執行延遲與成本由 backtest_weights 套用。
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd


def month_end_dates(index: pd.DatetimeIndex) -> List[pd.Timestamp]:
    """Last trading day of each month. The final, still-open month is NOT a rebalance date (its true month end
    is in the future), otherwise a truncated series would act on a partial month.
    各月最後交易日；尚未結束的最後一個月不算再平衡日（否則截斷的序列會對『不完整的月』做決策）。"""
    s = pd.Series(index, index=index)
    dates = list(s.groupby([index.year, index.month]).max())
    if dates and (dates[-1] + pd.offsets.BDay(1)).month == dates[-1].month:
        dates = dates[:-1]
    return dates


def benchmark_only(prices: pd.DataFrame, benchmark: str = "SPY") -> pd.DataFrame:
    w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    w[benchmark] = 1.0
    return w


def momentum_tilt(
    prices: pd.DataFrame, benchmark: str = "SPY", benchmark_weight: float = 0.7, top_k: int = 3,
    lookback: int = 126, skip: int = 21, trend_window: int = 200,
) -> pd.DataFrame:
    """Hold `benchmark_weight` in the benchmark; split the rest equally over the top_k momentum names that are
    also above their `trend_window` average at month end. No qualifying name -> 100% benchmark.
    benchmark 保留 benchmark_weight；其餘等分給月底動能最強且站上長期均線的 top_k 檔；無合格者則 100% 基準。"""
    cols = [c for c in prices.columns if c != benchmark]
    weights = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    sma = prices.rolling(trend_window).mean()
    mom = prices.shift(skip) / prices.shift(lookback + skip) - 1.0
    for d in month_end_dates(prices.index):
        if pd.isna(mom.loc[d, cols]).all():
            continue
        elig = [c for c in cols if pd.notna(mom.loc[d, c]) and pd.notna(sma.loc[d, c]) and prices.loc[d, c] > sma.loc[d, c]]
        picks = sorted(elig, key=lambda c: mom.loc[d, c], reverse=True)[:top_k]
        row = {c: 0.0 for c in prices.columns}
        if picks:
            row[benchmark] = benchmark_weight
            for c in picks:
                row[c] = (1.0 - benchmark_weight) / len(picks)
        else:
            row[benchmark] = 1.0
        weights.loc[d] = pd.Series(row)
    return weights
