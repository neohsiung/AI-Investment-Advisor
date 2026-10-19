"""Synthetic evidence for the charter change engine tests (G6/G9): BandSeries built without a database.
章程變更引擎測試用的合成證據：不經資料庫直接造 BandSeries。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from src.services.marginal_band_evaluator import BandSeries

COST_GAP = 0.001          # the 2x-cost series is the 1x series minus this / 2 倍成本序列＝1 倍序列減此值


def stream(mu: float, sigma: float, n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).normal(mu, sigma, n)


def band_series(key: str, x: Sequence[float], *, horizon: int, mult: float, cur: float = 5.5,
                chal: float = 5.0) -> BandSeries:
    arr = np.asarray(x, dtype=float)
    return BandSeries(key, horizon, cur, chal, mult, arr, arr.copy(), int(arr.size))


def series_dict(key: str, x: Sequence[float], *, cur: float = 5.5, chal: float = 5.0,
                x2: Optional[Sequence[float]] = None) -> Dict[Tuple[int, float], BandSeries]:
    """{(5|63, 1.0|2.0): BandSeries} from one return stream (2x = stream - COST_GAP unless x2 is given)."""
    arr = np.asarray(x, dtype=float)
    arr2 = np.asarray(x2, dtype=float) if x2 is not None else arr - COST_GAP
    return {(h, m): band_series(key, a, horizon=h, mult=m, cur=cur, chal=chal)
            for h in (5, 63) for m, a in ((1.0, arr), (2.0, arr2))}


def make_evaluator(per_key: Dict[str, Any], default: Optional[Sequence[float]] = None):
    """Stand-in for marginal_band_evaluator.evaluate_key. per_key[key] is a stream, or {challenger: stream, "*": stream}
    (the band is identified by its challenger value); keys not listed use `default`, else an empty series."""
    def fake(engine, user_id, key, current, challenger, since=None):
        spec = per_key.get(key, default)
        if isinstance(spec, dict):
            spec = spec.get(float(challenger), spec.get("*"))
        return series_dict(key, [] if spec is None else spec, cur=current, chal=challenger)
    return fake


def flat_closes(n: int = 700, start: float = 100.0, drift: float = 0.0004):
    """Noise-free uptrend: SPY above its 200d mean and zero vol -> one regime cell 'up_lovol' every week."""
    return [start * (1 + drift) ** i for i in range(n)]


def closes_provider(n: int = 700):
    data = flat_closes(n)
    return lambda ticker, days=None: data if days is None else data[-days:]


NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 19)
