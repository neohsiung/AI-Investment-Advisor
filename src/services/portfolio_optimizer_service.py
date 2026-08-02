"""
Portfolio optimization + risk model — ideas reimplemented from qlib
(qlib/contrib/strategy/optimizer/*.py, qlib/model/riskmodel/shrink.py — MIT
licensed). qlib's own engine/data-layer is NOT adopted; this is a standalone
cvxpy + scikit-learn implementation against this project's own price series.

Two additive pieces:
  - Ledoit-Wolf shrinkage covariance: a well-conditioned covariance estimate
    from a short return history (raw sample covariance is unstable/singular
    with few observations relative to the number of tickers).
  - Mean-variance weight optimizer: given expected returns (from factors/
    forecast) + the covariance above, solve for weights that maximize
    return for a risk budget, subject to long-only + fully-invested
    constraints (extendable with position limits later).

投組最佳化 + 風險模型：從 qlib 重寫核心公式（非移植其引擎/資料層）。
Ledoit-Wolf 收縮共變異數 + 均值-變異數最佳化，供 risk agent/再平衡使用。

Both functions degrade gracefully (return None) if cvxpy/scikit-learn are
not installed, or if there isn't enough data — never raises into callers.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def shrinkage_covariance(returns: Dict[str, List[float]]) -> Optional[np.ndarray]:
    """
    Ledoit-Wolf shrinkage covariance estimate from per-ticker daily return
    series. `returns` maps ticker -> list of daily returns (same length,
    aligned dates). Returns an (N, N) covariance matrix (ticker order =
    dict insertion order) or None if scikit-learn is unavailable or there
    isn't enough aligned history.
    """
    tickers = list(returns.keys())
    if len(tickers) < 2:
        return None
    lengths = {len(v) for v in returns.values()}
    if len(lengths) != 1 or min(lengths) < 20:
        logger.debug("shrinkage_covariance: insufficient/misaligned history, skipping")
        return None
    try:
        from sklearn.covariance import LedoitWolf
        matrix = np.array([returns[t] for t in tickers]).T  # (n_obs, n_tickers)
        lw = LedoitWolf().fit(matrix)
        return lw.covariance_
    except Exception as exc:
        logger.warning("shrinkage_covariance unavailable (%s); install scikit-learn to enable", exc)
        return None


def optimize_weights(
    tickers: List[str],
    expected_returns: List[float],
    covariance: np.ndarray,
    risk_aversion: float = 2.0,
    max_weight: float = 0.35,
) -> Optional[Dict[str, float]]:
    """
    Mean-variance optimization: maximize (expected_return - risk_aversion *
    variance) subject to long-only, fully-invested, and a per-position cap
    (default 35%, preventing concentration). Returns {ticker: weight} or
    None if cvxpy is unavailable or the problem doesn't solve.
    """
    n = len(tickers)
    if n == 0 or len(expected_returns) != n or covariance.shape != (n, n):
        return None
    try:
        import cvxpy as cp

        w = cp.Variable(n)
        mu = np.array(expected_returns)
        portfolio_return = mu @ w
        portfolio_variance = cp.quad_form(w, cp.psd_wrap(covariance))
        objective = cp.Maximize(portfolio_return - risk_aversion * portfolio_variance)
        constraints = [cp.sum(w) == 1, w >= 0, w <= max_weight]
        problem = cp.Problem(objective, constraints)
        problem.solve()

        if w.value is None:
            logger.warning("optimize_weights: solver did not converge")
            return None
        weights = {t: max(0.0, round(float(v), 6)) for t, v in zip(tickers, w.value)}
        total = sum(weights.values()) or 1.0
        return {t: round(v / total, 6) for t, v in weights.items()}
    except Exception as exc:
        logger.warning("optimize_weights unavailable (%s); install cvxpy to enable", exc)
        return None
