"""Unit tests for M7: Cross-Asset Volatility Spillover & Contagion Shielder Service."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.services.cross_asset_volatility_spillover_service import (
    CrossAssetVolatilitySpilloverService,
    ContagionSpilloverImpact,
    SpilloverContagionAssessment,
)
from src.services.intraday_liquidity_circuit_breaker_service import (
    IntradayLiquidityCircuitBreakerService,
    CircuitBreakerState,
    ShockTriggerType,
    CircuitBreakerStatus,
)
from src.services.adaptive_execution_slippage_compensator import (
    AdaptiveExecutionSlippageCompensator,
)
from src.services.portfolio_adaptive_intelligence_service import (
    PortfolioAdaptiveIntelligenceService,
)


@pytest.fixture
def compensator():
    """Fresh instance of AdaptiveExecutionSlippageCompensator."""
    return AdaptiveExecutionSlippageCompensator(user_id="test_m7_user")


@pytest.fixture
def circuit_breaker_service():
    """Fresh instance of IntradayLiquidityCircuitBreakerService."""
    return IntradayLiquidityCircuitBreakerService(user_id="test_m7_user")


@pytest.fixture
def spillover_service(circuit_breaker_service, compensator):
    """Configured CrossAssetVolatilitySpilloverService instance."""
    service = CrossAssetVolatilitySpilloverService(
        user_id="test_m7_user",
        circuit_breaker_service=circuit_breaker_service,
        slippage_compensator=compensator,
    )
    # Seed high correlation between NVDA and TSM / AMD
    service.update_correlations({
        "NVDA": {"AMD": 0.85, "TSM": 0.78, "AAPL": 0.50, "XOM": 0.10},
        "AMD": {"NVDA": 0.85, "TSM": 0.75, "AAPL": 0.45, "XOM": 0.05},
        "TSM": {"NVDA": 0.78, "AMD": 0.75, "AAPL": 0.52, "XOM": 0.12},
    })
    service.update_sector_map({
        "NVDA": "Semiconductors",
        "AMD": "Semiconductors",
        "TSM": "Semiconductors",
        "AAPL": "Consumer Electronics",
        "XOM": "Energy",
    })
    return service


class TestCrossAssetVolatilitySpilloverService:
    def test_no_active_shocks_clean_state(self, spillover_service):
        assessment = spillover_service.evaluate_contagion()
        assert assessment.is_active is False
        assert len(assessment.active_sources) == 0
        assert assessment.total_impacted_tickers == 0
        assert assessment.aggregate_cash_expansion_pct == 0.0
        assert assessment.max_slippage_multiplier == 1.0

    def test_single_leader_shock_propagation(self, spillover_service, compensator):
        # Register a shock on NVDA
        now = datetime.now(timezone.utc)
        spillover_service.register_shock(
            source_ticker="NVDA",
            triggered_at=now,
            cooldown_until=now + timedelta(minutes=15),
            reason="Spread exploded on major earnings whisper",
        )

        assessment = spillover_service.evaluate_contagion(universe_tickers=["NVDA", "AMD", "TSM", "AAPL", "XOM"])
        assert assessment.is_active is True
        assert "NVDA" in assessment.active_sources

        # AMD and TSM should be heavily impacted
        assert "AMD" in assessment.impacts
        amd_impact = assessment.impacts["AMD"]
        assert amd_impact.source_ticker == "NVDA"
        assert amd_impact.correlation == 0.85
        assert amd_impact.same_sector is True
        assert amd_impact.spillover_intensity > 0.80
        assert amd_impact.elevated_slippage_multiplier > 1.80
        assert amd_impact.additional_cash_buffer_pct > 0.10

        # Compensator should have received elevated multiplier
        amd_metrics = compensator.get_metrics("AMD")
        assert amd_metrics.slippage_multiplier >= 1.80

        # XOM has very low correlation and different sector -> should NOT be impacted
        assert "XOM" not in assessment.impacts

    def test_global_circuit_breaker_spread(self, spillover_service, compensator):
        now = datetime.now(timezone.utc)
        spillover_service.register_shock(
            source_ticker="GLOBAL",
            triggered_at=now,
            cooldown_until=now + timedelta(minutes=30),
            reason="Systemic Flash Crash",
        )

        assessment = spillover_service.evaluate_contagion(universe_tickers=["AAPL", "MSFT", "XOM"])
        assert assessment.is_active is True
        assert assessment.aggregate_cash_expansion_pct == spillover_service.max_cash_expansion_pct
        assert assessment.max_slippage_multiplier == spillover_service.max_slippage_elevation

        # All tickers in universe should be impacted
        assert "AAPL" in assessment.impacts
        assert "MSFT" in assessment.impacts
        assert "XOM" in assessment.impacts

    def test_circuit_breaker_listener_auto_subscription(self, circuit_breaker_service, spillover_service, compensator):
        # Trigger circuit breaker on NVDA via IntradayLiquidityCircuitBreakerService
        cb_status = circuit_breaker_service.manual_trigger(
            symbol="NVDA",
            reason="Operator emergency halt",
            cooldown_minutes=20,
        )

        # Spillover service should have automatically captured the event
        assessment = spillover_service.evaluate_contagion()
        assert assessment.is_active is True
        assert "NVDA" in assessment.active_sources
        assert "AMD" in assessment.impacts

        # Now resume NVDA in circuit breaker
        circuit_breaker_service.resume(symbol="NVDA")

        # Spillover should auto-clear
        assessment_resumed = spillover_service.evaluate_contagion()
        assert assessment_resumed.is_active is False
        assert len(assessment_resumed.active_sources) == 0
        assert compensator.get_spillover_multiplier("AMD") == 1.0

    def test_time_decay_half_life(self, spillover_service):
        now = datetime.now(timezone.utc)
        past_time = now - timedelta(minutes=30)  # Exactly 1 half-life ago
        spillover_service.register_shock(
            source_ticker="NVDA",
            triggered_at=past_time,
            cooldown_until=now + timedelta(minutes=15),
            reason="Decaying liquidity shock",
        )

        assessment = spillover_service.evaluate_contagion(universe_tickers=["AMD"])
        if "AMD" in assessment.impacts:
            impact = assessment.impacts["AMD"]
            # Raw intensity ~ 0.7*0.85 + 0.3*1.0 = 0.895
            # Decayed after 1 half-life ~ 0.895 * 0.5 ~ 0.4475
            assert impact.spillover_intensity < 0.60
            assert impact.spillover_intensity > 0.35

    def test_portfolio_adaptive_intelligence_cash_integration(self, spillover_service):
        d1 = PortfolioAdaptiveIntelligenceService(
            user_id="test_m7_user",
            spillover_service=spillover_service,
        )

        # Baseline diagnose with no shocks
        weights = {"AAPL": 0.40, "MSFT": 0.40, "CASH": 0.20}
        report_normal = d1.diagnose_portfolio(current_weights=weights)
        normal_cash = report_normal.rebalance_recommendation["target_weights"]["CASH"]

        # Register shock on leader
        spillover_service.register_shock(
            source_ticker="NVDA",
            reason="Spillover shock test",
        )

        report_shock = d1.diagnose_portfolio(current_weights=weights)
        shock_cash = report_shock.rebalance_recommendation["target_weights"]["CASH"]

        # Defensive cash should have expanded
        assert shock_cash > normal_cash


class TestSpilloverApiEndpoints:
    def test_get_spillover_contagion_api_flow(self, spillover_service):
        from src.api.v1.endpoints.execution import get_spillover_contagion_status

        # 1. Clean state
        clean_res = get_spillover_contagion_status(service=spillover_service)
        assert clean_res.status == "success"
        assert clean_res.is_active is False

        # 2. Add shock
        spillover_service.register_shock(source_ticker="NVDA", reason="API test shock")
        shock_res = get_spillover_contagion_status(service=spillover_service)
        assert shock_res.status == "success"
        assert shock_res.is_active is True
        assert "NVDA" in shock_res.active_sources
        assert shock_res.total_impacted_tickers > 0
        assert "AMD" in shock_res.impacts
