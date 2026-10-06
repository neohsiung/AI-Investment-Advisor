"""
Portfolio Adaptive Intelligence Service (D1 Central Orchestrator).

Unified Orchestration combining:
- M1 Volatility Parity & Cash Defense (MarketRegimeService / ConfidenceRebalanceService)
- M2 Correlation Clustering & Beta Shielder (TickerUniverseService)
- M3 Opportunity Cost & Alpha Decay Swapping (OpportunityCostService / AlphaDecayService)
- M4 Fractional Kelly Sizing & Edge Validation (KellySizingService)
- M5 Extreme Tail Risk & CVaR Stress Defense (StressTestingService)
- M6 Regime-Conditioned Multi-Factor Ensemble (MultiFactorEnsembleService)
- E1 Smart Order Routing & TWAP/VWAP Slicing (SmartOrderRoutingService)
- O1 Bayesian HMM Regime Transition & Nowcasting (BayesianRegimeHMMService)

Provides a centralized single source of truth for portfolio health diagnosis,
multi-factor radar metrics, and end-to-end rebalancing execution plans.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.services.regime_hmm_service import (
    BayesianRegimeHMMService,
    RegimeState,
    RegimeObservation,
    RegimePosterior,
)
from src.services.multi_factor_ensemble_service import (
    MultiFactorEnsembleService,
    RawFactorMetrics,
    StandardizedFactorScores,
)
from src.services.stress_testing_service import (
    StressTestingService,
    StressTestAssessment,
    StressScenario,
)
from src.services.kelly_sizing_service import (
    KellySizingService,
    KellyAssessment,
)
from src.services.opportunity_cost_service import (
    OpportunityCostService,
    SwapAssessment,
)
from src.services.alpha_decay_service import (
    AlphaDecayService,
    AlphaDecayAssessment,
)
from src.services.smart_order_routing_service import (
    SmartOrderRoutingService,
    SlicingPlan,
    ExecutionStrategy,
    OrderAction,
)
from src.services.extreme_value_theory_service import (
    ExtremeValueTheoryService,
    PortfolioEVTAssessment,
    EVTTailRiskMetrics,
    BlackSwanAlertLevel,
)
from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("PortfolioAdaptiveIntelligenceService")


class HealthRating(str, Enum):
    OPTIMAL = "OPTIMAL"
    BALANCED = "BALANCED"
    CAUTION = "CAUTION"
    CRITICAL = "CRITICAL"


@dataclass
class HealthRadarDimensions:
    regime_alignment: float
    diversification_efficiency: float
    factor_balance: float
    tail_risk_resilience: float
    capital_safety: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "regime_alignment": round(self.regime_alignment, 2),
            "diversification_efficiency": round(self.diversification_efficiency, 2),
            "factor_balance": round(self.factor_balance, 2),
            "tail_risk_resilience": round(self.tail_risk_resilience, 2),
            "capital_safety": round(self.capital_safety, 2),
        }


@dataclass
class AdaptiveDiagnosticReport:
    health_score: float
    health_rating: HealthRating
    radar_dimensions: HealthRadarDimensions
    regime_analysis: Dict[str, Any]
    factor_exposures: Dict[str, Any]
    diversification_metrics: Dict[str, Any]
    tail_risk_analysis: Dict[str, Any]
    capital_safety_metrics: Dict[str, Any]
    rebalance_recommendation: Dict[str, Any]
    summary_insights: List[str]
    provenance: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "health_score": round(self.health_score, 1),
            "health_rating": self.health_rating.value,
            "radar_dimensions": self.radar_dimensions.to_dict(),
            "regime_analysis": self.regime_analysis,
            "factor_exposures": self.factor_exposures,
            "diversification_metrics": self.diversification_metrics,
            "tail_risk_analysis": self.tail_risk_analysis,
            "capital_safety_metrics": self.capital_safety_metrics,
            "rebalance_recommendation": self.rebalance_recommendation,
            "summary_insights": self.summary_insights,
            "provenance": self.provenance or {
                "holdings": "template",
                "market_observation": "default",
                "tail_risk": "synthetic",
            },
        }


class PortfolioAdaptiveIntelligenceService:
    """
    D1 Unified Adaptive Intelligence Orchestrator.
    Synthesizes M1-M6, E1, and O1 into unified diagnosis and execution planning.
    """

    def __init__(
        self,
        user_id: str = "default_user",
        regime_service: Optional[BayesianRegimeHMMService] = None,
        factor_service: Optional[MultiFactorEnsembleService] = None,
        stress_service: Optional[StressTestingService] = None,
        kelly_service: Optional[KellySizingService] = None,
        opportunity_service: Optional[OpportunityCostService] = None,
        alpha_decay_service: Optional[AlphaDecayService] = None,
        sor_service: Optional[SmartOrderRoutingService] = None,
        evt_service: Optional[ExtremeValueTheoryService] = None,
        spillover_service: Optional[Any] = None,
        macro_surprise_service: Optional[Any] = None,
        settings_repo: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo
        self.regime_service = regime_service or BayesianRegimeHMMService(user_id=self.user_id, settings_repo=settings_repo)
        self.factor_service = factor_service or MultiFactorEnsembleService(user_id=self.user_id, settings_service=settings_repo)
        self.stress_service = stress_service or StressTestingService(user_id=self.user_id, settings_service=settings_repo)
        self.kelly_service = kelly_service or KellySizingService(user_id=self.user_id, settings_service=settings_repo)
        self.opportunity_service = opportunity_service or OpportunityCostService(user_id=self.user_id)
        self.alpha_decay_service = alpha_decay_service or AlphaDecayService(user_id=self.user_id)
        self.sor_service = sor_service or SmartOrderRoutingService(user_id=self.user_id, settings_repo=settings_repo)
        self.evt_service = evt_service or ExtremeValueTheoryService(settings_repo=settings_repo)
        self.spillover_service = spillover_service
        self.macro_surprise_service = macro_surprise_service

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_repo and hasattr(self.settings_repo, "get"):
            try:
                try:
                    val = self.settings_repo.get(self.user_id, key)
                except (TypeError, Exception):
                    val = self.settings_repo.get(key)
                if val is not None:
                    return val
            except Exception as e:
                logger.warning(f"Error fetching setting {key}: {e}")
        return default

    def diagnose_portfolio(
        self,
        current_weights: Dict[str, float],
        portfolio_value: float = 100000.0,
        asset_prices: Optional[Dict[str, float]] = None,
        asset_advs: Optional[Dict[str, float]] = None,
        asset_betas: Optional[Dict[str, float]] = None,
        asset_sectors: Optional[Dict[str, str]] = None,
        returns_history: Optional[pd.DataFrame] = None,
        market_observation: Optional[Dict[str, float] | RegimeObservation] = None,
        current_drawdown: float = 0.05,
        recent_win_rate: float = 0.55,
        recent_payoff_ratio: float = 1.8,
        provenance: Optional[Dict[str, str]] = None,
    ) -> AdaptiveDiagnosticReport:
        """
        Execute full cross-engine diagnostic evaluation.
        """
        # 1. Sanitize & Normalize current weights
        equity_weights, cash_pct = self._extract_equity_and_cash(current_weights)
        symbols = sorted(list(equity_weights.keys()))

        # Fallback observation if None
        if market_observation is None:
            obs = RegimeObservation(
                spy_price=510.0,
                spy_sma200=500.0,
                vix=18.5,
                return_5d=0.015,
                realized_vol_20d=0.16,
            )
        elif isinstance(market_observation, dict):
            # If spy_price & spy_sma200 not supplied, derive from spy_trend_ratio
            trend_ratio = float(market_observation.get("spy_trend_ratio", 0.02))
            spy_sma200 = float(market_observation.get("spy_sma200", 500.0))
            spy_price = float(market_observation.get("spy_price", spy_sma200 * (1.0 + trend_ratio)))
            obs = RegimeObservation(
                spy_price=spy_price,
                spy_sma200=spy_sma200,
                vix=float(market_observation.get("vix", 18.5)),
                return_5d=float(market_observation.get("return_5d", 0.015)),
                realized_vol_20d=float(market_observation.get("realized_vol_20d", 0.16)),
            )
        else:
            obs = market_observation

        # 2. O1: Regime HMM Nowcasting
        regime_posterior: RegimePosterior = self.regime_service.update_beliefs(observation=obs)
        regime_state: RegimeState = regime_posterior.dominant_regime
        regime_str = regime_state.value
        regime_data = {
            "current_regime": regime_str,
            "regime_confidence": round(regime_posterior.confidence, 3),
            "shannon_entropy": round(regime_posterior.entropy, 3),
            "posterior_probabilities": {
                k: round(v, 4) for k, v in regime_posterior.probabilities.items()
            },
            "suggested_cash_pct": round(regime_posterior.blended_cash_reserve_pct / 100.0, 3),
            "suggested_target_beta": round(regime_posterior.blended_target_beta, 2),
            "dominant_regime": regime_state.value,
        }

        # 3. M1 & M2: Volatility Parity & Correlation Clustering
        vols, betas, sectors = self._resolve_asset_metadata(
            symbols, asset_betas, asset_sectors, returns_history
        )
        (
            inv_vol_weights,
            clusters,
            dr,
            effective_n,
            hhi,
        ) = self._compute_vol_parity_and_clusters(symbols, equity_weights, vols)

        diversification_metrics = {
            "diversification_ratio": round(dr, 3),
            "effective_assets_count": round(effective_n, 2),
            "herfindahl_index": round(hhi, 3),
            "correlation_clusters": clusters,
            "volatility_parity_weights": {k: round(v, 4) for k, v in inv_vol_weights.items()},
        }

        # 4. M6: Multi-Factor Style Exposure Radar
        factor_weights = self.factor_service.get_regime_weights(regime_str)
        factor_exposures = self._estimate_portfolio_factor_exposures(symbols, equity_weights, vols, betas)

        factor_data = {
            "current_exposures": {k: round(v, 3) for k, v in factor_exposures.items()},
            "recommended_factor_tilts": {k: round(v, 3) for k, v in factor_weights.items()},
            "dominant_factor": max(factor_exposures.items(), key=lambda x: x[1])[0] if factor_exposures else "NEUTRAL",
        }

        # 5. M5 & O2: Stress Testing & Extreme Value Theory Tail Risk
        stress_assessment: StressTestAssessment = self.stress_service.evaluate_portfolio(
            weights=equity_weights,
            betas=betas,
            sectors=sectors,
            vols=vols,
        )

        returns_for_evt = returns_history.get("PORTFOLIO") if returns_history else None
        if (returns_for_evt is None or len(returns_for_evt) < 20) and vols:
            mean_vol = float(np.mean(list(vols.values()))) if vols else 0.20
            daily_vol = mean_vol / math.sqrt(252)
            np.random.seed(42)
            returns_for_evt = list(np.random.normal(0.0003, daily_vol, 250))

        evt_assessment = self.evt_service.assess_tail_risk(
            returns=returns_for_evt if returns_for_evt else [0.0] * 20,
            weights=equity_weights,
            asset_returns=returns_history,
        )
        evt_metrics = evt_assessment.portfolio_metrics

        tail_risk_data = {
            "var_95": round(stress_assessment.var_95, 4),
            "cvar_99": round(stress_assessment.cvar_99, 4),
            "worst_historical_drop": round(-stress_assessment.worst_scenario_loss_pct, 4),
            "worst_scenario_name": stress_assessment.worst_scenario_name,
            "mc_breach_prob": round(stress_assessment.mc_mdd_breach_prob, 4),
            "expected_mdd": round(stress_assessment.mc_expected_mdd, 4),
            "is_defense_triggered": stress_assessment.is_defense_triggered or evt_assessment.is_black_swan_triggered,
            "evt_var_999": round(evt_metrics.var_999, 4),
            "evt_cvar_999": round(evt_metrics.es_999, 4),
            "tail_fatness_ratio": round(evt_metrics.tail_fatness_ratio_999, 3),
            "black_swan_alert": evt_metrics.alert_level.value,
            "tail_domain": evt_metrics.tail_domain.value,
        }

        # 6. M4: Kelly Sizing & Drawdown Protection
        avg_loss = 0.05
        avg_win = avg_loss * recent_payoff_ratio
        kelly_assessment: KellyAssessment = self.kelly_service.calculate_from_metrics(
            win_rate=recent_win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sample_count=20,
        )

        shrinkage = max(0.20, 1.0 - (current_drawdown * 2.5))
        safe_leverage = min(1.0, kelly_assessment.fractional_kelly * 5.0) * shrinkage

        capital_safety_data = {
            "full_kelly": round(kelly_assessment.full_kelly, 3),
            "fractional_kelly": round(kelly_assessment.fractional_kelly, 3),
            "shrinkage_factor": round(shrinkage, 3),
            "recommended_leverage": round(safe_leverage, 2),
            "expected_edge": round(kelly_assessment.expected_edge, 4),
        }

        # 7. Synthesize Target Weights & M3 Rebalance Evaluation
        base_suggested_cash = regime_posterior.blended_cash_reserve_pct / 100.0
        extra_spillover_cash = 0.0
        if self.spillover_service is not None and hasattr(self.spillover_service, "get_extra_defensive_cash_pct"):
            try:
                extra_spillover_cash = float(self.spillover_service.get_extra_defensive_cash_pct())
            except Exception as e:
                logger.warning(f"Failed to query spillover extra cash: {e}")

        extra_macro_cash = 0.0
        if self.macro_surprise_service is not None and hasattr(self.macro_surprise_service, "evaluate_surprises"):
            try:
                macro_assessment = self.macro_surprise_service.evaluate_surprises()
                extra_macro_cash = float(getattr(macro_assessment, "recommended_cash_adjustment_pct", 0.0))
            except Exception as e:
                logger.warning(f"Failed to query macro surprise cash adjustment: {e}")

        suggested_cash = min(0.90, base_suggested_cash + extra_spillover_cash + extra_macro_cash)

        # Derive individual asset alpha scores from M6 MultiFactorEnsembleService
        asset_alpha_scores: Dict[str, float] = {}
        if symbols and self.factor_service:
            try:
                metrics_list = []
                for s in symbols:
                    s_vol = vols.get(s, 0.25)
                    s_beta = betas.get(s, 1.0)
                    metrics_list.append(
                        RawFactorMetrics(
                            ticker=s,
                            momentum_12_1=float(max(-0.5, min(1.0, (s_beta - 1.0) * 0.3 + 0.1))),
                            relative_strength_60d=float(max(-0.3, min(0.5, (s_beta - 1.0) * 0.2))),
                            annualized_vol_60d=float(s_vol),
                            downside_dev_60d=float(s_vol * 0.7),
                        )
                    )
                alpha_results = self.factor_service.compute_ensemble_alphas(
                    metrics_list=metrics_list,
                    current_regime=regime_str,
                )
                asset_alpha_scores = {r.ticker: r.composite_alpha_score for r in alpha_results}
            except Exception as e:
                logger.warning(f"PortfolioAdaptiveIntelligenceService: Failed to compute asset alpha scores: {e}")

        target_weights = self._build_target_portfolio_weights(
            base_weights=inv_vol_weights,
            suggested_cash=suggested_cash,
            factor_scores=asset_alpha_scores if asset_alpha_scores else None,
        )

        friction = self.opportunity_service.calculate_roundtrip_friction()
        rebalance_data = self._evaluate_rebalance_and_trades(
            current_weights=current_weights,
            target_weights=target_weights,
            portfolio_value=portfolio_value,
            friction=friction,
            asset_prices=asset_prices,
            asset_advs=asset_advs,
        )

        # 8. Compute 5-Dimensional Health Radar & Overall Score
        radar = self._calculate_health_radar(
            cash_pct=cash_pct,
            suggested_cash=suggested_cash,
            dr=dr,
            hhi=hhi,
            factor_exposures=factor_exposures,
            regime_state=regime_state,
            cvar_99=stress_assessment.cvar_99,
            worst_historical_drop=-stress_assessment.worst_scenario_loss_pct,
            shrinkage_factor=shrinkage,
            leverage=1.0 - cash_pct,
            tail_fatness_ratio=evt_metrics.tail_fatness_ratio_999,
        )

        overall_score = (
            0.25 * radar.regime_alignment
            + 0.25 * radar.diversification_efficiency
            + 0.20 * radar.factor_balance
            + 0.15 * radar.tail_risk_resilience
            + 0.15 * radar.capital_safety
        )
        overall_score = max(0.0, min(100.0, overall_score))

        # Rating categorization
        if overall_score >= 85.0:
            rating = HealthRating.OPTIMAL
        elif overall_score >= 70.0:
            rating = HealthRating.BALANCED
        elif overall_score >= 50.0:
            rating = HealthRating.CAUTION
        else:
            rating = HealthRating.CRITICAL

        # 9. Generate Actionable Summary Insights
        insights = self._generate_insights(
            score=overall_score,
            rating=rating,
            radar=radar,
            regime_state=regime_state,
            confidence=regime_posterior.confidence,
            rebalance_needed=rebalance_data["needs_rebalance"],
            worst_drop=-stress_assessment.worst_scenario_loss_pct,
            cvar_99=stress_assessment.cvar_99,
        )

        actual_provenance = provenance or {
            "holdings": "live" if ((len(current_weights) > 1 and "CASH" not in current_weights) or len(current_weights) > 2) else "template",
            "market_observation": "live" if market_observation is not None else "default",
            "tail_risk": "live_portfolio" if returns_history is not None else "synthetic",
        }

        return AdaptiveDiagnosticReport(
            health_score=overall_score,
            health_rating=rating,
            radar_dimensions=radar,
            regime_analysis=regime_data,
            factor_exposures=factor_data,
            diversification_metrics=diversification_metrics,
            tail_risk_analysis=tail_risk_data,
            capital_safety_metrics=capital_safety_data,
            rebalance_recommendation=rebalance_data,
            summary_insights=insights,
            provenance=actual_provenance,
        )

    def _extract_equity_and_cash(
        self, current_weights: Dict[str, float]
    ) -> Tuple[Dict[str, float], float]:
        """Extract cash and normalize equity weights."""
        cash_keys = {"cash", "usd", "csh", "uninvested"}
        cash_pct = 0.0
        equity_weights = {}

        for k, v in current_weights.items():
            if k.lower() in cash_keys:
                cash_pct += max(0.0, float(v))
            else:
                if v > 0:
                    equity_weights[k] = float(v)

        total_equity = sum(equity_weights.values())
        if total_equity > 0:
            equity_norm = {k: v / total_equity for k, v in equity_weights.items()}
        else:
            equity_norm = {}

        return equity_norm, cash_pct

    def _resolve_asset_metadata(
        self,
        symbols: List[str],
        asset_betas: Optional[Dict[str, float]],
        asset_sectors: Optional[Dict[str, str]],
        returns_history: Optional[pd.DataFrame],
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, str]]:
        """Resolve volatilities, betas, and sectors for holding assets."""
        vols = {}
        betas = {}
        sectors = {}

        default_sectors = {
            "AAPL": "Technology",
            "MSFT": "Technology",
            "GOOGL": "Communication Services",
            "AMZN": "Consumer Discretionary",
            "TSLA": "Consumer Discretionary",
            "NVDA": "Technology",
            "META": "Communication Services",
            "SPY": "Broad Market",
            "QQQ": "Technology",
            "TLT": "Fixed Income",
            "GLD": "Commodities",
        }

        for i, s in enumerate(symbols):
            if returns_history is not None:
                if isinstance(returns_history, pd.DataFrame) and s in returns_history.columns:
                    vols[s] = float(returns_history[s].std() * math.sqrt(252))
                elif isinstance(returns_history, dict) and s in returns_history:
                    vols[s] = float(np.std(returns_history[s]) * math.sqrt(252))
                else:
                    vols[s] = 0.18 + (i % 5) * 0.03
            else:
                vols[s] = 0.18 + (i % 5) * 0.03

            if asset_betas and s in asset_betas:
                betas[s] = float(asset_betas[s])
            else:
                betas[s] = 1.05 if s in {"AAPL", "MSFT", "GOOGL", "AMZN"} else 1.20

            if asset_sectors and s in asset_sectors:
                sectors[s] = asset_sectors[s]
            else:
                sectors[s] = default_sectors.get(s, "Technology")

        return vols, betas, sectors

    def _compute_vol_parity_and_clusters(
        self,
        symbols: List[str],
        equity_weights: Dict[str, float],
        vols: Dict[str, float],
    ) -> Tuple[Dict[str, float], List[List[str]], float, float, float]:
        """Compute inverse volatility parity weights, correlation clusters, DR, and HHI."""
        n = len(symbols)
        if n == 0:
            return {}, [], 1.0, 0.0, 0.0

        inv_vols = {s: 1.0 / max(0.05, vols.get(s, 0.25)) for s in symbols}
        tot_inv = sum(inv_vols.values())
        inv_vol_weights = {s: inv_vols[s] / tot_inv for s in symbols}

        clusters = []
        visited = set()
        for i, s1 in enumerate(symbols):
            if s1 in visited:
                continue
            curr_cluster = [s1]
            visited.add(s1)
            for s2 in symbols[i + 1 :]:
                if s2 not in visited and abs(vols.get(s1, 0.25) - vols.get(s2, 0.25)) < 0.05:
                    curr_cluster.append(s2)
                    visited.add(s2)
            clusters.append(curr_cluster)

        weighted_vol = sum(equity_weights.get(s, 0.0) * vols.get(s, 0.25) for s in symbols)
        rho = 0.45
        port_var = 0.0
        for i, s1 in enumerate(symbols):
            w1 = equity_weights.get(s1, 0.0)
            v1 = vols.get(s1, 0.25)
            port_var += (w1 * v1) ** 2
            for s2 in symbols[i + 1 :]:
                w2 = equity_weights.get(s2, 0.0)
                v2 = vols.get(s2, 0.25)
                port_var += 2.0 * w1 * w2 * v1 * v2 * rho

        port_vol = math.sqrt(max(1e-6, port_var))
        dr = weighted_vol / port_vol if port_vol > 0 else 1.0
        dr = max(1.0, min(2.5, dr))

        sum_sq = sum(w ** 2 for w in equity_weights.values())
        hhi = max(0.0, min(1.0, sum_sq))
        effective_n = 1.0 / hhi if hhi > 0 else float(n)

        return inv_vol_weights, clusters, dr, effective_n, hhi

    def _estimate_portfolio_factor_exposures(
        self,
        symbols: List[str],
        equity_weights: Dict[str, float],
        vols: Dict[str, float],
        betas: Dict[str, float],
    ) -> Dict[str, float]:
        """Estimate portfolio-level aggregate factor exposures [0.0 to 1.0]."""
        if not symbols:
            return {
                "momentum": 0.50,
                "quality": 0.50,
                "value": 0.50,
                "low_vol": 0.50,
                "smart_money": 0.50,
            }

        avg_vol = sum(equity_weights.get(s, 0.0) * vols.get(s, 0.25) for s in symbols)
        avg_beta = sum(equity_weights.get(s, 0.0) * betas.get(s, 1.0) for s in symbols)

        mom = min(1.0, max(0.0, 0.35 + (avg_beta - 1.0) * 0.4))
        qual = min(1.0, max(0.0, 0.70 - (avg_vol - 0.20) * 0.8))
        val = min(1.0, max(0.0, 0.50 - (avg_beta - 1.0) * 0.2))
        low_vol = min(1.0, max(0.0, 1.0 - (avg_vol / 0.40)))
        sm = min(1.0, max(0.0, 0.55 + (mom - 0.5) * 0.3))

        return {
            "momentum": round(mom, 3),
            "quality": round(qual, 3),
            "value": round(val, 3),
            "low_vol": round(low_vol, 3),
            "smart_money": round(sm, 3),
        }

    def _build_target_portfolio_weights(
        self,
        base_weights: Dict[str, float],
        suggested_cash: float,
        factor_scores: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Combine base weights with O1 cash defense and optional M6 multi-factor alpha tilts.
        Higher alpha scores receive proportional overweights while preserving inverse-vol risk parity baseline.
        """
        target = {}
        target["CASH"] = max(0.02, min(0.60, suggested_cash))
        equity_budget = 1.0 - target["CASH"]

        total_base = sum(base_weights.values())
        if total_base <= 0:
            return target

        # If factor_scores supplied, apply alpha tilt multiplier [0.70x ~ 1.30x]
        tilted_weights = {}
        for sym, w in base_weights.items():
            base_norm = w / total_base
            if factor_scores and sym in factor_scores:
                # Factor score in [0.0, 1.0], center at 0.50 -> multiplier in [0.80, 1.20]
                alpha_score = factor_scores[sym]
                multiplier = 1.0 + (alpha_score - 0.50) * 0.40
                tilted_weights[sym] = max(0.01, base_norm * multiplier)
            else:
                tilted_weights[sym] = base_norm

        total_tilted = sum(tilted_weights.values())
        for sym, tw in tilted_weights.items():
            target[sym] = (tw / total_tilted) * equity_budget

        return target

    def _evaluate_rebalance_and_trades(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        portfolio_value: float,
        friction: float,
        asset_prices: Optional[Dict[str, float]],
        asset_advs: Optional[Dict[str, float]],
    ) -> Dict[str, Any]:
        """Evaluate M3 buffer-band rebalance triggers and generate E1 SOR execution plans."""
        all_symbols = set(current_weights.keys()).union(set(target_weights.keys()))
        trades = []
        total_turnover = 0.0
        buffer_band = 0.025

        default_price = 100.0
        default_adv = 1000000.0

        for sym in all_symbols:
            if sym.upper() in {"CASH", "USD"}:
                continue
            cw = current_weights.get(sym, 0.0)
            tw = target_weights.get(sym, 0.0)
            delta = tw - cw

            if abs(delta) >= buffer_band:
                action = "BUY" if delta > 0 else "SELL"
                trade_value = abs(delta) * portfolio_value
                price = (asset_prices or {}).get(sym, default_price)
                shares = max(1, int(round(trade_value / price))) if price > 0 else 0

                trades.append({
                    "symbol": sym,
                    "action": action,
                    "target_weight": round(tw, 4),
                    "current_weight": round(cw, 4),
                    "delta_weight": round(delta, 4),
                    "estimated_shares": shares,
                    "estimated_value": round(trade_value, 2),
                })
                total_turnover += abs(delta)

        needs_rebalance = len(trades) > 0 and total_turnover >= 0.04
        estimated_friction = total_turnover * portfolio_value * friction

        execution_plans = []
        if needs_rebalance:
            for t in trades:
                adv = (asset_advs or {}).get(t["symbol"], default_adv)
                price = (asset_prices or {}).get(t["symbol"], default_price)
                parsed_action = OrderAction.BUY if str(t["action"]).upper() == "BUY" else OrderAction.SELL
                plan: SlicingPlan = self.sor_service.generate_plan(
                    symbol=t["symbol"],
                    action=parsed_action,
                    requested_quantity=float(t["estimated_shares"]),
                    arrival_price=price,
                    adv_20=adv,
                    execution_window_minutes=60,
                )
                execution_plans.append({
                    "symbol": plan.symbol,
                    "action": plan.action.value,
                    "routing_strategy": plan.strategy.value,
                    "approved_quantity": plan.approved_quantity,
                    "unfilled_rollover_quantity": plan.unfilled_rollover_quantity,
                    "total_child_orders": len(plan.child_orders),
                    "is_sliced": len(plan.child_orders) > 1,
                })

        return {
            "needs_rebalance": needs_rebalance,
            "target_weights": {k: round(v, 4) for k, v in target_weights.items()},
            "total_turnover": round(total_turnover, 4),
            "estimated_friction_cost": round(estimated_friction, 2),
            "trade_signals": trades,
            "execution_plans": execution_plans,
        }

    def _calculate_health_radar(
        self,
        cash_pct: float,
        suggested_cash: float,
        dr: float,
        hhi: float,
        factor_exposures: Dict[str, float],
        regime_state: RegimeState,
        cvar_99: float,
        worst_historical_drop: float,
        shrinkage_factor: float,
        leverage: float,
        tail_fatness_ratio: float = 1.0,
    ) -> HealthRadarDimensions:
        """Compute normalized scores [0.0, 100.0] for the 5 radar dimensions."""
        # 1. Regime Alignment (25%)
        cash_diff = abs(cash_pct - suggested_cash)
        regime_score = 100.0 - (cash_diff * 140.0)
        regime_score = max(10.0, min(100.0, regime_score))

        # 2. Diversification Efficiency (25%)
        dr_score = 45.0 + max(0.0, (dr - 1.0) / 0.5) * 55.0
        if hhi > 0.35:
            dr_score -= (hhi - 0.35) * 60.0
        div_score = max(10.0, min(100.0, dr_score))

        # 3. Factor Balance (20%)
        vals = list(factor_exposures.values()) if factor_exposures else [0.5]
        factor_dispersion = float(np.std(vals)) if len(vals) > 1 else 0.0
        factor_score = 90.0 - (factor_dispersion * 30.0)

        quality = factor_exposures.get("quality", 0.5)
        low_vol = factor_exposures.get("low_vol", 0.5)
        if regime_state in (RegimeState.BEAR, RegimeState.NEUTRAL):
            if quality > 0.50:
                factor_score += 10.0
            if low_vol > 0.50:
                factor_score += 10.0
        factor_score = max(10.0, min(100.0, factor_score))

        # 4. Tail Risk Resilience (15%)
        cvar_score = 100.0 - max(0.0, (cvar_99 - 0.025) / 0.045) * 70.0
        hist_score = 100.0 - max(0.0, (abs(worst_historical_drop) - 0.15) / 0.25) * 60.0
        tail_score = 0.5 * cvar_score + 0.5 * hist_score
        if tail_fatness_ratio > 1.80:
            tail_score -= min(30.0, (tail_fatness_ratio - 1.80) * 20.0)
        tail_score = max(10.0, min(100.0, tail_score))

        # 5. Capital Safety (15%)
        lev_score = 100.0
        if leverage > 1.0:
            lev_score -= (leverage - 1.0) * 80.0
        shrinkage_score = shrinkage_factor * 100.0
        cap_score = 0.6 * lev_score + 0.4 * shrinkage_score
        cap_score = max(10.0, min(100.0, cap_score))

        return HealthRadarDimensions(
            regime_alignment=regime_score,
            diversification_efficiency=div_score,
            factor_balance=factor_score,
            tail_risk_resilience=tail_score,
            capital_safety=cap_score,
        )

    def _generate_insights(
        self,
        score: float,
        rating: HealthRating,
        radar: HealthRadarDimensions,
        regime_state: RegimeState,
        confidence: float,
        rebalance_needed: bool,
        worst_drop: float,
        cvar_99: float,
    ) -> List[str]:
        """Generate human-readable, professional executive bullet points."""
        insights = []

        insights.append(
            f"投組自適應綜合評分 {score:.1f}/100（評級：{rating.value}）。"
        )

        regime_names = {
            RegimeState.BULL: "牛市動能擴張",
            RegimeState.NEUTRAL: "震盪整理體制",
            RegimeState.BEAR: "熊市防禦危機",
        }
        regime_desc = regime_names.get(regime_state, regime_state.value)
        insights.append(
            f"O1 HMM 在線現在預測：當前市場處於【{regime_desc}】，置信度達 {confidence * 100:.1f}%。"
        )

        if rebalance_needed:
            insights.append(
                "M3 緩衝帶換庫感知：持倉權重已顯著偏離目標防線，建議啟動再平衡調倉並透過 E1 SOR 分批執行。"
            )
        else:
            insights.append(
                "M3 緩衝帶檢驗：當前持倉處於容忍緩衝區間內，摩擦成本大於再平衡效益，建議維持現狀。"
            )

        if cvar_99 > 0.05:
            insights.append(
                f"尾部風險警示：99% 蒙地卡羅日度 CVaR 為 {cvar_99 * 100:.2f}%，極端情境預估最大跌幅 {abs(worst_drop) * 100:.1f}%，建議提升防禦資產配置。"
            )

        if radar.diversification_efficiency < 65.0:
            insights.append(
                "M2 分散化效率提醒：資產相關分群集中度偏高，可透過層級風險平價 (HRP) 加權以提升資產正交分散度。"
            )

        return insights
