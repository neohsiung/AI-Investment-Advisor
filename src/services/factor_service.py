"""
Alpha158-style factor library — pure pandas/numpy, no new dependencies.

Reimplements the core formula ideas from Microsoft qlib's Alpha158
(qlib/contrib/data/loader.py — MIT licensed): KBAR shape features, rolling
return/volatility/position factors, and price/volume ratios. qlib's own
engine (cython Ref/Rolling ops + its data layer) is NOT adopted — these are
plain pandas reimplementations against this project's own OHLCV shape
(`MarketDataService.get_ohlcv` -> {"date","open","high","low","close","volume"}).

Feeds momentum/fundamental agents a richer, deterministic factor snapshot
(zero LLM/API cost) instead of the previous handful of ad-hoc indicators
(RSI/MACD/SMA only, current-bar values). Additive: existing `indicators`
field is untouched; `factors` is a new field alongside it.

Alpha158 風格因子庫：純 pandas 重寫 qlib 核心公式（非移植其引擎/資料層），
零額外依賴、零成本，補齊動能/波動/量價因子的深度。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Windows used for rolling factors (days)
_WINDOWS = (5, 10, 20, 30, 60)


def _to_frame(ohlcv: Dict[str, List[Any]]) -> Optional[pd.DataFrame]:
    """Convert the get_ohlcv() dict shape into an indexed OHLCV DataFrame."""
    required = ("open", "high", "low", "close", "volume")
    if not ohlcv or not all(k in ohlcv for k in required):
        return None
    try:
        df = pd.DataFrame({
            "open": pd.to_numeric(pd.Series(ohlcv["open"]), errors="coerce"),
            "high": pd.to_numeric(pd.Series(ohlcv["high"]), errors="coerce"),
            "low": pd.to_numeric(pd.Series(ohlcv["low"]), errors="coerce"),
            "close": pd.to_numeric(pd.Series(ohlcv["close"]), errors="coerce"),
            "volume": pd.to_numeric(pd.Series(ohlcv["volume"]), errors="coerce"),
        })
        df = df.dropna(subset=["close"])
        return df if len(df) >= 2 else None
    except Exception as exc:
        logger.debug("factor_service: could not build frame (%s)", exc)
        return None


def compute_factors(ohlcv: Dict[str, List[Any]]) -> Dict[str, float]:
    """
    Compute an Alpha158-style factor snapshot (latest values) from an OHLCV
    dict. Returns {} if there isn't enough history — callers should treat an
    empty dict as "factors unavailable", never as a reason to fail.
    """
    df = _to_frame(ohlcv)
    if df is None:
        return {}

    out: Dict[str, float] = {}
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    n = len(df)

    def last(series: pd.Series) -> Optional[float]:
        val = series.iloc[-1]
        return None if pd.isna(val) else round(float(val), 6)

    # ── KBAR shape (qlib Alpha158 KBAR group) ────────────────────────
    c0, o0, h0, l0 = close.iloc[-1], open_.iloc[-1], high.iloc[-1], low.iloc[-1]
    rng = (h0 - l0) or np.nan
    out["kbar_body"] = _safe_round((c0 - o0) / o0) if o0 else None
    out["kbar_upper_shadow"] = _safe_round((h0 - max(o0, c0)) / rng) if rng else None
    out["kbar_lower_shadow"] = _safe_round((min(o0, c0) - l0) / rng) if rng else None
    out["kbar_range_pct"] = _safe_round((h0 - l0) / o0) if o0 else None

    # ── Rolling return / momentum (ROC) ──────────────────────────────
    for w in _WINDOWS:
        if n > w:
            out[f"roc_{w}d"] = _safe_round(close.iloc[-1] / close.iloc[-1 - w] - 1)
        else:
            out[f"roc_{w}d"] = None

    # ── Rolling volatility (std of daily returns) ────────────────────
    daily_ret = close.pct_change()
    for w in _WINDOWS:
        if n > w:
            out[f"std_{w}d"] = _safe_round(daily_ret.iloc[-w:].std())
        else:
            out[f"std_{w}d"] = None

    # ── Rolling price position (qlib RSV-style: 0=at low, 1=at high) ─
    for w in _WINDOWS:
        if n >= w:
            window_high = high.iloc[-w:].max()
            window_low = low.iloc[-w:].min()
            span = (window_high - window_low) or np.nan
            out[f"price_position_{w}d"] = _safe_round((c0 - window_low) / span) if span else None
        else:
            out[f"price_position_{w}d"] = None

    # ── Moving-average ratios (qlib MA group) ────────────────────────
    for w in _WINDOWS:
        if n >= w:
            ma = close.iloc[-w:].mean()
            out[f"ma_ratio_{w}d"] = _safe_round(c0 / ma - 1) if ma else None
        else:
            out[f"ma_ratio_{w}d"] = None

    # ── Volume factors ────────────────────────────────────────────────
    for w in _WINDOWS:
        if n >= w:
            avg_vol = volume.iloc[-w:].mean()
            out[f"volume_ratio_{w}d"] = _safe_round(volume.iloc[-1] / avg_vol) if avg_vol else None
        else:
            out[f"volume_ratio_{w}d"] = None

    # ── RSI (Wilder's, 14-period — kept for completeness alongside qlib-style factors)
    if n > 14:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] not in (0, None) and not pd.isna(loss.iloc[-1]) else None
        out["rsi_14"] = _safe_round(100 - (100 / (1 + rs))) if rs is not None else None
    else:
        out["rsi_14"] = None

    # Drop None entries — keep the payload compact for prompt injection.
    return {k: v for k, v in out.items() if v is not None}


def _safe_round(value, digits: int = 6) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            return None
        return round(float(value), digits)
    except Exception as e:
        logger.warning(f'Exception in factor_service.py: {e}', exc_info=True)
        return None
