"""
Multi-Asset Adaptive Portfolio Backtest Engine
多標的自適應投組回測驗證與動態部位定價引擎
=============================================================================
Comprehensive bar-by-bar multi-asset backtester integrating:
1. M1: Inverse-volatility risk parity weighting, regime cash buffer, target volatility dampening.
2. M2: 60-day rolling correlation clustering, cluster cap (<=30%), portfolio beta dampening.
3. M3: Holding tenure tracking, 20-day grace period, winner compound protection,
       exponential alpha decay for stagnant holdings, roundtrip friction & opportunity cost hurdle.
4. M4: Dynamic fractional Kelly sizing adjustment.
5. Benchmark comparison & parametric sensitivity analysis.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.services.kelly_sizing_service import KellyAssessment, KellySizingService
from src.services.metrics_service import compute_all_metrics

logger = logging.getLogger(__name__)


@dataclass
class BacktestTradeRecord:
    """Detailed record of an executed trade in the multi-asset simulation."""
    ticker: str
    action: str  # "BUY", "SELL", "TRIM", "ADD"
    date: str
    price: float
    quantity: float
    notional: float
    fee: float
    slippage: float
    pnl: float | None = None
    pnl_pct: float | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "action": self.action,
            "date": self.date,
            "price": round(self.price, 4),
            "quantity": round(self.quantity, 4),
            "notional": round(self.notional, 4),
            "fee": round(self.fee, 4),
            "slippage": round(self.slippage, 4),
            "pnl": round(self.pnl, 4) if self.pnl is not None else None,
            "pnl_pct": round(self.pnl_pct, 4) if self.pnl_pct is not None else None,
            "reason": self.reason,
        }


@dataclass
class MultiAssetBacktestResult:
    """Outcome of multi-asset portfolio backtest run."""
    dates: list[str] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    cash_curve: list[float] = field(default_factory=list)
    positions_history: list[dict[str, float]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    comparison_summary: dict[str, Any] = field(default_factory=dict)
    friction_saved: float = 0.0
    total_friction_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dates": self.dates,
            "equity_curve": [round(x, 2) for x in self.equity_curve],
            "cash_curve": [round(x, 2) for x in self.cash_curve],
            "positions_history": self.positions_history,
            "trades": self.trades,
            "metrics": self.metrics,
            "baseline_metrics": self.baseline_metrics,
            "comparison_summary": self.comparison_summary,
            "friction_saved": round(self.friction_saved, 2),
            "total_friction_cost": round(self.total_friction_cost, 2),
        }


class MultiAssetPortfolioBacktestEngine:
    """
    Event-driven multi-asset portfolio backtest engine supporting M1~M4 algorithmic suite.
    多標的自適應投組量化回測引擎。
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        fee_pct: float = 0.001,
        slippage_pct: float = 0.0005,
        rebalance_interval_days: int = 5,
        enable_m1_volatility_parity: bool = True,
        enable_m2_correlation_clusters: bool = True,
        enable_m3_alpha_decay: bool = True,
        enable_m3_opportunity_cost: bool = True,
        enable_m4_kelly_sizing: bool = True,
        target_volatility: float = 0.14,
        target_beta: float = 0.90,
        cluster_cap: float = 0.30,
        correlation_threshold: float = 0.70,
        min_position_pct: float = 0.02,
        max_position_pct: float = 0.20,
        holding_decay_start_days: int = 20,
        rotation_friction_multiplier: float = 2.5,
        rotation_hurdle_rate: float = 0.010,
        kelly_fraction: float = 0.25,
        kelly_min_trades: int = 10,
    ):
        self.initial_cash = initial_cash
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.rebalance_interval_days = max(1, rebalance_interval_days)
        self.enable_m1_volatility_parity = enable_m1_volatility_parity
        self.enable_m2_correlation_clusters = enable_m2_correlation_clusters
        self.enable_m3_alpha_decay = enable_m3_alpha_decay
        self.enable_m3_opportunity_cost = enable_m3_opportunity_cost
        self.enable_m4_kelly_sizing = enable_m4_kelly_sizing
        self.target_volatility = target_volatility
        self.target_beta = target_beta
        self.cluster_cap = cluster_cap
        self.correlation_threshold = correlation_threshold
        self.min_position_pct = min_position_pct
        self.max_position_pct = max_position_pct
        self.holding_decay_start_days = holding_decay_start_days
        self.rotation_friction_multiplier = rotation_friction_multiplier
        self.rotation_hurdle_rate = rotation_hurdle_rate
        self.kelly_fraction = kelly_fraction
        self.kelly_min_trades = kelly_min_trades

    def run(
        self,
        market_data: dict[str, dict[str, list[Any]]],
        benchmark_ticker: str = "SPY",
        research_signals: dict[str, dict[str, Any]] | None = None,
    ) -> MultiAssetBacktestResult:
        """
        Execute multi-asset bar-by-bar portfolio simulation over aligned chronological dates.
        """
        all_tickers = [t for t in market_data if t != benchmark_ticker]
        if not all_tickers:
            return MultiAssetBacktestResult(equity_curve=[self.initial_cash], cash_curve=[self.initial_cash])

        # Align chronological date index
        dates_set = set()
        for t, data in market_data.items():
            for d in data.get("date", []):
                dates_set.add(str(d))

        all_dates = sorted(dates_set)
        if len(all_dates) < 5:
            return MultiAssetBacktestResult(equity_curve=[self.initial_cash], cash_curve=[self.initial_cash])

        # Build date -> price lookup for quick access
        price_by_ticker_date: dict[str, dict[str, float]] = {}
        for t, data in market_data.items():
            d_list = data.get("date", [])
            c_list = data.get("close", [])
            price_by_ticker_date[t] = {
                str(d): float(c) for d, c in zip(d_list, c_list) if c is not None and not math.isnan(float(c))
            }

        # Initialize simulation state
        cash = self.initial_cash
        # holdings: ticker -> {"quantity": float, "entry_price": float, "entry_date": str, "holding_days": int, "peak_price": float}
        holdings: dict[str, dict[str, Any]] = {}
        trades: list[BacktestTradeRecord] = []
        closed_trades: list[dict[str, Any]] = []
        equity_curve: list[float] = []
        cash_curve: list[float] = []
        positions_history: list[dict[str, float]] = []

        total_friction_cost = 0.0
        friction_saved = 0.0
        last_rebalance_idx = -self.rebalance_interval_days

        # Initialize Kelly sizing helper
        kelly_service = KellySizingService()

        # Bar-by-bar daily loop
        for bar_idx, date in enumerate(all_dates):
            # 1. Update holding tenure and peak prices
            for ticker, pos in holdings.items():
                curr_price = price_by_ticker_date.get(ticker, {}).get(date)
                if curr_price is not None and curr_price > 0:
                    pos["holding_days"] += 1
                    pos["peak_price"] = max(pos["peak_price"], curr_price)

            # 2. Mark to market calculation
            portfolio_val = cash
            curr_prices: dict[str, float] = {}
            for ticker, pos in holdings.items():
                p = price_by_ticker_date.get(ticker, {}).get(date)
                if p is None or p <= 0:
                    p = pos["entry_price"]
                curr_prices[ticker] = p
                portfolio_val += pos["quantity"] * p

            equity_curve.append(round(portfolio_val, 4))
            cash_curve.append(round(cash, 4))

            # Record current weights
            current_weights: dict[str, float] = {}
            if portfolio_val > 0:
                for ticker, pos in holdings.items():
                    current_weights[ticker] = (pos["quantity"] * curr_prices.get(ticker, pos["entry_price"])) / portfolio_val
            positions_history.append(current_weights)

            # 3. Check Rebalance Trigger
            is_rebalance_day = (bar_idx - last_rebalance_idx) >= self.rebalance_interval_days
            # Warm-up requirement: need at least 20 bars of history
            if is_rebalance_day and bar_idx >= 20:
                last_rebalance_idx = bar_idx

                # Compute historical return series for active tickers up to date
                returns_map: dict[str, list[float]] = {}
                vols_map: dict[str, float] = {}
                sma20_map: dict[str, float] = {}

                # Benchmark returns for regime and beta
                spy_prices = [
                    price_by_ticker_date.get(benchmark_ticker, {}).get(d)
                    for d in all_dates[:bar_idx + 1]
                    if price_by_ticker_date.get(benchmark_ticker, {}).get(d) is not None
                ]
                spy_rets: list[float] = []
                if len(spy_prices) >= 2:
                    spy_rets = [
                        (spy_prices[k] - spy_prices[k - 1]) / spy_prices[k - 1]
                        for k in range(1, len(spy_prices))
                    ]

                # Market Regime determination
                regime_cash_ratio = 0.20  # Neutral default
                allow_new_buys = True
                if len(spy_prices) >= 60:
                    spy_60d_ret = (spy_prices[-1] / spy_prices[-60]) - 1.0
                    if spy_60d_ret < -0.05:
                        regime_cash_ratio = 0.50  # Bear Crisis defense
                        allow_new_buys = False
                    elif spy_60d_ret > 0.05:
                        regime_cash_ratio = 0.05  # Bull Trend defense
                    else:
                        regime_cash_ratio = 0.20

                # Per-ticker metrics
                for t in all_tickers:
                    hist_prices = [
                        price_by_ticker_date.get(t, {}).get(d)
                        for d in all_dates[:bar_idx + 1]
                        if price_by_ticker_date.get(t, {}).get(d) is not None
                    ]
                    if len(hist_prices) >= 10:
                        rets = [
                            (hist_prices[k] - hist_prices[k - 1]) / hist_prices[k - 1]
                            for k in range(1, len(hist_prices))
                        ]
                        returns_map[t] = rets[-60:]
                        std = float(np.std(rets[-60:], ddof=1)) if len(rets) >= 5 else 0.02
                        vols_map[t] = round(max(0.10, std * math.sqrt(252)), 4)
                        sma20_map[t] = sum(hist_prices[-20:]) / len(hist_prices[-20:])
                    else:
                        vols_map[t] = 0.25
                        sma20_map[t] = hist_prices[-1] if hist_prices else 100.0

                # Calculate Betas
                betas_map: dict[str, float] = {}
                for t in all_tickers:
                    r_t = returns_map.get(t, [])
                    if len(r_t) >= 10 and len(spy_rets) >= 10:
                        min_l = min(len(r_t), len(spy_rets))
                        y = np.array(r_t[-min_l:], dtype=float)
                        x = np.array(spy_rets[-min_l:], dtype=float)
                        var_x = float(np.var(x, ddof=1))
                        if var_x > 1e-7:
                            cov = float(np.cov(y, x, ddof=1)[0, 1])
                            betas_map[t] = round(max(0.1, min(3.0, cov / var_x)), 4)
                        else:
                            betas_map[t] = 1.0
                    else:
                        betas_map[t] = 1.0

                # M3 Alpha Decay evaluation for holdings
                decay_factors: dict[str, float] = {}
                for t in all_tickers:
                    if t in holdings and self.enable_m3_alpha_decay:
                        pos = holdings[t]
                        holding_days = pos["holding_days"]
                        entry_price = pos["entry_price"]
                        p_now = curr_prices.get(t, entry_price)
                        ret_since_entry = (p_now / entry_price) - 1.0 if entry_price > 0 else 0.0

                        # Benchmark return since entry
                        spy_entry = price_by_ticker_date.get(benchmark_ticker, {}).get(pos["entry_date"], 1.0)
                        spy_now = price_by_ticker_date.get(benchmark_ticker, {}).get(date, 1.0)
                        spy_ret_since_entry = (spy_now / spy_entry) - 1.0 if spy_entry > 0 else 0.0

                        sma_20 = sma20_map.get(t, p_now)
                        # Winner Compound Protection
                        is_compound_winner = (p_now >= sma_20) and (ret_since_entry >= spy_ret_since_entry)

                        if holding_days > self.holding_decay_start_days and not is_compound_winner:
                            decay = math.exp(-0.035 * (holding_days - self.holding_decay_start_days))
                            decay_factors[t] = max(0.40, decay)
                        else:
                            decay_factors[t] = 1.0
                    else:
                        decay_factors[t] = 1.0

                # Conviction and Base Scores
                scores_map: dict[str, float] = {}
                for t in all_tickers:
                    p_now = price_by_ticker_date.get(t, {}).get(date)
                    if p_now is None or p_now <= 0:
                        continue
                    if research_signals and t in research_signals:
                        sig = research_signals[t]
                        conf = float(sig.get("confidence", 0.70))
                        exp_ret = float(sig.get("expected_return", 0.08))
                    else:
                        conf = 0.70
                        exp_ret = 0.08

                    decay = decay_factors.get(t, 1.0)
                    scores_map[t] = conf * (1.0 + exp_ret) * decay

                if not scores_map:
                    continue

                # M1: Inverse-Volatility Risk Parity raw weights
                numerators: dict[str, float] = {}
                for t, score in scores_map.items():
                    vol = vols_map.get(t, 0.25)
                    if self.enable_m1_volatility_parity:
                        numerators[t] = score / vol
                    else:
                        numerators[t] = score

                total_num = sum(numerators.values())
                if total_num <= 0:
                    continue

                raw_weights = {t: n / total_num for t, n in numerators.items()}

                # M2: High Correlation Clustering
                clusters: list[list[str]] = []
                corr_matrix: dict[str, dict[str, float]] = {}
                active_cand = list(raw_weights.keys())

                if self.enable_m2_correlation_clusters and len(active_cand) > 1:
                    adj: dict[str, set[str]] = {t: set() for t in active_cand}
                    for i in range(len(active_cand)):
                        t_i = active_cand[i]
                        corr_matrix[t_i] = {t_i: 1.0}
                        r_i = returns_map.get(t_i, [])
                        for j in range(i + 1, len(active_cand)):
                            t_j = active_cand[j]
                            r_j = returns_map.get(t_j, [])
                            corr = 0.40
                            if len(r_i) >= 10 and len(r_j) >= 10:
                                min_l = min(len(r_i), len(r_j))
                                arr_i = np.array(r_i[-min_l:], dtype=float)
                                arr_j = np.array(r_j[-min_l:], dtype=float)
                                std_i = float(np.std(arr_i, ddof=1))
                                std_j = float(np.std(arr_j, ddof=1))
                                if std_i > 1e-6 and std_j > 1e-6:
                                    c = float(np.corrcoef(arr_i, arr_j)[0, 1])
                                    if not np.isnan(c):
                                        corr = max(-1.0, min(1.0, c))
                            corr_matrix[t_i][t_j] = corr
                            corr_matrix.setdefault(t_j, {})[t_i] = corr
                            if corr >= self.correlation_threshold:
                                adj[t_i].add(t_j)
                                adj[t_j].add(t_i)

                    visited = set()
                    for t in active_cand:
                        if t not in visited:
                            comp = []
                            q = [t]
                            visited.add(t)
                            while q:
                                curr = q.pop(0)
                                comp.append(curr)
                                for nbr in sorted(adj.get(curr, [])):
                                    if nbr not in visited:
                                        visited.add(nbr)
                                        q.append(nbr)
                            clusters.append(comp)

                    # Apply cluster cap
                    capped_weights = dict(raw_weights)
                    for cl in clusters:
                        if len(cl) > 1:
                            cl_sum = sum(capped_weights.get(t, 0.0) for t in cl)
                            if cl_sum > self.cluster_cap and cl_sum > 0:
                                scale_ratio = self.cluster_cap / cl_sum
                                for t in cl:
                                    capped_weights[t] = capped_weights[t] * scale_ratio
                    raw_weights = capped_weights

                # Normalize preliminary weights to 1.0 for risk scaling
                sum_w = sum(raw_weights.values())
                if sum_w <= 0:
                    continue
                prelim_weights = {t: w / sum_w for t, w in raw_weights.items()}

                # Estimate portfolio annualized volatility & beta
                port_var = 0.0
                cand_list = list(prelim_weights.keys())
                for i, t_i in enumerate(cand_list):
                    w_i = prelim_weights[t_i]
                    v_i = vols_map.get(t_i, 0.25)
                    port_var += (w_i * v_i) ** 2
                    for j in range(i + 1, len(cand_list)):
                        t_j = cand_list[j]
                        w_j = prelim_weights[t_j]
                        v_j = vols_map.get(t_j, 0.25)
                        pair_c = corr_matrix.get(t_i, {}).get(t_j, 0.40)
                        port_var += 2.0 * w_i * w_j * pair_c * v_i * v_j
                port_vol = math.sqrt(max(0.0, port_var))

                port_beta = sum(prelim_weights[t] * betas_map.get(t, 1.0) for t in cand_list)

                # M1 & M2 Risk Scaling Factors
                vol_scale = 1.0
                if self.enable_m1_volatility_parity and self.target_volatility > 0 and port_vol > self.target_volatility:
                    vol_scale = min(1.0, self.target_volatility / port_vol)

                beta_scale = 1.0
                if self.enable_m2_correlation_clusters and self.target_beta > 0 and port_beta > self.target_beta:
                    beta_scale = min(1.0, self.target_beta / port_beta)

                effective_scale = min(vol_scale, beta_scale)
                target_equity_fraction = (1.0 - regime_cash_ratio) * effective_scale

                # M4: Kelly Sizing Assessment
                kelly_assessments: dict[str, KellyAssessment] = {}
                if self.enable_m4_kelly_sizing and closed_trades:
                    # Rolling Kelly calculation based on closed trades up to now
                    recent_trades = closed_trades[-50:]
                    k_eval = kelly_service.calculate_from_trades(recent_trades)
                    for t in cand_list:
                        kelly_assessments[t] = k_eval

                # Determine final target weights per ticker
                target_weights: dict[str, float] = {}
                for t, w in prelim_weights.items():
                    target_w = w * target_equity_fraction
                    # Clamp by min and max position bounds
                    target_w = min(self.max_position_pct, target_w)

                    # Kelly constraint
                    if t in kelly_assessments:
                        rec_k = kelly_assessments[t].recommended_size
                        if rec_k > 0:
                            target_w = min(target_w, rec_k)

                    if target_w < self.min_position_pct:
                        target_w = 0.0
                    target_weights[t] = target_w

                # M3 Opportunity Cost Hurdle & Rebalance Execution
                roundtrip_friction = 2.0 * (self.fee_pct + self.slippage_pct)
                hurdle = (
                    self.rotation_friction_multiplier * roundtrip_friction + self.rotation_hurdle_rate
                    if self.enable_m3_opportunity_cost
                    else 0.001
                )

                # Evaluate sells / trims first to liberate cash
                all_sim_tickers = set(list(holdings.keys()) + list(target_weights.keys()))
                for t in sorted(all_sim_tickers):
                    target_w = target_weights.get(t, 0.0)
                    curr_w = current_weights.get(t, 0.0)
                    delta_w = target_w - curr_w
                    p_now = price_by_ticker_date.get(t, {}).get(date, curr_prices.get(t, 0.0))
                    if p_now <= 0:
                        continue

                    # Sell / Trim logic
                    if delta_w < 0 and t in holdings:
                        pos = holdings[t]
                        # If closing whole position (target_w == 0) or significant trim exceeding hurdle
                        if target_w == 0.0 or abs(delta_w) >= hurdle:
                            target_val = portfolio_val * target_w
                            curr_val = pos["quantity"] * p_now
                            trim_val = curr_val - target_val
                            trim_qty = min(pos["quantity"], trim_val / p_now)

                            if trim_qty > 0:
                                fill_price = p_now * (1.0 - self.slippage_pct)
                                fee = trim_qty * fill_price * self.fee_pct
                                proceeds = (trim_qty * fill_price) - fee
                                trade_pnl = proceeds - (trim_qty * pos["entry_price"])
                                trade_pnl_pct = ((fill_price / pos["entry_price"]) - 1.0) * 100.0

                                cash += proceeds
                                total_friction_cost += fee + (trim_qty * p_now * self.slippage_pct)

                                is_full_exit = (trim_qty >= pos["quantity"] - 1e-5) or (target_w == 0.0)
                                action = "SELL" if is_full_exit else "TRIM"

                                trade_record = BacktestTradeRecord(
                                    ticker=t,
                                    action=action,
                                    date=date,
                                    price=fill_price,
                                    quantity=trim_qty,
                                    notional=proceeds,
                                    fee=fee,
                                    slippage=trim_qty * p_now * self.slippage_pct,
                                    pnl=trade_pnl,
                                    pnl_pct=trade_pnl_pct,
                                    reason=f"Target weight adjusted to {target_w:.1%}",
                                )
                                trades.append(trade_record)
                                closed_trades.append(trade_record.to_dict())

                                if is_full_exit:
                                    del holdings[t]
                                else:
                                    pos["quantity"] -= trim_qty
                        else:
                            # Hurdle protected: friction saved
                            friction_saved += abs(delta_w) * portfolio_val * roundtrip_friction

                # Evaluate buys / additions with available cash
                for t in sorted(all_sim_tickers):
                    target_w = target_weights.get(t, 0.0)
                    curr_w = current_weights.get(t, 0.0)
                    delta_w = target_w - curr_w
                    p_now = price_by_ticker_date.get(t, {}).get(date, curr_prices.get(t, 0.0))
                    if p_now <= 0:
                        continue

                    if delta_w > 0:
                        # In Bear Crisis, if allow_new_buys is False and ticker is not already held, skip
                        if not allow_new_buys and t not in holdings:
                            continue

                        # Check opportunity cost hurdle
                        if delta_w >= hurdle:
                            target_add_val = min(portfolio_val * delta_w, cash * 0.98)
                            if target_add_val > 10.0:
                                fill_price = p_now * (1.0 + self.slippage_pct)
                                fee_rate = self.fee_pct
                                buy_qty = target_add_val / (fill_price * (1.0 + fee_rate))
                                if buy_qty > 0:
                                    fee = buy_qty * fill_price * fee_rate
                                    total_cost = (buy_qty * fill_price) + fee
                                    cash -= total_cost
                                    total_friction_cost += fee + (buy_qty * p_now * self.slippage_pct)

                                    if t in holdings:
                                        # Blended price update
                                        old_pos = holdings[t]
                                        new_total_qty = old_pos["quantity"] + buy_qty
                                        blended_price = (
                                            (old_pos["quantity"] * old_pos["entry_price"]) + (buy_qty * fill_price)
                                        ) / new_total_qty
                                        old_pos["quantity"] = new_total_qty
                                        old_pos["entry_price"] = blended_price
                                        action = "ADD"
                                    else:
                                        holdings[t] = {
                                            "quantity": buy_qty,
                                            "entry_price": fill_price,
                                            "entry_date": date,
                                            "holding_days": 0,
                                            "peak_price": fill_price,
                                        }
                                        action = "BUY"

                                    trades.append(BacktestTradeRecord(
                                        ticker=t,
                                        action=action,
                                        date=date,
                                        price=fill_price,
                                        quantity=buy_qty,
                                        notional=total_cost,
                                        fee=fee,
                                        slippage=buy_qty * p_now * self.slippage_pct,
                                        reason=f"Target weight increased to {target_w:.1%}",
                                    ))
                        else:
                            friction_saved += delta_w * portfolio_val * roundtrip_friction

        # Simulation completed: calculate comprehensive metrics
        trade_dicts = [t.to_dict() for t in trades]
        metrics = compute_all_metrics(equity_curve, trade_dicts)

        # Calculate Turnover rate: total traded volume / average portfolio equity
        total_traded_volume = sum(t["notional"] for t in trade_dicts)
        avg_equity = float(np.mean(equity_curve)) if equity_curve else self.initial_cash
        turnover_rate = (total_traded_volume / avg_equity) if avg_equity > 0 else 0.0

        # Calculate Annualized Volatility
        returns = []
        if len(equity_curve) > 1:
            arr = np.array(equity_curve, dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                rets = np.diff(arr) / arr[:-1]
            returns = [float(r) for r in rets if not (np.isnan(r) or np.isinf(r))]

        ann_vol = float(np.std(returns, ddof=1) * math.sqrt(252) * 100.0) if len(returns) >= 2 else 0.0

        metrics["annualized_volatility_pct"] = round(ann_vol, 2)
        metrics["turnover_rate"] = round(turnover_rate, 4)
        metrics["total_friction_cost"] = round(total_friction_cost, 2)
        metrics["friction_saved"] = round(friction_saved, 2)

        # Baseline Strategy: Equal-Weight Buy & Hold over the exact same time window
        baseline_result = self._run_baseline_equal_weight(
            all_tickers=all_tickers,
            all_dates=all_dates,
            price_by_ticker_date=price_by_ticker_date,
        )

        comparison = {
            "cagr_delta_pct": round((metrics.get("cagr_pct") or 0.0) - (baseline_result.get("cagr_pct") or 0.0), 2),
            "sharpe_delta": round((metrics.get("sharpe") or 0.0) - (baseline_result.get("sharpe") or 0.0), 3),
            "mdd_reduction_pct": round(
                abs(baseline_result.get("max_drawdown_pct") or 0.0) - abs(metrics.get("max_drawdown_pct") or 0.0),
                2,
            ),
            "calmar_delta": round((metrics.get("calmar") or 0.0) - (baseline_result.get("calmar") or 0.0), 3),
            "friction_saved_usd": round(friction_saved, 2),
        }

        return MultiAssetBacktestResult(
            dates=all_dates,
            equity_curve=equity_curve,
            cash_curve=cash_curve,
            positions_history=positions_history,
            trades=trade_dicts,
            metrics=metrics,
            baseline_metrics=baseline_result,
            comparison_summary=comparison,
            friction_saved=round(friction_saved, 2),
            total_friction_cost=round(total_friction_cost, 2),
        )

    def _run_baseline_equal_weight(
        self,
        all_tickers: list[str],
        all_dates: list[str],
        price_by_ticker_date: dict[str, dict[str, float]],
    ) -> dict[str, Any]:
        """
        Run static Equal-Weight Buy & Hold baseline on identical dates and tickers.
        """
        if not all_tickers or len(all_dates) < 2:
            return {}

        n_assets = len(all_tickers)
        alloc_per_asset = (self.initial_cash * 0.95) / n_assets
        initial_date = all_dates[0]

        # Initial buy allocations
        baseline_shares: dict[str, float] = {}
        cash = self.initial_cash - (alloc_per_asset * n_assets)
        for t in all_tickers:
            p0 = price_by_ticker_date.get(t, {}).get(initial_date)
            if p0 is not None and p0 > 0:
                baseline_shares[t] = alloc_per_asset / (p0 * (1.0 + self.slippage_pct + self.fee_pct))
            else:
                baseline_shares[t] = 0.0

        equity_curve: list[float] = []
        for d in all_dates:
            total_val = cash
            for t, shares in baseline_shares.items():
                p = price_by_ticker_date.get(t, {}).get(d, 0.0)
                total_val += shares * p
            equity_curve.append(round(total_val, 4))

        base_metrics = compute_all_metrics(equity_curve, [])
        return base_metrics

    def run_sensitivity_analysis(
        self,
        market_data: dict[str, dict[str, list[Any]]],
        benchmark_ticker: str = "SPY",
        target_volatilities: list[float] | None = None,
        cluster_caps: list[float] | None = None,
        friction_multipliers: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Run parameter sensitivity grid sweeps over key risk & friction parameters.
        """
        vol_list = target_volatilities or [0.10, 0.14, 0.18]
        cap_list = cluster_caps or [0.20, 0.30, 0.40]
        fric_list = friction_multipliers or [1.5, 2.5, 3.5]

        results = []
        for v in vol_list:
            for c in cap_list:
                for f in fric_list:
                    engine = MultiAssetPortfolioBacktestEngine(
                        initial_cash=self.initial_cash,
                        target_volatility=v,
                        cluster_cap=c,
                        rotation_friction_multiplier=f,
                    )
                    res = engine.run(market_data, benchmark_ticker=benchmark_ticker)
                    results.append({
                        "target_volatility": v,
                        "cluster_cap": c,
                        "friction_multiplier": f,
                        "cagr_pct": res.metrics.get("cagr_pct"),
                        "sharpe": res.metrics.get("sharpe"),
                        "max_drawdown_pct": res.metrics.get("max_drawdown_pct"),
                        "turnover_rate": res.metrics.get("turnover_rate"),
                        "friction_saved": res.friction_saved,
                    })

        return results
