"""
Backtest risk/performance metrics — pure pandas/numpy, formulas reimplemented
from well-known definitions (the same ones freqtrade's data/metrics.py
implements; freqtrade is GPL-3.0 so its code is not copied, only the
standard formulas are reimplemented independently here).

回測績效指標：Sharpe/Sortino/Calmar/CAGR/最大回撤/期望值/獲利因子。
純 pandas/numpy 重寫標準公式（非複製 freqtrade 原始碼，僅參考公式定義）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


def sharpe_ratio(returns: List[float], risk_free: float = 0.0, periods_per_year: int = 252) -> Optional[float]:
    """Annualized Sharpe ratio from a series of periodic returns."""
    if not returns or len(returns) < 2:
        return None
    arr = np.array(returns, dtype=float)
    excess = arr - (risk_free / periods_per_year)
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return None
    return float(excess.mean() / std * np.sqrt(periods_per_year))


def sortino_ratio(returns: List[float], risk_free: float = 0.0, periods_per_year: int = 252) -> Optional[float]:
    """Annualized Sortino ratio — like Sharpe but penalizes only downside deviation."""
    if not returns or len(returns) < 2:
        return None
    arr = np.array(returns, dtype=float)
    excess = arr - (risk_free / periods_per_year)
    downside = excess[excess < 0]
    if len(downside) == 0:
        return None
    downside_std = downside.std(ddof=1) if len(downside) > 1 else abs(downside[0])
    if downside_std == 0 or np.isnan(downside_std):
        return None
    return float(excess.mean() / downside_std * np.sqrt(periods_per_year))


def max_drawdown(equity_curve: List[float]) -> Dict[str, object]:
    """
    Max drawdown (%) + the underwater series (drawdown at each point).
    Returns {"max_drawdown_pct": float, "underwater_pct": List[float]}.
    """
    if not equity_curve or len(equity_curve) < 2:
        return {"max_drawdown_pct": None, "underwater_pct": []}
    arr = np.array(equity_curve, dtype=float)
    running_max = np.maximum.accumulate(arr)
    # avoid div-by-zero if equity ever hits 0
    underwater = np.where(running_max > 0, (arr - running_max) / running_max * 100.0, 0.0)
    return {
        "max_drawdown_pct": float(underwater.min()),
        "underwater_pct": [round(float(v), 4) for v in underwater],
    }


def cagr(equity_curve: List[float], periods_per_year: int = 252) -> Optional[float]:
    """Compound annual growth rate (%) from an equity curve."""
    if not equity_curve or len(equity_curve) < 2 or equity_curve[0] <= 0:
        return None
    n_periods = len(equity_curve) - 1
    years = n_periods / periods_per_year
    if years <= 0:
        return None
    total_return = equity_curve[-1] / equity_curve[0]
    if total_return <= 0:
        return None
    return float((total_return ** (1 / years) - 1) * 100.0)


def calmar_ratio(equity_curve: List[float], periods_per_year: int = 252) -> Optional[float]:
    """CAGR / |max drawdown| — return per unit of worst-case pain."""
    growth = cagr(equity_curve, periods_per_year)
    dd = max_drawdown(equity_curve)["max_drawdown_pct"]
    if growth is None or dd is None or dd == 0:
        return None
    return float(growth / abs(dd))


def win_rate(trades: List[Dict]) -> Optional[float]:
    """Percentage of trades with pnl > 0."""
    closed = [t for t in trades if t.get("pnl") is not None]
    if not closed:
        return None
    wins = sum(1 for t in closed if t["pnl"] > 0)
    return float(wins / len(closed) * 100.0)


def expectancy(trades: List[Dict]) -> Optional[float]:
    """Average pnl per trade."""
    closed = [t["pnl"] for t in trades if t.get("pnl") is not None]
    if not closed:
        return None
    return float(np.mean(closed))


def profit_factor(trades: List[Dict]) -> Optional[float]:
    """Gross profit / gross loss. None if there are no losing trades (undefined/infinite)."""
    closed = [t["pnl"] for t in trades if t.get("pnl") is not None]
    if not closed:
        return None
    gross_profit = sum(p for p in closed if p > 0)
    gross_loss = abs(sum(p for p in closed if p < 0))
    if gross_loss == 0:
        return None
    return float(gross_profit / gross_loss)


def compute_all_metrics(equity_curve: List[float], trades: List[Dict],
                         periods_per_year: int = 252, risk_free: float = 0.0) -> Dict[str, object]:
    """Convenience: compute the full metrics bundle for a backtest run."""
    returns = []
    if equity_curve and len(equity_curve) > 1:
        arr = np.array(equity_curve, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            rets = np.diff(arr) / arr[:-1]
        returns = [float(r) for r in rets if not (np.isnan(r) or np.isinf(r))]

    dd = max_drawdown(equity_curve)
    return {
        "sharpe": sharpe_ratio(returns, risk_free, periods_per_year),
        "sortino": sortino_ratio(returns, risk_free, periods_per_year),
        "cagr_pct": cagr(equity_curve, periods_per_year),
        "calmar": calmar_ratio(equity_curve, periods_per_year),
        "max_drawdown_pct": dd["max_drawdown_pct"],
        "win_rate_pct": win_rate(trades),
        "expectancy": expectancy(trades),
        "profit_factor": profit_factor(trades),
        "total_trades": len([t for t in trades if t.get("pnl") is not None]),
    }
