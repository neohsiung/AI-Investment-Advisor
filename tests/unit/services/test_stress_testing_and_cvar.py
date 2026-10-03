"""
Unit Tests for StressTestingService and CVaR Tail Risk Defense (M5)
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from src.services.stress_testing_service import (
    StressScenario,
    StressTestAssessment,
    StressTestingService,
)


class DummySettingsService:
    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)


class TestStressTestingService:
    def test_replay_historical_stress_scenarios(self):
        """Test replaying 2008 GFC, 2020 COVID, and other built-in scenarios."""
        service = StressTestingService()
        weights = {"AAPL": 0.40, "JPM": 0.30, "XOM": 0.30}
        betas = {"AAPL": 1.20, "JPM": 1.10, "XOM": 0.80}
        sectors = {"AAPL": "Technology", "JPM": "Financials", "XOM": "Energy"}

        # 2008 GFC scenario check
        gfc = next(s for s in service.scenarios if s.name == "2008_GFC")
        res = service.replay_stress_scenario(gfc, weights, betas, sectors)

        assert res.scenario_name == "2008_GFC"
        assert res.scenario_loss_pct > 0.15  # GFC shock should inflict substantial drawdown
        # AAPL shock = 1.2 * (-0.22) + (-0.08) = -0.344
        # JPM shock = 1.1 * (-0.22) + (-0.14) = -0.382
        # XOM shock = 0.8 * (-0.22) + (-0.15) = -0.326
        # Expected loss = 0.4*0.344 + 0.3*0.382 + 0.3*0.326 = 0.1376 + 0.1146 + 0.0978 = 0.350
        assert math.isclose(res.scenario_loss_pct, 0.350, abs_tol=1e-3)
        assert len(res.asset_contributions) == 3

    def test_var_and_cvar_historical(self):
        """Test historical VaR and CVaR calculations on a return series."""
        service = StressTestingService()
        np.random.seed(42)
        # Normal-ish returns with occasional severe fat tail
        returns = list(np.random.normal(0.0005, 0.015, 200))
        returns.extend([-0.05, -0.06, -0.08])  # Severe tail losses

        var_95, cvar_95 = service.calculate_var_cvar(returns, confidence=0.95)
        var_99, cvar_99 = service.calculate_var_cvar(returns, confidence=0.99)

        assert var_95 > 0
        assert var_99 > var_95
        assert cvar_95 >= var_95
        assert cvar_99 >= var_99
        assert cvar_99 > cvar_95

    def test_var_and_cvar_parametric(self):
        """Test 1-day parametric normal VaR and CVaR."""
        service = StressTestingService()
        # High vol vs low vol
        low_var, low_cvar = service.calculate_parametric_var_cvar(annualized_vol=0.10, confidence=0.99)
        high_var, high_cvar = service.calculate_parametric_var_cvar(annualized_vol=0.30, confidence=0.99)

        assert low_var > 0
        assert low_cvar > low_var
        assert high_var > low_var * 2.5
        assert high_cvar > low_cvar * 2.5

    def test_monte_carlo_drawdown_simulation(self):
        """Test 1,000-path Monte Carlo drawdown simulation."""
        service = StressTestingService()
        # Moderate daily vol (16% annualized -> ~1.0% daily)
        prob_mod, exp_mod, worst_mod = service.simulate_monte_carlo_drawdown(
            portfolio_daily_vol=0.010,
            days=60,
            simulations=500,
            mdd_threshold=0.12,
            seed=42,
        )

        # High daily vol (40% annualized -> ~2.5% daily)
        prob_high, exp_high, worst_high = service.simulate_monte_carlo_drawdown(
            portfolio_daily_vol=0.025,
            days=60,
            simulations=500,
            mdd_threshold=0.12,
            seed=42,
        )

        assert 0.0 <= prob_mod <= 1.0
        assert 0.0 <= prob_high <= 1.0
        assert prob_high > prob_mod  # Higher vol definitely has higher probability of breaching 12% MDD
        assert worst_high > worst_mod
        assert exp_high > exp_mod

    def test_evaluate_portfolio_defense_triggered(self):
        """Test that a high-risk portfolio triggers pre-emptive de-risking."""
        settings = DummySettingsService({
            "stress_test_cvar_budget": 0.04,        # Strict 4% CVaR budget
            "stress_test_loss_threshold": 0.15,      # Strict 15% stress loss threshold
            "stress_test_emergency_cash_pct": 0.40,  # 40% emergency cash
        })
        service = StressTestingService(settings_service=settings)

        # Aggressive tech portfolio with high beta & high volatility
        weights = {"NVDA": 0.50, "TSLA": 0.50}
        betas = {"NVDA": 1.80, "TSLA": 2.00}
        sectors = {"NVDA": "Technology", "TSLA": "Consumer Discretionary"}
        vols = {"NVDA": 0.45, "TSLA": 0.50}

        assessment = service.evaluate_portfolio(weights, betas, sectors, vols)
        assert isinstance(assessment, StressTestAssessment)
        assert assessment.is_defense_triggered is True
        assert len(assessment.defense_reasons) > 0
        assert assessment.recommended_cash_pct == 0.40

        # High beta / high vol positions should be dampened to sum to (1 - 0.40) = 0.60
        total_adj_equity = sum(assessment.recommended_weight_adjustments.values())
        assert math.isclose(total_adj_equity, 0.60, abs_tol=1e-3)

    def test_evaluate_portfolio_safe_no_defense(self):
        """Test that a low-volatility, defensive portfolio remains in normal operation."""
        settings = DummySettingsService({
            "stress_test_cvar_budget": 0.08,
            "stress_test_loss_threshold": 0.20,
            "stress_test_max_mdd_prob": 0.50,
            "stress_test_emergency_cash_pct": 0.35,
        })
        service = StressTestingService(settings_service=settings)

        # Defensive utility & consumer staples portfolio
        weights = {"JNJ": 0.50, "PG": 0.50}
        betas = {"JNJ": 0.50, "PG": 0.45}
        sectors = {"JNJ": "Healthcare", "PG": "Consumer Staples"}
        vols = {"JNJ": 0.12, "PG": 0.11}

        assessment = service.evaluate_portfolio(weights, betas, sectors, vols)
        assert assessment.is_defense_triggered is False
        assert len(assessment.defense_reasons) == 0
        assert assessment.recommended_cash_pct == 0.20
        # Weights should remain unchanged
        assert assessment.recommended_weight_adjustments == weights

    def test_custom_scenario_injection(self):
        """Test evaluating custom stress scenarios."""
        custom_scenario = StressScenario(
            name="GEOPOLITICAL_OIL_SHOCK",
            description="Middle East conflict escalates, energy spikes, equities tumble",
            market_shock_pct=-0.10,
            volatility_multiplier=2.2,
            sector_shocks={"Energy": 0.15, "Airlines": -0.25},
        )
        service = StressTestingService(custom_scenarios=[custom_scenario])

        weights = {"DAL": 0.50, "XOM": 0.50}
        betas = {"DAL": 1.30, "XOM": 0.80}
        sectors = {"DAL": "Airlines", "XOM": "Energy"}
        vols = {"DAL": 0.35, "XOM": 0.25}

        assessment = service.evaluate_portfolio(weights, betas, sectors, vols)
        assert len(assessment.scenario_results) == 1
        assert assessment.worst_scenario_name == "GEOPOLITICAL_OIL_SHOCK"
        assert assessment.worst_scenario_loss_pct > 0.0
