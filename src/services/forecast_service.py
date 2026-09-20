"""
Short-horizon price forecasting with a calibrated quantile band.

Two implementations behind one interface:

1. **TimesFM 2.5** (Google Research, 200M params, Apache-2.0) — zero-shot, runs
   locally on CPU/MPS. Ships in the optional `forecast` extra because it drags
   in ~900MB of PyTorch; loaded lazily as a process-wide singleton (~1.5GB RSS
   once resident).

2. **Random-walk band** (numpy only, always available) — drift-damped geometric
   random walk with an EWMA volatility estimate. This is the honest baseline for
   daily equity prices at a 5-day horizon, and it is what the default install
   uses so `data["forecast"]` is populated without a 900MB dependency.

Which one is better is no longer an open question, and the answer is not the
one the dependency size suggests. Measured 2026-09-11 via
`scripts/backtest_forecast.py` (AAPL/NVDA/JPM, 120-day window, 5-day horizon,
235 forecast points each, prices from the project's own provider chain):

    method        q10-q90 coverage    mean pinball loss
    random_walk        0.821                1.8124
    timesfm            0.786                1.9135

The numpy baseline won on pinball loss for all three tickers and sat closer to
the nominal 0.80 coverage. TimesFM was not merely "not better" — it was worse,
while costing ~900MB of PyTorch and ~1.5GB of RSS.

Caveat, stated plainly: three tickers, one time period. This is not a definitive
study, but it is the only evidence that exists, and it points against the heavy
model. Re-run the script before promoting TimesFM back to a default.

NOT for the hot path: scheduled/on-demand calls only (agent context enrichment
on the daily/weekly path), never per-tick.

兩種實作、同一介面：TimesFM（選配 extra，~900MB torch）與 numpy 隨機漫步
分位帶（預設可用）。2026-09-11 實測：numpy 基準在三檔標的上的 pinball loss
全數優於 TimesFM（1.8124 vs 1.9135），覆蓋率也更接近名目 0.80。
樣本僅三檔、單一期間，但這是目前唯一的證據，且不支持那 900MB。
"""
from __future__ import annotations

import logging
import math
import os
import threading
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

_MODEL_ID = "google/timesfm-2.5-200m-pytorch"
_lock = threading.Lock()
_model = None          # process-wide singleton; None until first successful load
_load_attempted = False

# z-scores for the 10th/90th percentiles of a standard normal.
_Z90 = 1.2815515655446004

# Daily drift estimated from a few hundred observations is mostly noise at a
# 5-day horizon, and an unshrunk estimate tilts the whole band. Shrink hard.
_DRIFT_SHRINK = float(os.getenv("FORECAST_DRIFT_SHRINK", "0.20"))
# EWMA decay for the volatility estimate (~30-observation effective window).
_VOL_LAMBDA = float(os.getenv("FORECAST_VOL_LAMBDA", "0.94"))


@dataclass
class ForecastResult:
    ticker: str
    horizon: int
    point_forecast: List[float]       # length == horizon
    q10: List[float]
    q50: List[float]
    q90: List[float]
    last_price: float
    method: str = "unknown"           # "timesfm" | "random_walk"

    def band_width_pct(self, step: int = -1) -> Optional[float]:
        """Relative width of the q10-q90 band at a horizon step (default: last)."""
        try:
            if not self.q10 or not self.q90 or self.last_price <= 0:
                return None
            return (self.q90[step] - self.q10[step]) / self.last_price * 100.0
        except Exception as e:
            logger.warning(f"band_width_pct failed: {e}", exc_info=True)
            return None


def _get_model():
    """Lazily load + compile TimesFM once per process. Thread-safe."""
    global _model, _load_attempted
    if _model is not None:
        return _model
    with _lock:
        if _model is not None or _load_attempted:
            return _model
        _load_attempted = True
        try:
            import timesfm

            model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(_MODEL_ID)
            model.compile(timesfm.ForecastConfig(
                max_context=1024,
                max_horizon=64,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                fix_quantile_crossing=True,
            ))
            _model = model
            logger.info("forecast_service: TimesFM 2.5 loaded and compiled")
        except ImportError:
            logger.info(
                "forecast_service: TimesFM not installed (optional 'forecast' "
                "extra) — using the numpy random-walk band instead."
            )
            _model = None
        except Exception as exc:
            logger.warning(
                "forecast_service: TimesFM present but failed to load (%s) — "
                "falling back to the numpy random-walk band.", exc,
            )
            _model = None
    return _model


def _random_walk_forecast(ticker: str, closes: List[float], horizon: int) -> Optional[ForecastResult]:
    """
    Drift-damped geometric random walk with an EWMA volatility estimate.

    price(t+h) = last * exp(mu*h)
    band       = last * exp(mu*h ± z90 * sigma * sqrt(h))

    The sqrt(h) term is what makes the band widen with horizon; a flat band
    would understate uncertainty at the far end and is the usual way a naive
    implementation of this looks right and scores badly.
    """
    import numpy as np

    prices = np.asarray(closes, dtype=float)
    prices = prices[np.isfinite(prices) & (prices > 0)]
    if prices.size < 10:
        return None

    log_returns = np.diff(np.log(prices))
    if log_returns.size < 2:
        return None

    mu = float(np.mean(log_returns)) * _DRIFT_SHRINK

    # EWMA variance, most recent observation weighted highest.
    weights = _VOL_LAMBDA ** np.arange(log_returns.size - 1, -1, -1)
    weights /= weights.sum()
    var = float(np.sum(weights * (log_returns - np.mean(log_returns)) ** 2))
    sigma = math.sqrt(max(var, 1e-12))

    last = float(prices[-1])
    point, q10, q50, q90 = [], [], [], []
    for h in range(1, horizon + 1):
        centre = mu * h
        spread = _Z90 * sigma * math.sqrt(h)
        median = last * math.exp(centre)
        point.append(median)
        q50.append(median)
        q10.append(last * math.exp(centre - spread))
        q90.append(last * math.exp(centre + spread))

    return ForecastResult(
        ticker=ticker, horizon=horizon, point_forecast=point,
        q10=q10, q50=q50, q90=q90, last_price=last, method="random_walk",
    )


def _timesfm_forecast(ticker: str, closes: List[float], horizon: int) -> Optional[ForecastResult]:
    model = _get_model()
    if model is None:
        return None
    try:
        import numpy as np

        point, quantiles = model.forecast(horizon=horizon, inputs=[np.array(closes, dtype=float)])
        # point: (1, horizon); quantiles: (1, horizon, 10) = [mean, q10..q90]
        return ForecastResult(
            ticker=ticker,
            horizon=horizon,
            point_forecast=point[0].tolist(),
            q10=quantiles[0, :, 1].tolist(),
            q50=quantiles[0, :, 5].tolist(),
            q90=quantiles[0, :, 9].tolist(),
            last_price=float(closes[-1]),
            method="timesfm",
        )
    except Exception as exc:
        logger.warning("TimesFM forecast(%s) failed: %s", ticker, exc)
        return None


def forecast(ticker: str, closes: List[float], horizon: int = 5) -> Optional[ForecastResult]:
    """
    Forecast a series of closing prices.

    Prefers TimesFM when the `forecast` extra is installed; otherwise (or if the
    model fails) returns the numpy random-walk band. Returns None only when the
    input series is too short to say anything — callers treat None as "no
    forecast this run", never as an error to propagate.

    Set FORECAST_METHOD=random_walk to pin the baseline even when TimesFM is
    available (used by the backtest script to compare the two).
    """
    if not closes or len(closes) < 10:
        return None

    method = os.getenv("FORECAST_METHOD", "auto").strip().lower()
    if method != "random_walk":
        result = _timesfm_forecast(ticker, closes, horizon)
        if result is not None:
            return result

    return _random_walk_forecast(ticker, closes, horizon)
