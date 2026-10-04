"""
Unit Test Suite: Adaptive Execution Slippage Compensator & Feedback Loop (P6)
=============================================================================
Tests slippage deviation calculation, EWMA multiplier calibration, adverse
selection penalty buffering, closed-loop SOR adaptation, Opportunity Cost friction
injection, and RESTful execution endpoints.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.execution import router as execution_router
from src.services.adaptive_execution_slippage_compensator import (
    AdaptiveExecutionSlippageCompensator,
    SlippageCompensationMetrics,
)
from src.services.opportunity_cost_service import OpportunityCostService
from src.services.order_execution_feedback_service import (
    ExecutionVenue,
    OrderAction,
    OrderExecutionFeedbackService,
)
from src.services.shadow_promotion_orchestrator import ShadowPromotionOrchestrator
from src.services.smart_order_routing_service import (
    ExecutionStrategy,
    SmartOrderRoutingService,
)


@pytest.fixture
def api_client(compensator):
    app = FastAPI()
    app.include_router(execution_router, prefix="/api/v1/execution")
    return TestClient(app)


class MockSettingsRepo:
    def __init__(self, settings: dict):
        self.settings = settings

    def get(self, user_id: str, key: str):
        return self.settings.get(key)


@pytest.fixture
def compensator():
    service = AdaptiveExecutionSlippageCompensator(user_id="test_trader")
    service.clear_metrics()
    return service


def test_record_fill_and_ewma_calibration(compensator):
    """Verify that recording a fill correctly updates EWMA multiplier and metrics."""
    # Arrival: 100.0, Fill: 100.30 -> +30 bps slippage
    # With ADV=100,000, qty=10 -> participation rate=0.0001, sqrt=0.01
    # Model expected = 0.15 * 0.01 * 10000 = 15.0 bps
    # Observed ratio: 30 / 15 = 2.0x
    fill = compensator.record_fill(
        order_id="fill-001",
        symbol="AAPL",
        action=OrderAction.BUY,
        venue=ExecutionVenue.IBKR,
        fill_price=100.30,
        fill_quantity=10.0,
        arrival_price=100.00,
        adv_20=100000.0,
    )

    assert fill.symbol == "AAPL"
    assert fill.realized_slippage_bps == 30.0

    metrics = compensator.get_metrics("AAPL")
    assert metrics.sample_count == 1
    assert metrics.slippage_multiplier > 1.0  # Should be elevated above 1.0
    assert metrics.calibrated_effective_slippage_bps > 15.0
    assert metrics.calibrated_effective_slippage_pct > 0.0015


def test_adverse_selection_penalty_buffer(compensator):
    """Verify that toxic/anomaly slippage triggers the adverse selection safety penalty buffer."""
    # Severe slippage: Arrival 100.0, Fill 100.60 -> +60 bps (breaches default 25 bps anomaly threshold)
    fill = compensator.record_fill(
        order_id="fill-002",
        symbol="TSLA",
        action=OrderAction.BUY,
        venue=ExecutionVenue.PAPER,
        fill_price=100.60,
        fill_quantity=500.0,
        arrival_price=100.00,
        adv_20=50000.0,
    )

    assert fill.is_anomaly is True
    metrics = compensator.get_metrics("TSLA")
    assert metrics.adverse_selection_count == 1
    assert metrics.adverse_penalty_bps == compensator.adverse_penalty_bps
    # Effective slippage should reflect base * mult + penalty
    assert metrics.calibrated_effective_slippage_bps >= (metrics.expected_slippage_bps_mean * metrics.slippage_multiplier + 5.0)


def test_sor_adaptation_high_slippage_regime(compensator):
    """Verify SOR adaptation in high slippage regime recommends finer slicing and wider window."""
    # Inject multiple high-slippage fills to drive multiplier up
    for i in range(3):
        compensator.record_fill(
            order_id=f"fill-high-{i}",
            symbol="NVDA",
            action=OrderAction.BUY,
            venue=ExecutionVenue.IBKR,
            fill_price=100.50,
            fill_quantity=1000.0,
            arrival_price=100.00,
            adv_20=50000.0,
        )

    params = compensator.get_sor_adaptation_parameters(
        symbol="NVDA",
        base_slices=5,
        base_window_minutes=30,
        base_max_slippage_bps=35.0,
    )

    assert params.strategy_hint == "AGGRESSIVE_SLICING"
    assert params.recommended_slices > 5
    assert params.recommended_window_minutes >= 30
    assert params.recommended_jitter_pct > 0.15


def test_sor_adaptation_low_slippage_regime(compensator):
    """Verify SOR adaptation in low slippage regime allows streamlined execution."""
    # Manually configure low-slippage state
    compensator._metrics_map["SPY"] = SlippageCompensationMetrics(
        symbol="SPY",
        realized_slippage_bps_mean=2.0,
        expected_slippage_bps_mean=10.0,
        slippage_multiplier=0.60,
        adverse_selection_count=0,
        adverse_penalty_bps=0.0,
        calibrated_effective_slippage_bps=6.0,
        calibrated_effective_slippage_pct=0.0006,
        sample_count=10,
        last_updated="2026-10-04T12:00:00Z",
    )

    params = compensator.get_sor_adaptation_parameters(
        symbol="SPY",
        base_slices=8,
        base_window_minutes=40,
    )

    assert params.strategy_hint == "STREAMLINED_EXECUTION"
    assert params.recommended_slices <= 8
    assert params.recommended_window_minutes <= 40


def test_sor_closed_loop_integration(compensator):
    """Verify that SmartOrderRoutingService natively uses compensator for plan generation."""
    # Seed high slippage for AMD
    for i in range(2):
        compensator.record_fill(
            order_id=f"amd-{i}",
            symbol="AMD",
            action=OrderAction.BUY,
            venue=ExecutionVenue.IBKR,
            fill_price=100.40,
            fill_quantity=1000.0,
            arrival_price=100.00,
            adv_20=50000.0,
        )

    sor = SmartOrderRoutingService(
        user_id="test_trader",
        feedback_service=compensator,
    )

    plan = sor.generate_plan(
        symbol="AMD",
        action=OrderAction.BUY,
        requested_quantity=2000.0,
        arrival_price=100.00,
        adv_20=500000.0,
    )

    # When elevated slippage is present, slices should be scaled up
    assert plan.num_slices >= 5
    assert len(plan.child_orders) == plan.num_slices
    assert plan.execution_window_minutes >= 30


def test_opportunity_cost_closed_loop_integration(compensator):
    """Verify that OpportunityCostService dynamically raises friction hurdles when target has high slippage."""
    # Seed high slippage on target candidate MEME
    for i in range(2):
        compensator.record_fill(
            order_id=f"meme-{i}",
            symbol="MEME",
            action=OrderAction.BUY,
            venue=ExecutionVenue.PAPER,
            fill_price=50.35,  # 70 bps slippage
            fill_quantity=1000.0,
            arrival_price=50.00,
            adv_20=10000.0,
        )

    opp_service = OpportunityCostService(
        user_id="test_trader",
        slippage_compensator=compensator,
    )

    # Compare static friction vs dynamic friction
    default_friction = opp_service.calculate_roundtrip_friction()
    calibrated_friction = opp_service.calculate_roundtrip_friction(
        sell_ticker="AAPL",
        buy_ticker="MEME",
    )

    # MEME high slippage must elevate roundtrip friction above standard
    assert calibrated_friction > default_friction

    # Evaluate swap: candidate requires a significantly higher edge to justify displacing holding
    decision = opp_service.evaluate_swap(
        holding_ticker="AAPL",
        candidate_ticker="MEME",
        holding_score=7.0,
        candidate_score=7.8,  # Only 0.8 edge
    )
    # The elevated friction should reject the swap or demand higher hurdle
    assert decision.friction_hurdle > 0.0


def test_shadow_orchestrator_initialization_with_compensator(compensator):
    """Verify ShadowPromotionOrchestrator accepts and wires compensator."""
    orchestrator = ShadowPromotionOrchestrator(
        user_id="test_trader",
        slippage_compensator=compensator,
    )

    assert orchestrator.slippage_compensator is compensator
    assert orchestrator.opportunity_cost.slippage_compensator is compensator
    assert orchestrator.sor_service.feedback_service is compensator


def test_execution_api_endpoints(api_client):
    """Verify FastAPI endpoints under /api/v1/execution."""
    client = api_client

    # 1. Post fill feedback
    feedback_payload = {
        "order_id": "test-api-01",
        "symbol": "GOOGL",
        "action": "BUY",
        "venue": "IBKR",
        "fill_price": 180.36,
        "fill_quantity": 50.0,
        "arrival_price": 180.00,
        "fee_usd": 1.0,
        "adv_20": 200000.0,
    }
    resp = client.post("/api/v1/execution/slippage/feedback", json=feedback_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["symbol"] == "GOOGL"
    assert data["realized_slippage_bps"] == 20.0

    # 2. Get metrics for GOOGL
    resp_metric = client.get("/api/v1/execution/slippage/metrics/GOOGL")
    assert resp_metric.status_code == 200
    m_data = resp_metric.json()
    assert m_data["symbol"] == "GOOGL"
    assert m_data["sample_count"] >= 1

    # 3. Get SOR recommendations
    resp_rec = client.get("/api/v1/execution/slippage/recommendations/GOOGL?base_slices=5")
    assert resp_rec.status_code == 200
    rec_data = resp_rec.json()
    assert rec_data["status"] == "success"
    assert "recommended_slices" in rec_data

    # 4. Get Friction
    resp_fric = client.get("/api/v1/execution/slippage/friction?sell_ticker=AAPL&buy_ticker=GOOGL")
    assert resp_fric.status_code == 200
    fric_data = resp_fric.json()
    assert fric_data["status"] == "success"
    assert fric_data["total_roundtrip_friction"] > 0.0
