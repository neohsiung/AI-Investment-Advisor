"""
Backtest Adapter for Synthesized Factor Validation
===================================================
將通過 AST 與沙盒 TDD 驗測的量化因子純函式，無縫接入歷史行情數據進行經驗回測，
並以 StrategyValidationService 之五大剛性指標進行客觀評定。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.services.code_synthesis.factor_synthesizer import (
    SynthesizedFactorCandidate,
)
from src.services.strategy_validation_service import (
    ValidationThresholds,
    evaluate_backtest,
)

logger = logging.getLogger("BacktestAdapter")


@dataclass
class BacktestValidationResult:
    """
    Backtest evaluation outcome for a synthesized factor.
    """
    passed: bool
    metrics: Dict[str, Any]
    failures: List[str] = field(default_factory=list)
    initial_cash: float = 10000.0
    final_cash: float = 10000.0
    buy_and_hold_return_pct: float = 0.0

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        sharpe = self.metrics.get("sharpe", 0.0)
        mdd = self.metrics.get("max_drawdown_pct", 0.0)
        ret = self.metrics.get("net_return_pct", 0.0)
        trades = self.metrics.get("total_trades", 0)
        return (
            f"[{status}] Sharpe: {sharpe:.2f}, MDD: {mdd:.1f}%, Return: {ret:.1f}%, "
            f"Trades: {trades}, Failures: {len(self.failures)}"
        )


class BacktestAdapter:
    """
    Runs an empirical simulation of a factor function against historical OHLCV data
    and assesses whether it passes the mandatory ValidationThresholds gate.
    """

    def __init__(self, initial_cash: float = 10000.0):
        self.initial_cash = initial_cash

    def backtest_factor(
        self,
        candidate: SynthesizedFactorCandidate,
        factor_callable: Callable[[pd.DataFrame, Optional[dict]], pd.Series],
        df: pd.DataFrame,
        entry_quantile: float = 0.70,
        exit_quantile: float = 0.30,
    ) -> BacktestValidationResult:
        """
        Execute backtest of factor signals on historical OHLCV DataFrame.
        """
        if df.empty or len(df) < 30 or "Close" not in df.columns:
            return BacktestValidationResult(
                passed=False,
                metrics={},
                failures=["Insufficient historical data (requires at least 30 bars with 'Close')"],
                initial_cash=self.initial_cash,
                final_cash=self.initial_cash,
            )

        # 1. 執行因子計算
        factor_values = factor_callable(df, candidate.parameters)
        if not isinstance(factor_values, pd.Series) or factor_values.empty:
            return BacktestValidationResult(
                passed=False,
                metrics={},
                failures=["Factor callable returned invalid or empty Series"],
                initial_cash=self.initial_cash,
                final_cash=self.initial_cash,
            )

        # 2. 模擬向量化與逐筆交易 (Trade Simulation)
        close = df["Close"]
        clean_factors = factor_values.dropna()
        if len(clean_factors) < 20:
            return BacktestValidationResult(
                passed=False,
                metrics={"total_trades": 0},
                failures=["Too many NaNs in factor series to evaluate trades"],
                initial_cash=self.initial_cash,
                final_cash=self.initial_cash,
            )

        entry_thresh = clean_factors.quantile(entry_quantile)
        exit_thresh = clean_factors.quantile(exit_quantile)

        in_position = False
        entry_price = 0.0
        cash = self.initial_cash
        trades: List[Dict[str, float]] = []
        equity_curve = [self.initial_cash]

        for i in range(1, len(df)):
            current_bar = df.index[i]
            prev_bar = df.index[i - 1]
            c_price = float(close.iloc[i])
            prev_factor = factor_values.get(prev_bar, np.nan)

            if not in_position:
                if not np.isnan(prev_factor) and prev_factor >= entry_thresh:
                    in_position = True
                    entry_price = c_price
            else:
                # 檢查出場條件 (Factor 轉弱或達到 6% 停損)
                pnl_pct = (c_price - entry_price) / entry_price * 100.0
                if (not np.isnan(prev_factor) and prev_factor <= exit_thresh) or pnl_pct <= -6.0:
                    trade_pnl = cash * (pnl_pct / 100.0)
                    cash += trade_pnl
                    trades.append({"pnl_pct": pnl_pct, "pnl": trade_pnl})
                    in_position = False

            equity_curve.append(cash if not in_position else cash * (1.0 + (c_price - entry_price) / entry_price))

        # 若回測結束仍有持倉，以最後收盤價結算
        if in_position:
            final_pnl_pct = (float(close.iloc[-1]) - entry_price) / entry_price * 100.0
            trade_pnl = cash * (final_pnl_pct / 100.0)
            cash += trade_pnl
            trades.append({"pnl_pct": final_pnl_pct, "pnl": trade_pnl})

        # 3. 計算回測指標
        total_trades = len(trades)
        net_return_pct = ((cash - self.initial_cash) / self.initial_cash) * 100.0
        bnh_return_pct = ((float(close.iloc[-1]) - float(close.iloc[0])) / float(close.iloc[0])) * 100.0

        # 計算最大回撤 (Max Drawdown)
        eq_series = pd.Series(equity_curve)
        peak = eq_series.cummax()
        drawdown_series = (eq_series - peak) / peak * 100.0
        max_drawdown_pct = abs(float(drawdown_series.min()))

        # 計算夏普比率 (Sharpe Ratio)
        returns = eq_series.pct_change().dropna()
        if len(returns) > 1 and returns.std() > 0:
            sharpe = float((returns.mean() / returns.std()) * np.sqrt(252))
        else:
            sharpe = 0.0

        win_trades = sum(1 for t in trades if t["pnl"] > 0)
        win_rate = (win_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        metrics = {
            "sharpe": sharpe,
            "max_drawdown_pct": max_drawdown_pct,
            "net_return_pct": net_return_pct,
            "total_trades": total_trades,
            "win_rate": win_rate,
        }

        # 4. 嚴格對標 StrategyValidationService 五大剛性指標
        passed, failures = evaluate_backtest(
            metrics=metrics,
            initial_cash=self.initial_cash,
            final_cash=cash,
            buy_and_hold_return_pct=bnh_return_pct,
            thresholds=ValidationThresholds,
        )

        return BacktestValidationResult(
            passed=passed,
            metrics=metrics,
            failures=failures,
            initial_cash=self.initial_cash,
            final_cash=cash,
            buy_and_hold_return_pct=bnh_return_pct,
        )
