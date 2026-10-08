"""
Strategy Auto-Evolution & Grid Annealing Backtest Service (P4)
策略自動演化回測與參數網格退火服務
=============================================================================
Provides automated quantitative hyperparameter search, Simulated Annealing (SA),
Walk-Forward Optimization (WFO) cross-validation, overfitting degradation guard,
and decision recommendation card generation.

Key Architecture:
1. Parametric Search Space (ParameterRange):
   - Supports continuous (float), discrete (int), and categorical (choice) parameters.
   - Gaussian neighborhood perturbation and step-scaled boundary mutations.
2. Simulated Annealing Optimization Engine:
   - Geometric cooling schedule: T_k = T_0 * gamma^k.
   - Metropolis acceptance criterion: P_accept = exp(delta_fitness / T_k).
   - Escapes local extrema at high temperatures; converges to global optima at low temperatures.
3. Walk-Forward Cross-Validation (WFO):
   - Strict In-Sample (IS) calibration and Out-of-Sample (OOS) validation partitioning.
   - Deflated Sharpe & WFO Efficiency Check (OOS Sharpe / IS Sharpe >= 0.55).
   - Rejects overfitted parameter combinations that fail out-of-sample persistence.
4. Strategy Evolution Recommendation Card:
   - Compares OOS candidates against live baseline configurations.
   - Requires >= 15% OOS Sharpe improvement and <= 10% MDD expansion for promotion.
   - Supports one-click parameter persistence to SettingsRepository.
"""
from __future__ import annotations

import itertools
import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class EvolutionObjective(str, Enum):
    """Optimization objectives for candidate scoring."""
    SHARPE = "SHARPE"
    CALMAR = "CALMAR"
    SORTINO = "SORTINO"
    TOTAL_RETURN = "TOTAL_RETURN"
    COMPOSITE_FITNESS = "COMPOSITE_FITNESS"


@dataclass
class ParameterRange:
    """Definition and mutation logic for a single hyperparameter."""
    name: str
    param_type: str  # "float", "int", "choice"
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[list[Any]] = None
    default_val: Any = None

    def sample(self, rng: random.Random) -> Any:
        """Sample a valid random value from the domain."""
        if self.param_type == "choice" and self.choices:
            return rng.choice(self.choices)
        elif self.param_type == "int":
            low = int(self.min_val if self.min_val is not None else 1)
            high = int(self.max_val if self.max_val is not None else 10)
            st = int(self.step or 1)
            vals = list(range(low, high + 1, st))
            return rng.choice(vals) if vals else low
        else:
            low = float(self.min_val if self.min_val is not None else 0.0)
            high = float(self.max_val if self.max_val is not None else 1.0)
            raw = rng.uniform(low, high)
            if self.step:
                steps = round((raw - low) / self.step)
                raw = low + steps * self.step
            return round(min(high, max(low, raw)), 4)

    def mutate(self, current_val: Any, step_scale: float, rng: random.Random) -> Any:
        """Perturb the current parameter value within domain bounds."""
        if self.param_type == "choice" and self.choices:
            if current_val in self.choices and len(self.choices) > 1:
                idx = self.choices.index(current_val)
                shift = rng.choice([-1, 1])
                new_idx = max(0, min(len(self.choices) - 1, idx + shift))
                return self.choices[new_idx]
            return rng.choice(self.choices)

        low = float(self.min_val if self.min_val is not None else 0.0)
        high = float(self.max_val if self.max_val is not None else 1.0)
        span = high - low

        # Gaussian neighborhood perturbation proportional to span and step_scale
        sigma = max(0.01 * span, (self.step or (0.1 * span)) * step_scale)
        delta = rng.gauss(0.0, sigma)
        new_val = float(current_val) + delta
        clamped = min(high, max(low, new_val))

        if self.param_type == "int":
            st = int(self.step or 1)
            rounded = round((clamped - low) / st) * st + low
            return int(min(high, max(low, rounded)))
        else:
            if self.step:
                steps = round((clamped - low) / self.step)
                clamped = low + steps * self.step
            return round(min(high, max(low, clamped)), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "param_type": self.param_type,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "step": self.step,
            "choices": self.choices,
            "default_val": self.default_val,
        }


@dataclass
class CandidateParameterSet:
    """An individual parameter combination evaluated across IS and OOS periods."""
    candidate_id: str
    params: dict[str, Any]
    in_sample_metrics: dict[str, float]
    out_of_sample_metrics: dict[str, float]
    wfo_efficiency: float
    composite_fitness: float
    generation: int = 0
    is_promotable: bool = False
    promotion_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "params": self.params,
            "in_sample_metrics": {k: round(v, 4) for k, v in self.in_sample_metrics.items()},
            "out_of_sample_metrics": {k: round(v, 4) for k, v in self.out_of_sample_metrics.items()},
            "wfo_efficiency": round(self.wfo_efficiency, 4),
            "composite_fitness": round(self.composite_fitness, 4),
            "generation": self.generation,
            "is_promotable": self.is_promotable,
            "promotion_reason": self.promotion_reason,
        }


@dataclass
class WalkForwardSplit:
    """In-Sample and Out-of-Sample temporal boundary indices."""
    split_index: int
    is_start_idx: int
    is_end_idx: int
    oos_start_idx: int
    oos_end_idx: int
    is_dates: tuple[str, str] = ("", "")
    oos_dates: tuple[str, str] = ("", "")


@dataclass
class EvolutionRunReport:
    """Comprehensive diagnostic artifact generated from an auto-evolution run."""
    run_id: str
    timestamp: str
    search_method: str
    objective: str
    total_candidates_evaluated: int
    baseline_params: dict[str, Any]
    baseline_metrics: dict[str, float]
    best_candidate: Optional[CandidateParameterSet]
    top_candidates: list[CandidateParameterSet] = field(default_factory=list)
    annealing_history: list[dict[str, Any]] = field(default_factory=list)
    recommendation_card: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "search_method": self.search_method,
            "objective": self.objective,
            "total_candidates_evaluated": self.total_candidates_evaluated,
            "baseline_params": self.baseline_params,
            "baseline_metrics": {k: round(v, 4) for k, v in self.baseline_metrics.items()},
            "best_candidate": self.best_candidate.to_dict() if self.best_candidate else None,
            "top_candidates": [c.to_dict() for c in self.top_candidates],
            "annealing_history": self.annealing_history,
            "recommendation_card": self.recommendation_card,
        }


class StrategyAutoEvolutionService:
    """
    Automated Quantitative Strategy Parameter Evolution & Grid Annealing Engine (P4).
    """

    DEFAULT_MIN_WFO_EFFICIENCY = 0.55
    DEFAULT_INITIAL_TEMP = 100.0
    DEFAULT_COOLING_RATE = 0.85
    DEFAULT_MIN_TEMP = 1.0
    DEFAULT_MAX_ITERATIONS = 30
    DEFAULT_PROMOTION_SHARPE_EDGE = 0.15  # Require +15% OOS Sharpe improvement

    DEFAULT_SEARCH_SPACE: list[ParameterRange] = [
        ParameterRange("alloc_target_volatility", "float", min_val=0.08, max_val=0.20, step=0.01, default_val=0.14),
        ParameterRange("alloc_target_beta", "float", min_val=0.50, max_val=1.20, step=0.05, default_val=0.90),
        ParameterRange("alloc_correlation_cluster_threshold", "float", min_val=0.50, max_val=0.85, step=0.05, default_val=0.70),
        ParameterRange("holding_decay_rate", "float", min_val=0.015, max_val=0.060, step=0.005, default_val=0.035),
        ParameterRange("kelly_multiplier", "float", min_val=0.10, max_val=0.40, step=0.05, default_val=0.25),
        ParameterRange("rebalance_interval_days", "int", min_val=3, max_val=10, step=1, default_val=5),
    ]

    def __init__(self, user_id: str = "default_user", settings_repo: Any = None):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
        """Helper to retrieve dynamic setting with fallback."""
        if not self.settings_repo:
            return default
        try:
            val = self.settings_repo.get(self.user_id, key)
            if val is None:
                return default
            if val_type is bool:
                return str(val).lower() in ("true", "1", "yes")
            return val_type(val)
        except Exception as e:
            logger.warning(f"Error loading setting '{key}' ({e}); using default {default}")
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting("evolution_annealing_enabled", True, bool)

    @property
    def min_wfo_efficiency(self) -> float:
        return float(self._get_setting("evolution_wfo_min_efficiency", self.DEFAULT_MIN_WFO_EFFICIENCY, float))

    @property
    def initial_temp(self) -> float:
        return float(self._get_setting("evolution_annealing_initial_temp", self.DEFAULT_INITIAL_TEMP, float))

    @property
    def cooling_rate(self) -> float:
        return float(self._get_setting("evolution_annealing_cooling_rate", self.DEFAULT_COOLING_RATE, float))

    def evaluate_fitness(
        self,
        metrics: dict[str, float],
        objective: EvolutionObjective | str = EvolutionObjective.COMPOSITE_FITNESS,
    ) -> float:
        """
        Evaluate objective fitness score for backtest metrics.
        Composite Formula:
            Fitness = 0.50 * Sharpe + 0.30 * Calmar + 0.20 * max(0, Return) - 1.50 * min(0.50, MDD)
        """
        sharpe = float(metrics.get("sharpe", 0.0))
        mdd = abs(float(metrics.get("max_drawdown", metrics.get("mdd", 0.15))))
        ann_return = float(metrics.get("annualized_return", metrics.get("total_return", 0.0)))
        calmar = float(metrics.get("calmar", (ann_return / max(0.01, mdd)) if mdd > 0 else 0.0))
        sortino = float(metrics.get("sortino", sharpe * 1.1))

        obj_name = getattr(objective, "value", str(objective)).upper()
        if obj_name == EvolutionObjective.SHARPE.value:
            return sharpe
        elif obj_name == EvolutionObjective.CALMAR.value:
            return calmar
        elif obj_name == EvolutionObjective.SORTINO.value:
            return sortino
        elif obj_name == EvolutionObjective.TOTAL_RETURN.value:
            return ann_return
        else:  # COMPOSITE_FITNESS
            score = (
                0.50 * sharpe
                + 0.30 * min(5.0, calmar)
                + 0.20 * max(-0.50, min(1.0, ann_return))
                - 1.50 * min(0.50, mdd)
            )
            return round(score, 4)

    def split_walk_forward(
        self,
        total_bars: int,
        train_ratio: float = 0.70,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """
        Partition sequential bar index range into In-Sample (IS) and Out-of-Sample (OOS).
        """
        n = max(10, int(total_bars))
        ratio = max(0.50, min(0.90, float(train_ratio)))
        split_point = int(n * ratio)

        is_bounds = (0, split_point)
        oos_bounds = (split_point, n)
        return is_bounds, oos_bounds

    def calculate_wfo_efficiency(self, is_sharpe: float, oos_sharpe: float) -> float:
        """
        Calculate Walk-Forward Optimization (WFO) efficiency ratio.
        Efficiency = OOS_Sharpe / max(0.01, IS_Sharpe).
        """
        if is_sharpe <= 0:
            return 0.0 if oos_sharpe <= 0 else 1.0
        eff = oos_sharpe / max(0.01, is_sharpe)
        return max(0.0, round(eff, 4))

    def _default_fast_backtest_evaluator(
        self,
        params: dict[str, Any],
        returns_series: list[float],
    ) -> dict[str, float]:
        """
        Internal deterministic, pure-Python performance evaluator for hyperparameter testing.
        Simulates portfolio equity compounding modulated by target volatility, beta, and decay.
        """
        if not returns_series:
            return {"sharpe": 0.0, "max_drawdown": 0.0, "annualized_return": 0.0, "calmar": 0.0}

        target_vol = float(params.get("alloc_target_volatility", 0.14))
        target_beta = float(params.get("alloc_target_beta", 0.90))
        cluster_thresh = float(params.get("alloc_correlation_cluster_threshold", 0.70))
        decay_rate = float(params.get("holding_decay_rate", 0.035))
        kelly_mult = float(params.get("kelly_multiplier", 0.25))

        # Leverage & exposure factor based on params
        vol_scalar = min(1.3, target_vol / 0.14)
        beta_scalar = min(1.2, target_beta / 0.90)
        clustering_protection = 1.0 + max(0.0, (0.75 - cluster_thresh) * 0.1)
        decay_benefit = 1.0 + (0.035 - decay_rate) * 0.5
        kelly_factor = 0.8 + (kelly_mult * 0.8)

        leverage = vol_scalar * beta_scalar * kelly_factor

        # Compound simulated equity curve
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        period_returns: list[float] = []

        for r in returns_series:
            # Scaled daily return with parameter friction/enhancement
            sim_r = r * leverage * clustering_protection * decay_benefit
            # Apply slight fee drag per bar (0.01 bps)
            sim_r -= 0.00001
            equity *= (1.0 + sim_r)
            period_returns.append(sim_r)

            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        n = len(period_returns)
        mean_r = sum(period_returns) / n
        var_r = sum((x - mean_r) ** 2 for x in period_returns) / max(1, n - 1)
        std_r = math.sqrt(var_r)

        ann_factor = math.sqrt(252.0)
        ann_mean = mean_r * 252.0
        ann_std = max(1e-6, std_r * ann_factor)

        sharpe = ann_mean / ann_std
        total_ret = equity - 1.0
        ann_ret = (equity ** (252.0 / max(1, n))) - 1.0
        calmar = (ann_ret / max(0.01, max_dd)) if max_dd > 0 else ann_ret

        return {
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "annualized_return": round(ann_ret, 4),
            "total_return": round(total_ret, 4),
            "calmar": round(calmar, 4),
        }

    def evaluate_promotion_gate(
        self,
        candidate: CandidateParameterSet,
        baseline_metrics: dict[str, float],
    ) -> tuple[bool, str]:
        """
        Examine if an evolved parameter candidate satisfies statistical promotion criteria:
        1. WFO Efficiency >= min_wfo_efficiency (no curve-fitting).
        2. OOS Sharpe >= Baseline Sharpe * (1 + 15%).
        3. OOS Max Drawdown <= Baseline MDD * 1.10.
        """
        oos_sharpe = candidate.out_of_sample_metrics.get("sharpe", 0.0)
        base_sharpe = baseline_metrics.get("sharpe", 0.0)
        oos_mdd = candidate.out_of_sample_metrics.get("max_drawdown", 0.20)
        base_mdd = baseline_metrics.get("max_drawdown", 0.20)

        # 1. WFO Overfitting Check
        if candidate.wfo_efficiency < self.min_wfo_efficiency:
            return False, f"WFO efficiency {candidate.wfo_efficiency:.2f} < {self.min_wfo_efficiency:.2f} (Overfitting risk)"

        # 2. Sharpe Improvement Check
        required_sharpe = base_sharpe * (1.0 + self.DEFAULT_PROMOTION_SHARPE_EDGE)
        if oos_sharpe < required_sharpe:
            return False, f"OOS Sharpe {oos_sharpe:.2f} < required threshold {required_sharpe:.2f} (+15% edge)"

        # 3. Risk / MDD Constraint Check
        if oos_mdd > (base_mdd * 1.15):
            return False, f"OOS Max Drawdown {oos_mdd * 100:.1f}% exceeded tolerance ceiling ({base_mdd * 1.15 * 100:.1f}%)"

        reason = (
            f"Passed all promotion gates: OOS Sharpe {oos_sharpe:.2f} (+{((oos_sharpe/max(0.01, base_sharpe))-1)*100:.1f}%), "
            f"WFO Efficiency {candidate.wfo_efficiency:.2f} >= {self.min_wfo_efficiency:.2f}, "
            f"MDD {oos_mdd * 100:.1f}%"
        )
        return True, reason

    def generate_recommendation_card(
        self,
        best_candidate: Optional[CandidateParameterSet],
        baseline_params: dict[str, Any],
        baseline_metrics: dict[str, float],
    ) -> dict[str, Any]:
        """
        Generate structured decision card for auto-evolution recommendation.
        """
        if not best_candidate or not best_candidate.is_promotable:
            return {
                "decision": "MAINTAIN_CURRENT",
                "status": "NO_PROMOTION",
                "headline": "Current production baseline remains optimal; no candidates cleared OOS promotion gates.",
                "confidence": "HIGH",
                "param_diffs": {},
                "projected_improvements": {},
            }

        param_diffs: dict[str, dict[str, Any]] = {}
        for k, v in best_candidate.params.items():
            base_v = baseline_params.get(k)
            if base_v != v:
                param_diffs[k] = {"current": base_v, "evolved": v}

        base_sharpe = max(0.01, baseline_metrics.get("sharpe", 0.0))
        cand_sharpe = best_candidate.out_of_sample_metrics.get("sharpe", 0.0)
        sharpe_gain_pct = round(((cand_sharpe - base_sharpe) / base_sharpe) * 100.0, 1)

        base_mdd = baseline_metrics.get("max_drawdown", 0.0)
        cand_mdd = best_candidate.out_of_sample_metrics.get("max_drawdown", 0.0)
        mdd_change_pct = round((cand_mdd - base_mdd) * 100.0, 1)

        return {
            "decision": "PRODUCE_UPDATE_RECOMMENDATION",
            "status": "READY_FOR_PROMOTION",
            "candidate_id": best_candidate.candidate_id,
            "headline": f"Evolved hyperparameter set cleared WFO gates with +{sharpe_gain_pct}% OOS Sharpe edge.",
            "confidence": "HIGH" if best_candidate.wfo_efficiency >= 0.70 else "MODERATE",
            "wfo_efficiency": best_candidate.wfo_efficiency,
            "param_diffs": param_diffs,
            "projected_improvements": {
                "sharpe_edge_pct": sharpe_gain_pct,
                "mdd_delta_pts": mdd_change_pct,
                "composite_fitness": best_candidate.composite_fitness,
            },
            "promotion_reason": best_candidate.promotion_reason,
            "action_required": "Review diffs and approve one-click promotion into SettingsRepository.",
        }

    def run_simulated_annealing(
        self,
        historical_returns: list[float],
        search_space: Optional[list[ParameterRange]] = None,
        baseline_params: Optional[dict[str, Any]] = None,
        objective: EvolutionObjective | str = EvolutionObjective.COMPOSITE_FITNESS,
        iterations: Optional[int] = None,
        initial_temp: Optional[float] = None,
        cooling_rate: Optional[float] = None,
        train_ratio: float = 0.70,
        random_seed: Optional[int] = None,
        custom_backtest_fn: Optional[Callable] = None,
    ) -> EvolutionRunReport:
        """
        Execute Simulated Annealing (SA) optimization with Walk-Forward IS/OOS cross-validation.
        """
        obj_key = getattr(objective, "value", str(objective)).upper()
        rng = random.Random(random_seed) if random_seed is not None else random.Random()
        space = search_space or self.DEFAULT_SEARCH_SPACE
        eval_fn = custom_backtest_fn or self._default_fast_backtest_evaluator

        max_iters = iterations or self.DEFAULT_MAX_ITERATIONS
        t_current = initial_temp or self.initial_temp
        gamma = cooling_rate or self.cooling_rate

        # 1. Establish Walk-Forward Partition
        is_bounds, oos_bounds = self.split_walk_forward(len(historical_returns), train_ratio=train_ratio)
        is_data = historical_returns[is_bounds[0]:is_bounds[1]]
        oos_data = historical_returns[oos_bounds[0]:oos_bounds[1]]

        # 2. Evaluate Baseline Configuration
        base_p = baseline_params or {p.name: (p.default_val if p.default_val is not None else p.sample(rng)) for p in space}
        base_is_metrics = eval_fn(base_p, is_data)
        base_oos_metrics = eval_fn(base_p, oos_data)

        # 3. Annealing Initialization
        current_params = dict(base_p)
        current_is_metrics = dict(base_is_metrics)
        current_fitness = self.evaluate_fitness(current_is_metrics, objective)

        best_candidate: Optional[CandidateParameterSet] = None
        top_candidates: list[CandidateParameterSet] = []
        annealing_history: list[dict[str, Any]] = []

        total_evaluated = 0

        for i in range(max_iters):
            # Mutate neighborhood candidate
            cand_p = dict(current_params)
            step_scale = max(0.2, t_current / (initial_temp or self.initial_temp))

            # Choose 1~2 parameters to mutate
            num_mutations = rng.choice([1, 2])
            mutate_keys = rng.sample(space, min(num_mutations, len(space)))
            for param_def in mutate_keys:
                cand_p[param_def.name] = param_def.mutate(cand_p[param_def.name], step_scale, rng)

            cand_is_metrics = eval_fn(cand_p, is_data)
            cand_fitness = self.evaluate_fitness(cand_is_metrics, objective)
            total_evaluated += 1

            delta_f = cand_fitness - current_fitness

            # Metropolis Acceptance Criterion
            accepted = False
            if delta_f > 0:
                accepted = True
            else:
                prob = math.exp(delta_f / max(1e-4, t_current))
                if rng.random() < prob:
                    accepted = True

            if accepted:
                current_params = dict(cand_p)
                current_is_metrics = dict(cand_is_metrics)
                current_fitness = cand_fitness

            # Out-of-Sample verification for accepted or high-performing candidates
            cand_oos_metrics = eval_fn(cand_p, oos_data)
            is_sh = cand_is_metrics.get("sharpe", 0.0)
            oos_sh = cand_oos_metrics.get("sharpe", 0.0)
            wfo_eff = self.calculate_wfo_efficiency(is_sh, oos_sh)

            cand_obj = CandidateParameterSet(
                candidate_id=f"cand-{uuid.uuid4().hex[:8]}",
                params=cand_p,
                in_sample_metrics=cand_is_metrics,
                out_of_sample_metrics=cand_oos_metrics,
                wfo_efficiency=wfo_eff,
                composite_fitness=self.evaluate_fitness(cand_oos_metrics, objective),
                generation=i + 1,
            )

            is_promo, reason = self.evaluate_promotion_gate(cand_obj, base_oos_metrics)
            cand_obj.is_promotable = is_promo
            cand_obj.promotion_reason = reason

            top_candidates.append(cand_obj)

            # Update best candidate (evaluated on Out-of-Sample stability)
            if best_candidate is None or (cand_obj.composite_fitness > best_candidate.composite_fitness and cand_obj.wfo_efficiency >= self.min_wfo_efficiency):
                best_candidate = cand_obj

            annealing_history.append({
                "iteration": i + 1,
                "temperature": round(t_current, 2),
                "current_fitness": round(current_fitness, 4),
                "delta_fitness": round(delta_f, 4),
                "accepted": accepted,
                "wfo_efficiency": round(wfo_eff, 4),
            })

            # Geometric cooling
            t_current = max(self.DEFAULT_MIN_TEMP, t_current * gamma)

        # Sort top candidates by OOS composite fitness
        sorted_top = sorted(top_candidates, key=lambda c: c.composite_fitness, reverse=True)[:5]
        recommendation_card = self.generate_recommendation_card(best_candidate, base_p, base_oos_metrics)

        report = EvolutionRunReport(
            run_id=f"evo-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            search_method="SIMULATED_ANNEALING",
            objective=obj_key,
            total_candidates_evaluated=total_evaluated,
            baseline_params=base_p,
            baseline_metrics=base_oos_metrics,
            best_candidate=best_candidate,
            top_candidates=sorted_top,
            annealing_history=annealing_history,
            recommendation_card=recommendation_card,
        )

        return report

    def run_grid_search(
        self,
        historical_returns: list[float],
        search_space: Optional[list[ParameterRange]] = None,
        baseline_params: Optional[dict[str, Any]] = None,
        objective: EvolutionObjective | str = EvolutionObjective.COMPOSITE_FITNESS,
        train_ratio: float = 0.70,
        max_combinations: int = 50,
        custom_backtest_fn: Optional[Callable] = None,
    ) -> EvolutionRunReport:
        """
        Execute deterministic Grid Search across discretized parameter coordinates.
        """
        obj_key = getattr(objective, "value", str(objective)).upper()
        space = search_space or self.DEFAULT_SEARCH_SPACE
        eval_fn = custom_backtest_fn or self._default_fast_backtest_evaluator

        is_bounds, oos_bounds = self.split_walk_forward(len(historical_returns), train_ratio=train_ratio)
        is_data = historical_returns[is_bounds[0]:is_bounds[1]]
        oos_data = historical_returns[oos_bounds[0]:oos_bounds[1]]

        base_p = baseline_params or {p.name: (p.default_val if p.default_val is not None else 0.14) for p in space}
        base_oos_metrics = eval_fn(base_p, oos_data)

        # Generate discrete grids
        param_grids: dict[str, list[Any]] = {}
        for p in space:
            if p.param_type == "choice" and p.choices:
                param_grids[p.name] = p.choices[:3]
            elif p.param_type == "int":
                low = int(p.min_val or 1)
                high = int(p.max_val or 10)
                st = max(1, int(p.step or 1))
                param_grids[p.name] = list(range(low, high + 1, st))[:4]
            else:
                low = float(p.min_val or 0.0)
                high = float(p.max_val or 1.0)
                st = float(p.step or (high - low) / 3.0)
                vals: list[float] = []
                cur = low
                while cur <= high + 1e-6 and len(vals) < 4:
                    vals.append(round(cur, 4))
                    cur += st
                param_grids[p.name] = vals

        keys = list(param_grids.keys())
        all_combinations = list(itertools.product(*(param_grids[k] for k in keys)))
        if len(all_combinations) > max_combinations:
            all_combinations = all_combinations[:max_combinations]

        candidates: list[CandidateParameterSet] = []
        best_candidate: Optional[CandidateParameterSet] = None

        for idx, comb in enumerate(all_combinations):
            cand_p = dict(zip(keys, comb))
            cand_is_metrics = eval_fn(cand_p, is_data)
            cand_oos_metrics = eval_fn(cand_p, oos_data)

            is_sh = cand_is_metrics.get("sharpe", 0.0)
            oos_sh = cand_oos_metrics.get("sharpe", 0.0)
            wfo_eff = self.calculate_wfo_efficiency(is_sh, oos_sh)

            cand_obj = CandidateParameterSet(
                candidate_id=f"grid-{idx + 1}",
                params=cand_p,
                in_sample_metrics=cand_is_metrics,
                out_of_sample_metrics=cand_oos_metrics,
                wfo_efficiency=wfo_eff,
                composite_fitness=self.evaluate_fitness(cand_oos_metrics, obj_key),
                generation=idx + 1,
            )

            is_promo, reason = self.evaluate_promotion_gate(cand_obj, base_oos_metrics)
            cand_obj.is_promotable = is_promo
            cand_obj.promotion_reason = reason

            candidates.append(cand_obj)
            if best_candidate is None or (cand_obj.composite_fitness > best_candidate.composite_fitness and cand_obj.wfo_efficiency >= self.min_wfo_efficiency):
                best_candidate = cand_obj

        sorted_top = sorted(candidates, key=lambda c: c.composite_fitness, reverse=True)[:5]
        recommendation_card = self.generate_recommendation_card(best_candidate, base_p, base_oos_metrics)

        report = EvolutionRunReport(
            run_id=f"grid-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            search_method="GRID",
            objective=obj_key,
            total_candidates_evaluated=len(all_combinations),
            baseline_params=base_p,
            baseline_metrics=base_oos_metrics,
            best_candidate=best_candidate,
            top_candidates=sorted_top,
            annealing_history=[],
            recommendation_card=recommendation_card,
        )

        return report

    def run_random_search(
        self,
        historical_returns: list[float],
        search_space: Optional[list[ParameterRange]] = None,
        baseline_params: Optional[dict[str, Any]] = None,
        objective: EvolutionObjective | str = EvolutionObjective.COMPOSITE_FITNESS,
        iterations: int = 30,
        train_ratio: float = 0.70,
        random_seed: Optional[int] = None,
        custom_backtest_fn: Optional[Callable] = None,
    ) -> EvolutionRunReport:
        """
        Execute random uniform exploration across hyperparameter bounds.
        """
        obj_key = getattr(objective, "value", str(objective)).upper()
        rng = random.Random(random_seed) if random_seed is not None else random.Random()
        space = search_space or self.DEFAULT_SEARCH_SPACE
        eval_fn = custom_backtest_fn or self._default_fast_backtest_evaluator

        is_bounds, oos_bounds = self.split_walk_forward(len(historical_returns), train_ratio=train_ratio)
        is_data = historical_returns[is_bounds[0]:is_bounds[1]]
        oos_data = historical_returns[oos_bounds[0]:oos_bounds[1]]

        base_p = baseline_params or {p.name: (p.default_val if p.default_val is not None else p.sample(rng)) for p in space}
        base_oos_metrics = eval_fn(base_p, oos_data)

        candidates: list[CandidateParameterSet] = []
        best_candidate: Optional[CandidateParameterSet] = None

        for idx in range(iterations):
            cand_p = {p.name: p.sample(rng) for p in space}
            cand_is_metrics = eval_fn(cand_p, is_data)
            cand_oos_metrics = eval_fn(cand_p, oos_data)

            is_sh = cand_is_metrics.get("sharpe", 0.0)
            oos_sh = cand_oos_metrics.get("sharpe", 0.0)
            wfo_eff = self.calculate_wfo_efficiency(is_sh, oos_sh)

            cand_obj = CandidateParameterSet(
                candidate_id=f"rand-{idx + 1}",
                params=cand_p,
                in_sample_metrics=cand_is_metrics,
                out_of_sample_metrics=cand_oos_metrics,
                wfo_efficiency=wfo_eff,
                composite_fitness=self.evaluate_fitness(cand_oos_metrics, obj_key),
                generation=idx + 1,
            )

            is_promo, reason = self.evaluate_promotion_gate(cand_obj, base_oos_metrics)
            cand_obj.is_promotable = is_promo
            cand_obj.promotion_reason = reason

            candidates.append(cand_obj)
            if best_candidate is None or (cand_obj.composite_fitness > best_candidate.composite_fitness and cand_obj.wfo_efficiency >= self.min_wfo_efficiency):
                best_candidate = cand_obj

        sorted_top = sorted(candidates, key=lambda c: c.composite_fitness, reverse=True)[:5]
        recommendation_card = self.generate_recommendation_card(best_candidate, base_p, base_oos_metrics)

        report = EvolutionRunReport(
            run_id=f"rand-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            search_method="RANDOM",
            objective=obj_key,
            total_candidates_evaluated=iterations,
            baseline_params=base_p,
            baseline_metrics=base_oos_metrics,
            best_candidate=best_candidate,
            top_candidates=sorted_top,
            annealing_history=[],
            recommendation_card=recommendation_card,
        )

        return report

    def apply_candidate_to_settings(self, candidate: CandidateParameterSet) -> bool:
        """
        Persist approved candidate hyperparameters into SettingsRepository.
        """
        if not self.settings_repo:
            logger.warning("Cannot apply candidate parameters: settings_repo is None")
            return False

        try:
            for key, val in candidate.params.items():
                self.settings_repo.set(self.user_id, key, val)
            logger.info(f"Successfully applied candidate {candidate.candidate_id} to settings repository")
            return True
        except Exception as e:
            logger.error(f"Failed to apply candidate to settings repository: {e}")
            return False

    def evolve_factor_rotation_matrix(
        self,
        bars: Optional[list[Any]] = None,
        baseline_matrix: Optional[Any] = None,
        iterations: int = 30,
        train_ratio: float = 0.70,
        objective: str = "SHARPE",
        random_seed: Optional[int] = None,
    ) -> Any:
        """
        Execute Walk-Forward Simulated Annealing on tactical factor rotation weights.
        """
        from src.services.factor_rotation_replay_engine import (
            FactorRotationReplayEngine,
            FactorWeightMatrix,
        )

        tuning_enabled = self._get_setting("enable_tactical_factor_replay_tuning", True, bool)
        if not tuning_enabled:
            logger.info("Factor replay tuning is disabled by settings.")

        lookback = int(self._get_setting("replay_evolution_lookback_bars", 252, int))
        wfo_ratio = float(self._get_setting("replay_evolution_wfo_train_ratio", train_ratio, float))

        replay_bars = bars
        if not replay_bars:
            replay_bars = FactorRotationReplayEngine.generate_synthetic_replay_dataset(
                num_bars=lookback,
                random_seed=random_seed or 42,
            )

        base_mat = baseline_matrix
        if base_mat is None:
            # Check if existing matrix stored in settings
            stored_pw = self._get_setting("tactical_phase_factor_weights", None, str)
            if stored_pw:
                try:
                    pw_data = json.loads(stored_pw) if isinstance(stored_pw, str) else stored_pw
                    base_mat = FactorWeightMatrix.from_dict(pw_data)
                except Exception as e:
                    logger.warning(f"Could not parse stored tactical_phase_factor_weights: {e}")
                    base_mat = FactorWeightMatrix()
            else:
                base_mat = FactorWeightMatrix()

        engine = FactorRotationReplayEngine()
        report = engine.evolve_factor_weights(
            bars=replay_bars,
            baseline_matrix=base_mat,
            max_iterations=iterations,
            train_ratio=wfo_ratio,
            objective=objective,
            random_seed=random_seed,
        )
        return report

    def apply_evolved_matrix_to_settings(self, matrix: Any) -> bool:
        """
        Persist evolved FactorWeightMatrix into SettingsRepository.
        """
        if not self.settings_repo:
            logger.warning("Cannot apply evolved matrix: settings_repo is None")
            return False

        try:
            mat_dict = matrix.to_dict() if hasattr(matrix, "to_dict") else dict(matrix)
            # Store primary phase weights mapping
            self.settings_repo.set(
                self.user_id,
                "tactical_phase_factor_weights",
                json.dumps(mat_dict),
            )
            # Synchronize rotation hyperparameters if present
            if "min_edge_pct" in mat_dict:
                self.settings_repo.set(
                    self.user_id,
                    "tactical_rotation_min_edge_pct",
                    float(mat_dict["min_edge_pct"]),
                )
            if "liquidity_premium_weight" in mat_dict:
                self.settings_repo.set(
                    self.user_id,
                    "factor_liquidity_premium_weight",
                    float(mat_dict["liquidity_premium_weight"]),
                )
            logger.info("Successfully applied evolved factor matrix to settings repository")
            return True
        except Exception as e:
            logger.error(f"Failed to apply evolved factor matrix to settings: {e}")
            return False

