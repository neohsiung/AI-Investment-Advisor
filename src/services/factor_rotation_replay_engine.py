"""
Factor Rotation Replay & Auto-Evolution Engine
==============================================
策略自學演化歷史重播回測與因子權重矩陣退火調參引擎

核心功能：
1. 因子權重矩陣 (FactorWeightMatrix)：
   - 管理 4 大市場週期 (EARLY_REBOUND, BULL_ACCELERATION, LATE_CYCLE_VALUE, DEFENSIVE_CONSOLIDATION)
     對應的 6 大因子權重 (Momentum, Smart Money, Liquidity Premium, Quality, Value, Low Vol)
     及換倉超參數 (min_edge_pct, liquidity_premium_weight)。
   - 提供嚴格單體投影 (Simplex Projection) 與高斯變異算子，保證權重非負且和為 1.0。
2. 歷史回放回測 (FactorRotationReplayEngine.simulate_replay)：
   - 逐日回放歷史市場體制 (VIX, Z-Score, SPY SMA200, 殖利率利差) 與候選標的多因子回報。
   - 模擬動態現金直投 (Direct Cash Deployment) 與摩擦感知換倉 (Friction-Aware Swaps)。
   - 計算年化夏普 (Sharpe)、索提諾 (Sortino)、卡瑪 (Calmar)、最大回撤 (MDD) 與換手率。
3. 模擬退火與前向走查優化 (FactorRotationReplayEngine.evolve_factor_weights)：
   - Walk-Forward Optimization (WFO: In-Sample 訓練 vs Out-of-Sample 驗證)。
   - 幾何降溫退火排程，探索全局最優因子權重分配。
   - 過擬合降解防護 (WFO Efficiency >= 0.55, OOS Sharpe 提升 >= 15%)。
   - 生成結構化決策建議卡 (recommendation_card) 並支援一鍵持久化至 SettingsRepository。
"""
from __future__ import annotations

import copy
import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from src.services.tactical_factor_rotation_service import (
    TacticalFactorRotationService,
    TacticalMarketPhase,
)

logger = logging.getLogger("FactorRotationReplayEngine")

FACTOR_NAMES = [
    "momentum",
    "smart_money",
    "liquidity_premium",
    "quality",
    "value",
    "low_vol",
]


@dataclass
class FactorWeightMatrix:
    """
    Parametric factor allocation weights for all 4 tactical market phases,
    plus rotation hyperparameters.
    """
    phase_weights: Dict[str, Dict[str, float]] = field(default_factory=dict)
    min_edge_pct: float = 0.08
    liquidity_premium_weight: float = 0.35

    def __post_init__(self):
        if not self.phase_weights:
            self.phase_weights = self.default_phase_weights()
        self.normalize()

    @classmethod
    def default_phase_weights(cls) -> Dict[str, Dict[str, float]]:
        """Standard baseline weights customized for each market phase."""
        return {
            TacticalMarketPhase.EARLY_REBOUND.value: {
                "momentum": 0.30,
                "liquidity_premium": 0.25,
                "smart_money": 0.20,
                "quality": 0.15,
                "value": 0.10,
                "low_vol": 0.00,
            },
            TacticalMarketPhase.BULL_ACCELERATION.value: {
                "momentum": 0.35,
                "smart_money": 0.25,
                "quality": 0.20,
                "liquidity_premium": 0.10,
                "value": 0.10,
                "low_vol": 0.00,
            },
            TacticalMarketPhase.LATE_CYCLE_VALUE.value: {
                "value": 0.35,
                "quality": 0.25,
                "liquidity_premium": 0.15,
                "low_vol": 0.15,
                "smart_money": 0.05,
                "momentum": 0.05,
            },
            TacticalMarketPhase.DEFENSIVE_CONSOLIDATION.value: {
                "low_vol": 0.35,
                "quality": 0.35,
                "value": 0.15,
                "liquidity_premium": 0.10,
                "smart_money": 0.05,
                "momentum": 0.00,
            },
        }

    def normalize(self) -> None:
        """Ensure all phase weights sum to 1.0 and are non-negative."""
        for phase_name, weights in self.phase_weights.items():
            for factor in FACTOR_NAMES:
                weights[factor] = max(0.0, float(weights.get(factor, 0.0)))
            total = sum(weights.values())
            if total > 0:
                for factor in FACTOR_NAMES:
                    weights[factor] = round(weights[factor] / total, 4)
                # Re-adjust rounding residual onto largest component
                residual = 1.0 - sum(weights.values())
                largest_k = max(weights.keys(), key=lambda k: weights[k])
                weights[largest_k] = round(weights[largest_k] + residual, 4)
            else:
                eq = round(1.0 / len(FACTOR_NAMES), 4)
                for factor in FACTOR_NAMES:
                    weights[factor] = eq

    def mutate(self, step_scale: float, rng: random.Random) -> FactorWeightMatrix:
        """
        Produce a mutated matrix perturbing 1~2 phases and/or hyperparameters.
        Guarantees mutated weights lie on the simplex.
        """
        new_mat = copy.deepcopy(self)
        phases = list(new_mat.phase_weights.keys())

        # Select 1~2 phases to mutate
        num_phases = rng.choice([1, 2])
        chosen_phases = rng.sample(phases, num_phases)

        for p in chosen_phases:
            p_weights = new_mat.phase_weights[p]
            # Choose 2 factors to trade off weight
            f1, f2 = rng.sample(FACTOR_NAMES, 2)
            shift = rng.gauss(0.0, 0.05 * step_scale)
            # Apply shift
            p_weights[f1] = max(0.0, p_weights[f1] + shift)
            p_weights[f2] = max(0.0, p_weights[f2] - shift)

        # 30% chance to mutate rotation threshold parameters
        if rng.random() < 0.30:
            edge_delta = rng.gauss(0.0, 0.01 * step_scale)
            new_mat.min_edge_pct = max(0.03, min(0.20, round(new_mat.min_edge_pct + edge_delta, 4)))

        new_mat.normalize()
        return new_mat

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_weights": {
                p: {k: round(v, 4) for k, v in w.items()}
                for p, w in self.phase_weights.items()
            },
            "min_edge_pct": round(self.min_edge_pct, 4),
            "liquidity_premium_weight": round(self.liquidity_premium_weight, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FactorWeightMatrix:
        if not data:
            return cls()
        pw = data.get("phase_weights") or {}
        min_edge = float(data.get("min_edge_pct", 0.08))
        liq_w = float(data.get("liquidity_premium_weight", 0.35))
        return cls(phase_weights=pw, min_edge_pct=min_edge, liquidity_premium_weight=liq_w)


@dataclass
class ReplayBar:
    """Historical bar containing regime indicators and cross-sectional factor data."""
    timestamp: str
    vix: float = 20.0
    vix_z_score: float = 0.0
    spy_price: float = 500.0
    spy_sma200: float = 490.0
    yield_spread: Optional[float] = None
    regime_hint: Optional[str] = None
    asset_factors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    asset_returns: Dict[str, float] = field(default_factory=dict)


@dataclass
class ReplayPerformanceMetrics:
    """Quantitative backtest metrics calculated from simulated portfolio equity curve."""
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    total_return: float = 0.0
    turnover_ratio: float = 0.0
    total_swaps: int = 0
    daily_returns: List[float] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sharpe": round(self.sharpe, 4),
            "sortino": round(self.sortino, 4),
            "calmar": round(self.calmar, 4),
            "annualized_return": round(self.annualized_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "total_return": round(self.total_return, 4),
            "turnover_ratio": round(self.turnover_ratio, 4),
            "total_swaps": self.total_swaps,
        }


@dataclass
class FactorEvolutionReport:
    """Comprehensive diagnostic artifact generated from factor matrix evolution."""
    run_id: str
    timestamp: str
    objective: str
    total_iterations: int
    baseline_matrix: FactorWeightMatrix
    baseline_metrics: ReplayPerformanceMetrics
    best_matrix: FactorWeightMatrix
    best_is_metrics: ReplayPerformanceMetrics
    best_oos_metrics: ReplayPerformanceMetrics
    wfo_efficiency: float
    is_promotable: bool
    promotion_reason: str
    recommendation_card: Dict[str, Any] = field(default_factory=dict)
    annealing_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "objective": self.objective,
            "total_iterations": self.total_iterations,
            "baseline_matrix": self.baseline_matrix.to_dict(),
            "baseline_metrics": self.baseline_metrics.to_dict(),
            "best_matrix": self.best_matrix.to_dict(),
            "best_is_metrics": self.best_is_metrics.to_dict(),
            "best_oos_metrics": self.best_oos_metrics.to_dict(),
            "wfo_efficiency": round(self.wfo_efficiency, 4),
            "is_promotable": self.is_promotable,
            "promotion_reason": self.promotion_reason,
            "recommendation_card": self.recommendation_card,
            "annealing_history": self.annealing_history,
        }


class FactorRotationReplayEngine:
    """
    Simulates portfolio evolution and optimizes factor weight matrices
    via historical time-series replay and walk-forward simulated annealing.
    """

    DEFAULT_WFO_MIN_EFFICIENCY = 0.55
    DEFAULT_MIN_SHARPE_EDGE = 0.15      # Require >= +15% OOS Sharpe improvement
    DEFAULT_MAX_MDD_EXPANSION = 0.10     # Max +10% relative drawdown increase

    def __init__(self, rotation_service: Optional[TacticalFactorRotationService] = None):
        self.rotation_service = rotation_service or TacticalFactorRotationService()

    def simulate_replay(
        self,
        bars: List[ReplayBar],
        matrix: FactorWeightMatrix,
        initial_cash: float = 100000.0,
        target_cash_ratio: float = 0.10,
        max_swaps_per_tick: int = 2,
    ) -> ReplayPerformanceMetrics:
        """
        Replay sequential market bars simulating tactical factor rotation and cash deployment.
        """
        if not bars:
            return ReplayPerformanceMetrics()

        cash = float(initial_cash)
        positions: Dict[str, float] = {}  # ticker -> current market value
        equity_curve: List[float] = [initial_cash]
        daily_returns: List[float] = []
        total_swaps = 0
        total_swap_volume = 0.0

        for bar in bars:
            # 1. Update existing positions based on daily asset returns
            for ticker, mval in list(positions.items()):
                r = float(bar.asset_returns.get(ticker, 0.0))
                positions[ticker] = max(0.0, mval * (1.0 + r))

            curr_pos_val = sum(positions.values())
            total_nlv = cash + curr_pos_val

            if total_nlv <= 0:
                break

            # 2. Determine market phase
            phase, _ = self.rotation_service.determine_market_phase(
                vix=bar.vix,
                vix_z_score=bar.vix_z_score,
                spy_price=bar.spy_price,
                spy_sma200=bar.spy_sma200,
                yield_spread=bar.yield_spread,
                regime_hint=bar.regime_hint,
            )

            # 3. Score candidate assets using current matrix weights
            weights = matrix.phase_weights.get(phase.value, {})
            candidate_scores: List[Tuple[str, float, float]] = []  # (ticker, composite_score, beta)

            # Extract liquidity metrics
            liq_metrics = self.rotation_service.compute_liquidity_premium_metrics(bar.asset_factors)

            for ticker, f_data in bar.asset_factors.items():
                f_mom = float(f_data.get("momentum_score", f_data.get("momentum", 0.5)))
                f_smart = float(f_data.get("smart_money_score", f_data.get("smart_money", 0.5)))
                f_qual = float(f_data.get("quality_score", f_data.get("quality", 0.5)))
                f_val = float(f_data.get("value_score", f_data.get("value", 0.5)))
                f_low_vol = float(f_data.get("low_vol_score", f_data.get("low_vol", 0.5)))
                beta = float(f_data.get("beta", 1.0))

                metric = liq_metrics.get(ticker)
                f_liq = metric.liquidity_premium_score if metric else 0.50

                comp = (
                    weights.get("momentum", 0.0) * f_mom
                    + weights.get("smart_money", 0.0) * f_smart
                    + weights.get("liquidity_premium", 0.0) * f_liq
                    + weights.get("quality", 0.0) * f_qual
                    + weights.get("value", 0.0) * f_val
                    + weights.get("low_vol", 0.0) * f_low_vol
                )
                if phase == TacticalMarketPhase.EARLY_REBOUND and beta > 1.2:
                    comp = min(1.0, comp + min(0.08, (beta - 1.0) * 0.05))

                candidate_scores.append((ticker, comp, beta))

            candidate_scores.sort(key=lambda x: x[1], reverse=True)
            cand_score_map = {x[0]: x[1] for x in candidate_scores}

            # 4. Direct Cash Deployment (Deploy excess cash above target_cash_ratio)
            base_cash_target = target_cash_ratio * total_nlv
            excess_cash = max(0.0, cash - base_cash_target)
            max_pos_val = 0.20 * total_nlv

            if excess_cash >= 100.0:
                top_leaders = [c for c in candidate_scores if c[1] >= 0.65][:3]
                if top_leaders:
                    cash_per_leader = excess_cash / len(top_leaders)
                    for leader_sym, leader_score, _ in top_leaders:
                        curr_mval = positions.get(leader_sym, 0.0)
                        if curr_mval < max_pos_val:
                            alloc = min(cash_per_leader, max_pos_val - curr_mval)
                            fee = alloc * 0.0015
                            if alloc >= 50.0 and (alloc + fee) <= cash:
                                positions[leader_sym] = curr_mval + alloc
                                cash -= (alloc + fee)

            # 5. Friction-Aware Swaps (汰弱換強)
            holding_list = [
                (sym, cand_score_map.get(sym, 0.40), mval)
                for sym, mval in positions.items()
                if mval >= 100.0
            ]
            holding_list.sort(key=lambda x: x[1])  # Ascending

            top_candidates = [
                c for c in candidate_scores
                if c[0] not in positions and c[1] >= 0.70
            ]
            swap_count = 0
            friction_hurdle = 0.003 * 2.5 + matrix.min_edge_pct

            for h_sym, h_score, h_val in holding_list:
                if swap_count >= max_swaps_per_tick or not top_candidates:
                    break

                cand_sym, cand_score, _ = top_candidates[0]
                edge = cand_score - h_score

                if edge >= friction_hurdle:
                    swap_amount = min(h_val, total_nlv * 0.10)
                    if swap_amount >= 100.0:
                        roundtrip_friction = swap_amount * 0.003 * 2.5
                        # Sell holding
                        positions[h_sym] = max(0.0, positions[h_sym] - swap_amount)
                        if positions[h_sym] < 1.0:
                            positions.pop(h_sym, None)
                        # Buy candidate after deducting friction
                        net_buy_amount = swap_amount - roundtrip_friction
                        positions[cand_sym] = positions.get(cand_sym, 0.0) + net_buy_amount

                        top_candidates.pop(0)
                        swap_count += 1
                        total_swaps += 1
                        total_swap_volume += swap_amount

            # 6. End-of-day equity calculation
            end_nlv = cash + sum(positions.values())
            prev_nlv = equity_curve[-1]
            day_return = (end_nlv - prev_nlv) / prev_nlv if prev_nlv > 0 else 0.0

            daily_returns.append(day_return)
            equity_curve.append(end_nlv)

        return self._compute_performance_metrics(
            daily_returns=daily_returns,
            equity_curve=equity_curve,
            total_swaps=total_swaps,
            total_swap_volume=total_swap_volume,
            initial_cash=initial_cash,
        )

    def _compute_performance_metrics(
        self,
        daily_returns: List[float],
        equity_curve: List[float],
        total_swaps: int,
        total_swap_volume: float,
        initial_cash: float,
    ) -> ReplayPerformanceMetrics:
        """Calculate annualized Sharpe, Sortino, Calmar, MDD from return series."""
        if not daily_returns:
            return ReplayPerformanceMetrics()

        n_bars = len(daily_returns)
        mean_ret = float(np.mean(daily_returns))
        std_ret = float(np.std(daily_returns))
        rf_daily = 0.04 / 252.0  # Assumed 4% risk-free rate

        # Annualized Sharpe
        ann_sharpe = 0.0
        if std_ret > 1e-6:
            ann_sharpe = ((mean_ret - rf_daily) / std_ret) * math.sqrt(252)

        # Downside Deviation for Sortino
        downside_returns = [r - rf_daily for r in daily_returns if r < rf_daily]
        ann_sortino = ann_sharpe
        if downside_returns:
            downside_std = float(np.std(downside_returns))
            if downside_std > 1e-6:
                ann_sortino = ((mean_ret - rf_daily) / downside_std) * math.sqrt(252)

        # Max Drawdown
        peak = equity_curve[0]
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        # Total & Annualized Return
        final_eq = equity_curve[-1]
        total_return = (final_eq - initial_cash) / initial_cash
        years = max(1.0 / 252.0, n_bars / 252.0)
        ann_return = (1.0 + total_return) ** (1.0 / years) - 1.0 if total_return > -1.0 else -1.0

        # Calmar Ratio
        calmar = (ann_return / max_dd) if max_dd > 0 else 0.0

        # Turnover Ratio (Total swap volume / Avg NLV)
        avg_nlv = float(np.mean(equity_curve))
        turnover_ratio = (total_swap_volume / avg_nlv) if avg_nlv > 0 else 0.0

        return ReplayPerformanceMetrics(
            sharpe=round(ann_sharpe, 4),
            sortino=round(ann_sortino, 4),
            calmar=round(calmar, 4),
            annualized_return=round(ann_return, 4),
            max_drawdown=round(max_dd, 4),
            total_return=round(total_return, 4),
            turnover_ratio=round(turnover_ratio, 4),
            total_swaps=total_swaps,
            daily_returns=daily_returns,
            equity_curve=equity_curve,
        )

    def evaluate_fitness(
        self,
        metrics: ReplayPerformanceMetrics,
        objective: str = "SHARPE",
    ) -> float:
        """Score performance metrics according to optimization objective."""
        obj_upper = objective.upper()
        if obj_upper == "SHARPE":
            return metrics.sharpe
        elif obj_upper == "CALMAR":
            return metrics.calmar
        elif obj_upper == "SORTINO":
            return metrics.sortino
        elif obj_upper == "RETURN":
            return metrics.annualized_return
        else:  # COMPOSITE
            return (
                0.50 * metrics.sharpe
                + 0.30 * min(4.0, metrics.calmar)
                + 0.20 * min(1.0, metrics.annualized_return)
                - 1.50 * min(0.50, metrics.max_drawdown)
            )

    def evolve_factor_weights(
        self,
        bars: List[ReplayBar],
        baseline_matrix: Optional[FactorWeightMatrix] = None,
        max_iterations: int = 30,
        initial_temp: float = 100.0,
        cooling_rate: float = 0.85,
        train_ratio: float = 0.70,
        objective: str = "SHARPE",
        random_seed: Optional[int] = None,
    ) -> FactorEvolutionReport:
        """
        Execute Simulated Annealing over historical bars with Walk-Forward cross validation.
        """
        rng = random.Random(random_seed) if random_seed is not None else random.Random()
        base_mat = baseline_matrix or FactorWeightMatrix()

        # 1. Walk-Forward Partitioning (In-Sample vs Out-of-Sample)
        n_bars = len(bars)
        split_idx = max(20, int(n_bars * max(0.50, min(0.90, train_ratio))))
        is_bars = bars[:split_idx]
        oos_bars = bars[split_idx:]

        # 2. Evaluate Baseline Performance
        base_is_metrics = self.simulate_replay(is_bars, base_mat)
        base_oos_metrics = self.simulate_replay(oos_bars, base_mat)
        base_oos_fitness = self.evaluate_fitness(base_oos_metrics, objective)

        # 3. Annealing State
        curr_mat = copy.deepcopy(base_mat)
        curr_is_metrics = base_is_metrics
        curr_fitness = self.evaluate_fitness(curr_is_metrics, objective)

        best_mat = copy.deepcopy(base_mat)
        best_is_metrics = base_is_metrics
        best_oos_metrics = base_oos_metrics
        best_oos_fitness = base_oos_fitness

        annealing_history: List[Dict[str, Any]] = []
        t_current = initial_temp

        for it in range(max_iterations):
            step_scale = max(0.2, t_current / initial_temp)
            cand_mat = curr_mat.mutate(step_scale=step_scale, rng=rng)

            cand_is_metrics = self.simulate_replay(is_bars, cand_mat)
            cand_fitness = self.evaluate_fitness(cand_is_metrics, objective)
            delta_f = cand_fitness - curr_fitness

            # Metropolis Acceptance Criterion
            accepted = False
            if delta_f > 0:
                accepted = True
            else:
                prob = math.exp(delta_f / max(1e-4, t_current))
                if rng.random() < prob:
                    accepted = True

            if accepted:
                curr_mat = cand_mat
                curr_is_metrics = cand_is_metrics
                curr_fitness = cand_fitness

            # Check Out-of-Sample performance on accepted candidate
            cand_oos_metrics = self.simulate_replay(oos_bars, cand_mat)
            is_sh = cand_is_metrics.sharpe
            oos_sh = cand_oos_metrics.sharpe
            wfo_eff = (oos_sh / max(0.01, is_sh)) if is_sh > 0 else 0.0

            cand_oos_fitness = self.evaluate_fitness(cand_oos_metrics, objective)

            # Update best candidate if OOS performance improves and passes WFO barrier
            if (cand_oos_fitness > best_oos_fitness and wfo_eff >= self.DEFAULT_WFO_MIN_EFFICIENCY):
                best_mat = cand_mat
                best_is_metrics = cand_is_metrics
                best_oos_metrics = cand_oos_metrics
                best_oos_fitness = cand_oos_fitness

            annealing_history.append({
                "iteration": it + 1,
                "temperature": round(t_current, 2),
                "is_fitness": round(cand_fitness, 4),
                "oos_sharpe": round(oos_sh, 4),
                "wfo_efficiency": round(wfo_eff, 4),
                "accepted": accepted,
            })

            # Geometric cooling schedule
            t_current = max(1.0, t_current * cooling_rate)

        # 4. Out-of-Sample Promotion Gate Check
        final_wfo_eff = (
            (best_oos_metrics.sharpe / max(0.01, best_is_metrics.sharpe))
            if best_is_metrics.sharpe > 0 else 0.0
        )
        sharpe_edge = (
            (best_oos_metrics.sharpe - base_oos_metrics.sharpe) / max(0.01, abs(base_oos_metrics.sharpe))
            if base_oos_metrics.sharpe != 0 else (1.0 if best_oos_metrics.sharpe > 0 else 0.0)
        )
        mdd_expansion = (
            (best_oos_metrics.max_drawdown - base_oos_metrics.max_drawdown) / max(0.01, base_oos_metrics.max_drawdown)
            if base_oos_metrics.max_drawdown > 0 else 0.0
        )

        is_promotable = (
            sharpe_edge >= self.DEFAULT_MIN_SHARPE_EDGE
            and mdd_expansion <= self.DEFAULT_MAX_MDD_EXPANSION
            and final_wfo_eff >= self.DEFAULT_WFO_MIN_EFFICIENCY
        )

        if is_promotable:
            promo_reason = (
                f"通過客觀驗證門檻：OOS Sharpe 提升 {sharpe_edge*100:+.1f}% "
                f"(基準={base_oos_metrics.sharpe:.2f} -> 最優={best_oos_metrics.sharpe:.2f}), "
                f"WFO 效率={final_wfo_eff:.2f}, MDD 變化={mdd_expansion*100:+.1f}%"
            )
        else:
            promo_reason = (
                f"未達晉升門檻：Sharpe 提升 {sharpe_edge*100:+.1f}% (需 >=15%), "
                f"WFO 效率={final_wfo_eff:.2f} (需 >=0.55), 或 MDD 擴展過大 ({mdd_expansion*100:+.1f}%)"
            )

        recommendation_card = {
            "decision": "PRODUCE_UPDATE_RECOMMENDATION" if is_promotable else "MAINTAIN_CURRENT",
            "is_promotable": is_promotable,
            "promotion_reason": promo_reason,
            "metrics_comparison": {
                "sharpe": {"baseline": base_oos_metrics.sharpe, "evolved": best_oos_metrics.sharpe},
                "annualized_return": {"baseline": base_oos_metrics.annualized_return, "evolved": best_oos_metrics.annualized_return},
                "max_drawdown": {"baseline": base_oos_metrics.max_drawdown, "evolved": best_oos_metrics.max_drawdown},
                "calmar": {"baseline": base_oos_metrics.calmar, "evolved": best_oos_metrics.calmar},
                "turnover": {"baseline": base_oos_metrics.turnover_ratio, "evolved": best_oos_metrics.turnover_ratio},
            },
            "best_matrix": best_mat.to_dict(),
        }

        return FactorEvolutionReport(
            run_id=f"evo-fac-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            objective=objective,
            total_iterations=max_iterations,
            baseline_matrix=base_mat,
            baseline_metrics=base_oos_metrics,
            best_matrix=best_mat,
            best_is_metrics=best_is_metrics,
            best_oos_metrics=best_oos_metrics,
            wfo_efficiency=final_wfo_eff,
            is_promotable=is_promotable,
            promotion_reason=promo_reason,
            recommendation_card=recommendation_card,
            annealing_history=annealing_history,
        )

    @classmethod
    def generate_synthetic_replay_dataset(
        cls,
        num_bars: int = 252,
        num_assets: int = 8,
        random_seed: int = 42,
    ) -> List[ReplayBar]:
        """
        Generate realistic synthetic historical bars with alternating market regimes
        and multi-factor asset time series for deterministic testing and replay evaluation.
        """
        rng = random.Random(random_seed)
        tickers = [f"ASSET_{i+1}" for i in range(num_assets)]
        bars: List[ReplayBar] = []

        base_spy = 450.0
        base_sma200 = 440.0

        for b in range(num_bars):
            # Simulate alternating market regimes (Bull -> High VIX / Rebound -> Late Cycle)
            cycle_phase = (b // 60) % 4
            if cycle_phase == 0:  # Bull Acceleration
                vix = rng.uniform(14.0, 19.0)
                vix_z = rng.uniform(-1.0, 0.5)
                spy_price = base_spy * 1.05
                spread = 0.40
                regime_hint = "TREND_ACCELERATION"
            elif cycle_phase == 1:  # Panic Spike to Rebound
                vix = rng.uniform(23.0, 29.0)
                vix_z = rng.uniform(0.5, 1.3)  # falling z-score
                spy_price = base_spy * 0.98
                spread = 0.10
                regime_hint = "VOLATILITY_PIVOT"
            elif cycle_phase == 2:  # Late Cycle Value
                vix = rng.uniform(16.0, 21.0)
                vix_z = rng.uniform(-0.2, 0.5)
                spy_price = base_spy * 1.02
                spread = -0.45  # Inverted yield curve
                regime_hint = "NORMAL"
            else:  # Defensive Consolidation
                vix = rng.uniform(28.0, 34.0)
                vix_z = rng.uniform(1.8, 2.7)
                spy_price = base_spy * 0.93
                spread = -0.10
                regime_hint = "DEFENSIVE"

            asset_factors: Dict[str, Dict[str, Any]] = {}
            asset_returns: Dict[str, float] = {}

            for idx, t in enumerate(tickers):
                # Endow first 2 assets with high momentum/smart money
                is_leader = idx < 2
                is_laggard = idx >= (num_assets - 2)

                mom = rng.uniform(0.75, 0.98) if is_leader else (rng.uniform(0.10, 0.35) if is_laggard else rng.uniform(0.40, 0.70))
                smart = rng.uniform(0.70, 0.95) if is_leader else (rng.uniform(0.15, 0.40) if is_laggard else rng.uniform(0.40, 0.65))
                qual = rng.uniform(0.60, 0.95)
                val = rng.uniform(0.30, 0.80)
                low_vol = rng.uniform(0.20, 0.80)
                beta = rng.uniform(1.3, 1.8) if is_leader else rng.uniform(0.8, 1.2)

                adv5 = rng.uniform(2000.0, 3500.0) if is_leader else rng.uniform(500.0, 1500.0)
                adv20 = rng.uniform(1000.0, 1800.0)

                asset_factors[t] = {
                    "momentum": mom,
                    "smart_money": smart,
                    "quality": qual,
                    "value": val,
                    "low_vol": low_vol,
                    "beta": beta,
                    "adv_5d": adv5,
                    "adv_20d": adv20,
                }

                # Asset returns correlated with leadership
                drift = 0.0015 if is_leader else (-0.0005 if is_laggard else 0.0003)
                asset_returns[t] = rng.gauss(drift, 0.015)

            bars.append(ReplayBar(
                timestamp=f"2026-01-{(b%28)+1:02d}",
                vix=vix,
                vix_z_score=vix_z,
                spy_price=spy_price,
                spy_sma200=base_sma200,
                yield_spread=spread,
                regime_hint=regime_hint,
                asset_factors=asset_factors,
                asset_returns=asset_returns,
            ))

        return bars
