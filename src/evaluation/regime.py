"""Market-regime proxy for loosening condition 5 (charter G6). Pure functions, no I/O.
體制代理（放寬條件 5）：純函式，無 I/O。

A regime cell is trend x volatility of SPY: 'up'/'down' = last close vs its 200-day mean; 'hivol'/'lovol' = sd of the
last 21 log returns vs the median of all rolling 21-day sds inside the last 252 closes. Missing or short data gives
None / not measurable, which blocks loosening: there is no default regime.
體制格＝SPY 趨勢×波動；資料缺漏或不足回 None／不可量測，放寬因此被擋，沒有預設體制。
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

MIN_CLOSES = 252
_EPS = 1e-12                       # float noise must not turn a flat tape into 'hivol' / 浮點雜訊不可把平盤判成高波動


def regime_cell(closes: Sequence[float]) -> Optional[str]:
    """'up_lovol' etc., or None if fewer than 252 usable closes. / 少於 252 筆可用收盤回 None。"""
    c = np.asarray(closes, dtype=float)
    if c.size < MIN_CLOSES or not np.all(np.isfinite(c)) or np.any(c <= 0):
        return None
    c = c[-MIN_CLOSES:]
    trend = "up" if c[-1] > c[-200:].mean() else "down"
    sd = np.lib.stride_tricks.sliding_window_view(np.diff(np.log(c)), 21).std(axis=1, ddof=1)
    vol = "hivol" if sd[-1] > np.median(sd) + _EPS else "lovol"
    return f"{trend}_{vol}"


@dataclass(frozen=True)
class RegimeCheck:
    measurable: bool
    ok: bool
    cells: Dict[str, int]


def regime_condition(cells_by_week: Sequence[Tuple[date, Optional[str]]], decision_dates: Sequence[date],
                     min_per_cell: int = 10) -> RegimeCheck:
    """Decisions are assigned to the cell of the latest week starting on or before them. Any week without a cell (or no
    weeks) -> not measurable. ok = the period had one cell only, or every cell has >= min_per_cell decisions.
    決策歸入「起始日不晚於它」的最近一週的格；任一週無格（或無週）即不可量測。"""
    weeks = sorted(cells_by_week, key=lambda w: w[0])
    if not weeks or any(cell is None for _, cell in weeks):
        return RegimeCheck(False, False, {})
    starts = [d for d, _ in weeks]
    counts = Counter({cell: 0 for _, cell in weeks})
    for d in decision_dates:
        counts[weeks[max(0, bisect_right(starts, d) - 1)][1]] += 1
    ok = len(counts) == 1 or all(n >= min_per_cell for n in counts.values())
    return RegimeCheck(True, ok, dict(counts))
