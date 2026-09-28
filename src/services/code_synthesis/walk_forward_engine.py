"""
Walk-Forward Analysis (WFA) & Monte Carlo Path Perturbation Engine
==================================================================
Provides institutional-grade empirical stress testing for synthesized alpha factors:
  1. Walk-Forward Analysis (WFA): Rolling In-Sample (IS) vs Out-of-Sample (OOS) slices
     evaluating Walk-Forward Efficiency (WFE >= 0.50) to reject overfitted factors.
  2. Monte Carlo Path Perturbation: 500+ bootstrap trade resamplings assessing
     95% confidence max drawdown (MDD_95 <= 25%) and profit probability (>= 80%).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("WalkForwardEngine")


@dataclass
class WalkForwardWindowResult:
    window_idx: int
    is_bars: int
    oos_bars: int
    is_return_pct: float
    is_sharpe: float
    is_mdd_pct: float
    oos_return_pct: float
    oos_sharpe: float
    oos_mdd_pct: float
    wfe: float


@dataclass
class WalkForwardAnalysisResult:
    passed: bool
    wfe: float
    avg_oos_sharpe: float
    avg_oos_return_pct: float
    oos_win_rate_pct: float
    windows: List[WalkForwardWindowResult] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"[{status}] WFE: {self.wfe:.2f}, OOS Sharpe: {self.avg_oos_sharpe:.2f}, "
            f"OOS Ret: {self.avg_oos_return_pct:.1f}%, OOS WinRate: {self.oos_win_rate_pct:.0f}%"
        )


@dataclass
class MonteCarloResult:
    passed: bool
    num_simulations: int
    mc_mdd_95: float
    mc_mdd_99: float
    mc_profit_prob: float
    median_return_pct: float
    failures: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"[{status}] MC MDD 95%: {self.mc_mdd_95:.1f}%, MDD 99%: {self.mc_mdd_99:.1f}%, "
            f"Profit Prob: {self.mc_profit_prob * 100:.1f}%, Median Ret: {self.median_return_pct:.1f}%"
        )


class WalkForwardEngine:
    """
    Evaluates factor robustness across rolling In-Sample (IS) and Out-of-Sample (OOS) slices.
    """
    MIN_WFE = 0.50
    MIN_AVG_OOS_SHARPE = 0.50
    MIN_OOS_WIN_RATE = 75.0  # At least 75% of OOS windows must have net profit > 0

    @staticmethod
    def _simulate_segment_trades(
        close_series: pd.Series,
        factor_series: pd.Series,
        entry_thresh: float,
        exit_thresh: float,
        initial_cash: float = 10000.0,
    ) -> Tuple[float, float, float, int]:
        """
        Simulate factor trades on a sub-segment and return (net_return_pct, sharpe, mdd_pct, total_trades).
        """
        if len(close_series) < 10:
            return 0.0, 0.0, 0.0, 0

        in_pos = False
        entry_p = 0.0
        cash = initial_cash
        equity = [initial_cash]
        trades = []

        for i in range(1, len(close_series)):
            c_price = float(close_series.iloc[i])
            prev_bar = close_series.index[i - 1]
            prev_f = factor_series.get(prev_bar, np.nan)

            if not in_pos:
                if not np.isnan(prev_f) and prev_f >= entry_thresh:
                    in_pos = True
                    entry_p = c_price
            else:
                pnl_pct = (c_price - entry_p) / entry_p * 100.0
                if (not np.isnan(prev_f) and prev_f <= exit_thresh) or pnl_pct <= -6.0:
                    trade_pnl = cash * (pnl_pct / 100.0)
                    cash += trade_pnl
                    trades.append(pnl_pct)
                    in_pos = False

            equity.append(cash if not in_pos else cash * (1.0 + (c_price - entry_p) / entry_p))

        if in_pos:
            final_pnl = (float(close_series.iloc[-1]) - entry_p) / entry_p * 100.0
            cash += cash * (final_pnl / 100.0)
            trades.append(final_pnl)

        net_ret = ((cash - initial_cash) / initial_cash) * 100.0
        eq_s = pd.Series(equity)
        peak = eq_s.cummax()
        mdd = abs(float(((eq_s - peak) / peak * 100.0).min()))

        ret_s = eq_s.pct_change().dropna()
        sharpe = float((ret_s.mean() / ret_s.std()) * np.sqrt(252)) if len(ret_s) > 1 and ret_s.std() > 0 else 0.0
        return net_ret, sharpe, mdd, len(trades)

    @classmethod
    def evaluate(
        cls,
        candidate_params: Dict[str, Any],
        factor_callable: Callable[[pd.DataFrame, Optional[dict]], pd.Series],
        df: pd.DataFrame,
        num_windows: int = 4,
        train_ratio: float = 0.65,
        entry_quantile: float = 0.70,
        exit_quantile: float = 0.30,
    ) -> WalkForwardAnalysisResult:
        """
        Runs Walk-Forward Analysis across rolling temporal windows.
        """
        n_bars = len(df)
        if n_bars < 50:
            return WalkForwardAnalysisResult(
                passed=False,
                wfe=0.0,
                avg_oos_sharpe=0.0,
                avg_oos_return_pct=0.0,
                oos_win_rate_pct=0.0,
                failures=["Data length too short for Walk-Forward Analysis (requires >= 50 bars)"],
            )

        # Pre-compute full factor series
        factor_series = factor_callable(df, candidate_params)
        clean_factors = factor_series.dropna()
        if len(clean_factors) < 30:
            return WalkForwardAnalysisResult(
                passed=False,
                wfe=0.0,
                avg_oos_sharpe=0.0,
                avg_oos_return_pct=0.0,
                oos_win_rate_pct=0.0,
                failures=["Factor series has excessive NaNs for Walk-Forward Analysis"],
            )

        entry_thresh = clean_factors.quantile(entry_quantile)
        exit_thresh = clean_factors.quantile(exit_quantile)

        # Compute sliding window sizes
        window_size = int(n_bars / (num_windows * (1.0 - train_ratio) + train_ratio))
        is_size = int(window_size * train_ratio)
        oos_size = window_size - is_size
        step = oos_size

        window_results: List[WalkForwardWindowResult] = []

        for w_idx in range(num_windows):
            start_idx = w_idx * step
            is_end_idx = start_idx + is_size
            oos_end_idx = min(n_bars, is_end_idx + oos_size)

            if is_end_idx >= n_bars or (oos_end_idx - is_end_idx) < 5:
                break

            df_is = df.iloc[start_idx:is_end_idx]
            df_oos = df.iloc[is_end_idx:oos_end_idx]

            is_ret, is_sharpe, is_mdd, _ = cls._simulate_segment_trades(
                df_is["Close"], factor_series, entry_thresh, exit_thresh
            )
            oos_ret, oos_sharpe, oos_mdd, _ = cls._simulate_segment_trades(
                df_oos["Close"], factor_series, entry_thresh, exit_thresh
            )

            # WFE per window
            wfe = (oos_ret / is_ret) if is_ret > 0 else (1.0 if oos_ret > 0 else 0.0)

            window_results.append(
                WalkForwardWindowResult(
                    window_idx=w_idx + 1,
                    is_bars=len(df_is),
                    oos_bars=len(df_oos),
                    is_return_pct=is_ret,
                    is_sharpe=is_sharpe,
                    is_mdd_pct=is_mdd,
                    oos_return_pct=oos_ret,
                    oos_sharpe=oos_sharpe,
                    oos_mdd_pct=oos_mdd,
                    wfe=wfe,
                )
            )

        if not window_results:
            return WalkForwardAnalysisResult(
                passed=False,
                wfe=0.0,
                avg_oos_sharpe=0.0,
                avg_oos_return_pct=0.0,
                oos_win_rate_pct=0.0,
                failures=["Failed to generate valid walk-forward windows"],
            )

        # Compute aggregate metrics
        mean_is_ret = float(np.mean([w.is_return_pct for w in window_results]))
        mean_oos_ret = float(np.mean([w.oos_return_pct for w in window_results]))
        avg_oos_sharpe = float(np.mean([w.oos_sharpe for w in window_results]))

        overall_wfe = (mean_oos_ret / mean_is_ret) if mean_is_ret > 0 else (1.0 if mean_oos_ret > 0 else 0.0)
        overall_wfe = max(0.0, round(overall_wfe, 4))

        profitable_oos = sum(1 for w in window_results if w.oos_return_pct > 0)
        oos_win_rate = (profitable_oos / len(window_results)) * 100.0

        failures = []
        if overall_wfe < cls.MIN_WFE:
            failures.append(
                f"Walk-Forward Efficiency {overall_wfe:.2f} is below minimum {cls.MIN_WFE:.2f} threshold (Overfitting Risk)"
            )
        if avg_oos_sharpe < cls.MIN_AVG_OOS_SHARPE:
            failures.append(
                f"Average Out-of-Sample Sharpe {avg_oos_sharpe:.2f} is below minimum {cls.MIN_AVG_OOS_SHARPE:.2f}"
            )
        if oos_win_rate < cls.MIN_OOS_WIN_RATE:
            failures.append(
                f"OOS Profitable Windows Rate {oos_win_rate:.0f}% is below required {cls.MIN_OOS_WIN_RATE:.0f}%"
            )

        passed = len(failures) == 0

        return WalkForwardAnalysisResult(
            passed=passed,
            wfe=overall_wfe,
            avg_oos_sharpe=round(avg_oos_sharpe, 2),
            avg_oos_return_pct=round(mean_oos_ret, 2),
            oos_win_rate_pct=round(oos_win_rate, 1),
            windows=window_results,
            failures=failures,
        )


class MonteCarloSimulator:
    """
    Performs trade resampling bootstrap to stress test maximum drawdown and path fragility.
    """
    MAX_MDD_95 = 25.0
    MIN_PROFIT_PROB = 0.80

    @classmethod
    def simulate_trade_paths(
        cls,
        trades: List[Dict[str, float]],
        initial_cash: float = 10000.0,
        num_simulations: int = 500,
        random_seed: int = 42,
    ) -> MonteCarloResult:
        """
        Bootstrap resamples realized trade sequences and derives confidence interval drawdowns.
        """
        if len(trades) < 4:
            return MonteCarloResult(
                passed=False,
                num_simulations=num_simulations,
                mc_mdd_95=0.0,
                mc_mdd_99=0.0,
                mc_profit_prob=0.0,
                median_return_pct=0.0,
                failures=["Insufficient trade sample for Monte Carlo simulation (minimum 4 trades required)"],
            )

        np.random.seed(random_seed)
        pnl_pcts = np.array([t.get("pnl_pct", 0.0) for t in trades])
        n_trades = len(pnl_pcts)

        simulated_mdds = []
        simulated_returns = []

        for _ in range(num_simulations):
            # Bootstrap sample trades with replacement
            sampled_pnls = np.random.choice(pnl_pcts, size=n_trades, replace=True)

            # Reconstruct equity curve
            cash = initial_cash
            equity_path = [cash]
            for p in sampled_pnls:
                cash += cash * (p / 100.0)
                equity_path.append(cash)

            eq_arr = np.array(equity_path)
            peak = np.maximum.accumulate(eq_arr)
            dd = (eq_arr - peak) / peak * 100.0
            max_dd = abs(float(np.min(dd)))

            final_ret = ((cash - initial_cash) / initial_cash) * 100.0
            simulated_mdds.append(max_dd)
            simulated_returns.append(final_ret)

        mc_mdd_95 = round(float(np.percentile(simulated_mdds, 95)), 2)
        mc_mdd_99 = round(float(np.percentile(simulated_mdds, 99)), 2)
        profit_prob = round(float(np.sum(np.array(simulated_returns) > 0) / num_simulations), 4)
        median_return = round(float(np.median(simulated_returns)), 2)

        failures = []
        if mc_mdd_95 > cls.MAX_MDD_95:
            failures.append(
                f"Monte Carlo 95% worst-case MDD {mc_mdd_95:.1f}% exceeds risk threshold {cls.MAX_MDD_95:.1f}%"
            )
        if profit_prob < cls.MIN_PROFIT_PROB:
            failures.append(
                f"Monte Carlo profit probability {profit_prob * 100:.1f}% is below {cls.MIN_PROFIT_PROB * 100:.1f}% requirement"
            )

        passed = len(failures) == 0

        return MonteCarloResult(
            passed=passed,
            num_simulations=num_simulations,
            mc_mdd_95=mc_mdd_95,
            mc_mdd_99=mc_mdd_99,
            mc_profit_prob=profit_prob,
            median_return_pct=median_return,
            failures=failures,
        )
