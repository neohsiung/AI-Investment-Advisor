"""
Real-Time Portfolio Stress Testing & CVaR Tail Risk Defense Service
投組實時極端壓力測試與 CVaR 尾部風險防禦服務
=============================================================================
Implements production-grade stress testing and pre-emptive de-risking:
1. Historical Scenario Replay (2008 GFC, 2020 COVID, 2022 Rates, 2024 Tech Unwind).
2. Parametric & Historical Value-at-Risk (VaR) and Conditional VaR (CVaR / Expected Shortfall).
3. Monte Carlo Simulation (1,000 paths over 60-day horizon) for MDD breach probability.
4. Pre-emptive De-risking Policy: automatic emergency cash buffer raise and high-beta dampening.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


@dataclass
class StressScenario:
    """Historical or hypothetical market stress scenario definition."""
    name: str
    description: str
    market_shock_pct: float
    volatility_multiplier: float = 2.0
    sector_shocks: dict[str, float] = field(default_factory=dict)
    default_asset_shock_pct: float | None = None


@dataclass
class ScenarioImpactResult:
    """Impact of a single stress scenario on the portfolio."""
    scenario_name: str
    scenario_loss_pct: float
    asset_contributions: dict[str, float]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "scenario_loss_pct": round(self.scenario_loss_pct, 4),
            "asset_contributions": {k: round(v, 4) for k, v in self.asset_contributions.items()},
            "details": self.details,
        }


@dataclass
class StressTestAssessment:
    """Comprehensive portfolio tail risk and stress testing assessment."""
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    worst_scenario_name: str
    worst_scenario_loss_pct: float
    scenario_results: list[ScenarioImpactResult]
    mc_mdd_breach_prob: float
    mc_expected_mdd: float
    mc_worst_mdd_95: float
    is_defense_triggered: bool
    defense_reasons: list[str]
    recommended_cash_pct: float
    recommended_weight_adjustments: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "var_95": round(self.var_95, 4),
            "var_99": round(self.var_99, 4),
            "cvar_95": round(self.cvar_95, 4),
            "cvar_99": round(self.cvar_99, 4),
            "worst_scenario_name": self.worst_scenario_name,
            "worst_scenario_loss_pct": round(self.worst_scenario_loss_pct, 4),
            "scenario_results": [r.to_dict() for r in self.scenario_results],
            "mc_mdd_breach_prob": round(self.mc_mdd_breach_prob, 4),
            "mc_expected_mdd": round(self.mc_expected_mdd, 4),
            "mc_worst_mdd_95": round(self.mc_worst_mdd_95, 4),
            "is_defense_triggered": self.is_defense_triggered,
            "defense_reasons": self.defense_reasons,
            "recommended_cash_pct": round(self.recommended_cash_pct, 4),
            "recommended_weight_adjustments": {
                k: round(v, 4) for k, v in self.recommended_weight_adjustments.items()
            },
        }


class StressTestingService:
    """
    Stress Testing and Tail Risk Defense Service.
    極端黑天鵝壓力測試與尾部風險預防性降險服務。
    """

    DEFAULT_CVAR_BUDGET = 0.08           # Max allowable 99% CVaR (8.0%)
    DEFAULT_LOSS_THRESHOLD = 0.10        # Max allowable worst historical scenario loss (10.0%)
    DEFAULT_MC_SIMULATIONS = 1000        # Number of Monte Carlo return paths
    DEFAULT_MAX_MDD_PROB = 0.15          # Max allowable probability of breaching 12% MDD (15.0%)
    DEFAULT_EMERGENCY_CASH = 0.35        # Mandated cash buffer upon de-risking trigger (35.0%)

    # Built-in Historical Scenarios
    STANDARD_SCENARIOS: ClassVar[list[StressScenario]] = [
        StressScenario(
            name="2008_GFC",
            description="2008 Global Financial Crisis: liquidity freeze and global systemic credit breakdown",
            market_shock_pct=-0.22,
            volatility_multiplier=3.0,
            sector_shocks={
                "Financials": -0.14,
                "Technology": -0.08,
                "Consumer Discretionary": -0.10,
                "Energy": -0.15,
            },
        ),
        StressScenario(
            name="2020_COVID",
            description="2020 COVID-19 Flash Crash: rapid cascade with VIX spike and cross-asset correlation surge",
            market_shock_pct=-0.16,
            volatility_multiplier=3.5,
            sector_shocks={
                "Technology": -0.05,
                "Industrials": -0.12,
                "Energy": -0.22,
                "Real Estate": -0.18,
            },
        ),
        StressScenario(
            name="2022_RATES",
            description="2022 Aggressive Inflation & Fed Rate Hike Shock: multiple compression on high-multiple tech",
            market_shock_pct=-0.12,
            volatility_multiplier=1.8,
            sector_shocks={
                "Technology": -0.16,
                "Communication Services": -0.14,
                "Consumer Discretionary": -0.10,
                "Utilities": 0.02,
                "Energy": 0.08,
            },
        ),
        StressScenario(
            name="2024_TECH_UNWIND",
            description="2024 AI / Mega-cap Momentum Reversal & Crowded Position Unwind",
            market_shock_pct=-0.08,
            volatility_multiplier=2.0,
            sector_shocks={
                "Technology": -0.13,
                "Semiconductors": -0.18,
                "Communication Services": -0.08,
            },
        ),
    ]

    def __init__(
        self,
        user_id: str = "default_user",
        settings_service: Any | None = None,
        custom_scenarios: list[StressScenario] | None = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self.scenarios = custom_scenarios if custom_scenarios is not None else list(self.STANDARD_SCENARIOS)

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service is not None:
            try:
                val = self.settings_service.get_setting(key)
                if val is not None:
                    return type(default)(val)
            except Exception as e:  # noqa: BLE001
                logger.debug("Failed to read setting %s: %s", key, e)
        return default

    @property
    def cvar_budget(self) -> float:
        return float(self._get_setting("stress_test_cvar_budget", self.DEFAULT_CVAR_BUDGET))

    @property
    def loss_threshold(self) -> float:
        return float(self._get_setting("stress_test_loss_threshold", self.DEFAULT_LOSS_THRESHOLD))

    @property
    def mc_simulations(self) -> int:
        return int(self._get_setting("stress_test_mc_simulations", self.DEFAULT_MC_SIMULATIONS))

    @property
    def max_mdd_prob(self) -> float:
        return float(self._get_setting("stress_test_max_mdd_prob", self.DEFAULT_MAX_MDD_PROB))

    @property
    def emergency_cash_pct(self) -> float:
        return float(self._get_setting("stress_test_emergency_cash_pct", self.DEFAULT_EMERGENCY_CASH))

    def calculate_var_cvar(
        self,
        returns: list[float],
        confidence: float = 0.99,
    ) -> tuple[float, float]:
        """
        Compute historical Value-at-Risk (VaR) and Conditional Value-at-Risk (CVaR).
        Returns:
            (var, cvar) where values are positive float decimals representing loss.
        """
        if not returns or len(returns) < 5:
            # Fallback for insufficient sample
            return (0.03, 0.05)

        arr = np.array(returns, dtype=float)
        losses = -arr  # Loss is negative return

        # VaR at given confidence percentile
        var_val = float(np.percentile(losses, confidence * 100.0))
        var_val = max(0.0, var_val)

        # CVaR is the mean of losses exceeding VaR
        tail_losses = losses[losses >= var_val]
        if len(tail_losses) > 0:
            cvar_val = float(np.mean(tail_losses))
        else:
            cvar_val = var_val

        return (var_val, cvar_val)

    def calculate_parametric_var_cvar(
        self,
        annualized_vol: float,
        annualized_return: float = 0.0,
        confidence: float = 0.99,
    ) -> tuple[float, float]:
        """
        Compute parametric normal VaR and CVaR for a 1-day horizon.
        """
        daily_vol = max(0.001, annualized_vol / math.sqrt(252))
        daily_ret = annualized_return / 252.0

        if confidence >= 0.99:
            z = 2.3263
        elif confidence >= 0.95:
            z = 1.6449
        else:
            z = 1.2816

        var_val = max(0.0, float(z * daily_vol - daily_ret))
        # Normal CVaR: daily_vol * phi(z) / (1 - alpha) - daily_ret
        phi_z = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * z * z)
        cvar_val = max(var_val, float((daily_vol * phi_z / (1.0 - confidence)) - daily_ret))

        return (var_val, cvar_val)

    def replay_stress_scenario(
        self,
        scenario: StressScenario,
        weights: dict[str, float],
        betas: dict[str, float],
        sectors: dict[str, str],
    ) -> ScenarioImpactResult:
        """
        Evaluate portfolio instant drawdown under a specific stress scenario.
        Shock_i = beta_i * MarketShock + SectorShock_i
        """
        total_loss = 0.0
        contributions: dict[str, float] = {}

        for ticker, weight in weights.items():
            if weight <= 0:
                continue
            beta = betas.get(ticker, 1.0)
            sector = sectors.get(ticker, "")
            sec_shock = scenario.sector_shocks.get(sector, 0.0)

            # Asset shock combines market beta transmission and sector penalty
            asset_shock = beta * scenario.market_shock_pct + sec_shock
            if scenario.default_asset_shock_pct is not None:
                asset_shock = min(asset_shock, scenario.default_asset_shock_pct)

            loss_contribution = weight * asset_shock  # Negative number
            contributions[ticker] = loss_contribution
            total_loss += loss_contribution

        # Total scenario drawdown as positive percentage loss
        loss_pct = abs(total_loss)
        return ScenarioImpactResult(
            scenario_name=scenario.name,
            scenario_loss_pct=loss_pct,
            asset_contributions=contributions,
            details={
                "description": scenario.description,
                "market_shock_pct": scenario.market_shock_pct,
                "volatility_multiplier": scenario.volatility_multiplier,
            },
        )

    def simulate_monte_carlo_drawdown(
        self,
        portfolio_daily_vol: float,
        portfolio_daily_return: float = 0.0003,
        days: int = 60,
        simulations: int = 1000,
        mdd_threshold: float = 0.12,
        seed: int = 42,
    ) -> tuple[float, float, float]:
        """
        Simulate 1,000 future return paths over `days` trading bars.
        Returns:
            (breach_prob, expected_mdd, worst_mdd_95)
        """
        np.random.seed(seed)
        daily_vol = max(0.005, portfolio_daily_vol)
        daily_ret = portfolio_daily_return

        # Generate random normal matrix of shape (simulations, days)
        rand_shocks = np.random.randn(simulations, days)
        # Daily returns under geometric Brownian motion: (mu - 0.5 * sigma^2) + sigma * Z
        drift = daily_ret - 0.5 * (daily_vol ** 2)
        step_returns = np.exp(drift + daily_vol * rand_shocks)

        # Price paths starting at 1.0
        cum_paths = np.cumprod(step_returns, axis=1)
        # Prepend initial 1.0
        initial_points = np.ones((simulations, 1))
        all_paths = np.hstack([initial_points, cum_paths])

        # Compute max drawdown per path
        running_max = np.maximum.accumulate(all_paths, axis=1)
        drawdowns = (running_max - all_paths) / running_max
        max_drawdowns = np.max(drawdowns, axis=1)

        # Probability of breaching MDD threshold
        breach_count = int(np.sum(max_drawdowns > mdd_threshold))
        breach_prob = float(breach_count / simulations)

        expected_mdd = float(np.mean(max_drawdowns))
        worst_mdd_95 = float(np.percentile(max_drawdowns, 95.0))

        return (breach_prob, expected_mdd, worst_mdd_95)

    def evaluate_portfolio(
        self,
        weights: dict[str, float],
        betas: dict[str, float],
        sectors: dict[str, str],
        vols: dict[str, float],
        historical_portfolio_returns: list[float] | None = None,
        corr_matrix: dict[str, dict[str, float]] | None = None,
    ) -> StressTestAssessment:
        """
        Full portfolio stress test evaluation integrating Historical Replay, CVaR, and Monte Carlo.
        """
        # 1. Historical Scenarios Replay
        scenario_results: list[ScenarioImpactResult] = []
        worst_scenario_name = ""
        worst_scenario_loss = 0.0

        for sc in self.scenarios:
            res = self.replay_stress_scenario(sc, weights, betas, sectors)
            scenario_results.append(res)
            if res.scenario_loss_pct > worst_scenario_loss:
                worst_scenario_loss = res.scenario_loss_pct
                worst_scenario_name = sc.name

        # 2. Portfolio Annualized Volatility Estimation
        tickers = list(weights.keys())
        rho_default = 0.40
        port_var = 0.0
        for i, t_i in enumerate(tickers):
            w_i = weights[t_i]
            v_i = vols.get(t_i, 0.25)
            port_var += (w_i * v_i) ** 2
            for j in range(i + 1, len(tickers)):
                t_j = tickers[j]
                w_j = weights[t_j]
                v_j = vols.get(t_j, 0.25)
                pair_c = rho_default
                if corr_matrix and t_i in corr_matrix and t_j in corr_matrix[t_i]:
                    pair_c = corr_matrix[t_i][t_j]
                port_var += 2.0 * w_i * w_j * pair_c * v_i * v_j

        port_ann_vol = math.sqrt(max(0.0, port_var))
        port_daily_vol = port_ann_vol / math.sqrt(252)

        # 3. VaR & CVaR (95% & 99%)
        if historical_portfolio_returns and len(historical_portfolio_returns) >= 20:
            var_95, cvar_95 = self.calculate_var_cvar(historical_portfolio_returns, confidence=0.95)
            var_99, cvar_99 = self.calculate_var_cvar(historical_portfolio_returns, confidence=0.99)
        else:
            var_95, cvar_95 = self.calculate_parametric_var_cvar(port_ann_vol, confidence=0.95)
            var_99, cvar_99 = self.calculate_parametric_var_cvar(port_ann_vol, confidence=0.99)

        # 4. Monte Carlo Simulation for 60-day MDD breach
        sim_count = self.mc_simulations
        breach_prob, exp_mdd, worst_mdd_95 = self.simulate_monte_carlo_drawdown(
            portfolio_daily_vol=port_daily_vol,
            simulations=sim_count,
            mdd_threshold=0.12,
        )

        # 5. Pre-emptive De-Risking Assessment
        defense_reasons: list[str] = []
        is_triggered = False

        cvar_limit = self.cvar_budget
        loss_limit = self.loss_threshold
        mdd_prob_limit = self.max_mdd_prob

        if cvar_99 > cvar_limit:
            is_triggered = True
            defense_reasons.append(
                f"99% 條件在險價值 (CVaR {cvar_99:.1%}) 超出風險預算上限 ({cvar_limit:.1%})"
            )

        if worst_scenario_loss > loss_limit:
            is_triggered = True
            defense_reasons.append(
                f"極端情境 [{worst_scenario_name}] 預估瞬時虧損 ({worst_scenario_loss:.1%}) "
                f"突破最大耐受門檻 ({loss_limit:.1%})"
            )

        if breach_prob > mdd_prob_limit:
            is_triggered = True
            defense_reasons.append(
                f"未來 60 天內跌破 12% MDD 機率 ({breach_prob:.1%}) 高於安全上限 ({mdd_prob_limit:.1%})"
            )

        # Determine recommended defensive cash and asset scaling
        rec_cash = self.emergency_cash_pct if is_triggered else 0.20
        rec_adjustments: dict[str, float] = {}

        if is_triggered:
            # Scale down total equity to (1 - rec_cash)
            # High-beta (beta > 1.2) or high-vol (vol > 0.30) positions receive additional dampening
            target_equity_sum = 1.0 - rec_cash
            dampened_raw: dict[str, float] = {}

            for t, w in weights.items():
                beta = betas.get(t, 1.0)
                vol = vols.get(t, 0.25)
                dampener = 1.0
                if beta > 1.2:
                    dampener *= 0.70
                if vol > 0.30:
                    dampener *= 0.75
                dampened_raw[t] = w * dampener

            sub_tot = sum(dampened_raw.values())
            if sub_tot > 0:
                scale_ratio = target_equity_sum / sub_tot
                for t, w in dampened_raw.items():
                    rec_adjustments[t] = round(w * scale_ratio, 4)
        else:
            rec_adjustments = dict(weights)

        return StressTestAssessment(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            cvar_99=cvar_99,
            worst_scenario_name=worst_scenario_name,
            worst_scenario_loss_pct=worst_scenario_loss,
            scenario_results=scenario_results,
            mc_mdd_breach_prob=breach_prob,
            mc_expected_mdd=exp_mdd,
            mc_worst_mdd_95=worst_mdd_95,
            is_defense_triggered=is_triggered,
            defense_reasons=defense_reasons,
            recommended_cash_pct=rec_cash,
            recommended_weight_adjustments=rec_adjustments,
        )
