"""
TimesFM forecasting service — zero-shot price/return forecasting with a
calibrated quantile band.

Google Research's TimesFM 2.5 (200M params, Apache-2.0, torch backend) runs
locally on CPU/MPS — no training, no per-ticker fine-tuning, no API cost.
Loaded lazily as a process-wide singleton on first use (~1.5GB RAM once
loaded; the model weight downloads once to the HuggingFace cache on first
run). Feeds agents a FORWARD-looking signal (point forecast + q10-q90 band)
to complement the backward-looking indicators/factors they already get.

本地零樣本時間序列預測（TimesFM 2.5，Apache-2，torch，M3 可跑）。延遲載入
單例，補齊推演唯一的前瞻訊號。任何失敗（未裝 torch、模型下載失敗等）一律
回傳 None/空，呼叫方視為「預測不可用」，絕不阻塞既有流程。

NOT for the hot path: this is for scheduled/on-demand calls (momentum agent
context enrichment, daily Sentinel anomaly scan), never per-tick.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

_MODEL_ID = "google/timesfm-2.5-200m-pytorch"
_lock = threading.Lock()
_model = None  # process-wide singleton; None until first successful load
_load_attempted = False


@dataclass
class ForecastResult:
    ticker: str
    horizon: int
    point_forecast: List[float]       # length == horizon
    q10: List[float]
    q50: List[float]
    q90: List[float]
    last_price: float

    def band_width_pct(self, step: int = -1) -> Optional[float]:
        """Relative width of the q10-q90 band at a given horizon step (default: last)."""
        try:
            if not self.q10 or not self.q90 or self.last_price <= 0:
                return None
            return (self.q90[step] - self.q10[step]) / self.last_price * 100.0
        except Exception as e:
            logger.warning(f'Exception in forecast_service.py: {e}', exc_info=True)
            return None


def _get_model():
    """Lazily load + compile the TimesFM model once per process. Thread-safe."""
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
        except Exception as exc:
            logger.warning(
                "forecast_service: TimesFM unavailable (%s) — forecasts will "
                "be skipped. Install with `pip install timesfm[torch]` to enable.",
                exc,
            )
            _model = None
    return _model


def is_available() -> bool:
    """Cheap check without triggering a load — True only after a successful load."""
    return _model is not None


def forecast(ticker: str, closes: List[float], horizon: int = 5) -> Optional[ForecastResult]:
    """
    Zero-shot forecast for a single series of closing prices.

    Returns None if TimesFM isn't installed, the model fails to load, or the
    input series is too short — callers must treat None as "no forecast this
    run", never as an error to propagate.
    """
    if not closes or len(closes) < 10:
        return None
    model = _get_model()
    if model is None:
        return None
    try:
        import numpy as np
        point, quantiles = model.forecast(horizon=horizon, inputs=[np.array(closes, dtype=float)])
        # point: (1, horizon); quantiles: (1, horizon, 10) = [mean, q10..q90]
        point_list = point[0].tolist()
        q10 = quantiles[0, :, 1].tolist()   # index 1 = q10
        q50 = quantiles[0, :, 5].tolist()   # index 5 = q50 (median)
        q90 = quantiles[0, :, 9].tolist()   # index 9 = q90
        return ForecastResult(
            ticker=ticker, horizon=horizon, point_forecast=point_list,
            q10=q10, q50=q50, q90=q90, last_price=float(closes[-1]),
        )
    except Exception as exc:
        logger.warning("forecast(%s) failed: %s", ticker, exc)
        return None


def is_anomalous(current_price: float, forecast_result: ForecastResult, step: int = 0) -> Optional[bool]:
    """
    True if `current_price` falls outside the forecast's q10-q90 band at the
    given horizon step — a statistically unusual move worth flagging (used
    by Sentinel's polling scan, never per-event). None if undeterminable.
    """
    try:
        if not forecast_result or not forecast_result.q10 or not forecast_result.q90:
            return None
        return not (forecast_result.q10[step] <= current_price <= forecast_result.q90[step])
    except Exception as e:
        logger.warning(f'Exception in forecast_service.py: {e}', exc_info=True)
        return None
