"""
Unit Test Suite: Order Execution Feedback & Real-Time Slippage Analytics (E2)
=============================================================================
Tests execution fill recording, Perold Implementation Shortfall (IS) decomposition,
dynamic Almgren-Chriss (2000) eta calibration, adverse selection anomaly detection,
venue quality scoring, and closed-loop E1 SOR integration.
"""
import pytest

from src.services.order_execution_feedback_service import (
    ExecutionVenue,
    OrderAction,
    OrderExecutionFeedbackService,
)
from src.services.smart_order_routing_service import (
    ExecutionStrategy,
    SmartOrderRoutingService,
)


class MockSettingsRepo:
    def __init__(self, settings: dict):
        self.settings = settings

    def get(self, user_id: str, key: str):
        return self.settings.get(key)


@pytest.fixture
def feedback_service():
    service = OrderExecutionFeedbackService(user_id="test_trader")
    service.clear_buffers()
    return service


def test_record_single_fill_buy_positive_slippage(feedback_service):
    """Verify BUY order slippage: fill price above arrival price produces positive slippage in bps."""
    # Arrival: 150.00, Fill: 150.30 -> +30 cents / 150.00 = +20 bps
    fill = feedback_service.record_fill(
        order_id="ord-001",
        symbol="AAPL",
        action=OrderAction.BUY,
        venue=ExecutionVenue.IBKR,
        fill_price=150.30,
        fill_quantity=100.0,
        arrival_price=150.00,
        fee_usd=1.50,
    )

    assert fill.symbol == "AAPL"
    assert fill.action == OrderAction.BUY
    assert fill.venue == "IBKR"
    assert fill.realized_slippage_bps == 20.0
    assert fill.fee_usd == 1.50
    assert fill.is_anomaly is False
    assert len(feedback_service._fills_buffer) == 1


def test_record_single_fill_sell_positive_slippage(feedback_service):
    """Verify SELL order slippage: fill price below arrival price produces positive slippage in bps."""
    # Arrival: 200.00, Fill: 199.60 -> -40 cents below arrival = +20 bps adverse slippage
    fill = feedback_service.record_fill(
        order_id="ord-002",
        symbol="MSFT",
        action=OrderAction.SELL,
        venue=ExecutionVenue.ETORO,
        fill_price=199.60,
        fill_quantity=50.0,
        arrival_price=200.00,
        fee_usd=0.0,
    )

    assert fill.symbol == "MSFT"
    assert fill.action == OrderAction.SELL
    assert fill.venue == "ETORO"
    assert fill.realized_slippage_bps == 20.0
    assert fill.is_anomaly is False


def test_record_fill_with_market_impact(feedback_service):
    """Verify contemporaneous market impact bps calculation when market price at fill is supplied."""
    fill = feedback_service.record_fill(
        order_id="ord-003",
        symbol="NVDA",
        action=OrderAction.BUY,
        venue=ExecutionVenue.PAPER,
        fill_price=120.24,
        fill_quantity=200.0,
        arrival_price=120.00,
        market_price_at_fill=120.18,  # Market drifted up 15 bps
    )

    assert fill.realized_slippage_bps == 20.0
    assert fill.market_impact_bps == 15.0


def test_adverse_selection_anomaly_detection(feedback_service):
    """Verify static alert threshold and 3-sigma statistical adverse selection alerting."""
    # 1. Static threshold breach (> default 25 bps)
    anomaly_fill = feedback_service.record_fill(
        order_id="ord-bad-01",
        symbol="TSLA",
        action=OrderAction.BUY,
        venue=ExecutionVenue.IBKR,
        fill_price=251.00,
        fill_quantity=10.0,
        arrival_price=250.00,  # 40 bps slippage > 25 bps
    )
    assert anomaly_fill.is_anomaly is True
    assert "exceeded static tolerance" in anomaly_fill.anomaly_reason

    # 2. Statistical 3-sigma outlier check
    feedback_service.clear_buffers()
    # Populate with 10 normal fills around 2.0 bps
    for i in range(10):
        feedback_service.record_fill(
            order_id=f"norm-{i}",
            symbol="GOOGL",
            action=OrderAction.BUY,
            venue=ExecutionVenue.IBKR,
            fill_price=175.00 + (0.01 if i % 2 == 0 else -0.01),
            fill_quantity=10.0,
            arrival_price=175.00,
        )

    # Now inject a 15 bps slippage (below static 25 bps, but > 3-sigma of tiny baseline variance)
    stat_anomaly = feedback_service.record_fill(
        order_id="ord-stat-01",
        symbol="GOOGL",
        action=OrderAction.BUY,
        venue=ExecutionVenue.IBKR,
        fill_price=175.2625,  # 15 bps slippage
        fill_quantity=10.0,
        arrival_price=175.00,
    )
    assert stat_anomaly.is_anomaly is True
    assert "exceeded 3-sigma" in stat_anomaly.anomaly_reason

    recent_anomalies = feedback_service.get_anomaly_fills()
    assert len(recent_anomalies) >= 1


def test_perold_implementation_shortfall_decomposition(feedback_service):
    """
    Verify full Perold Implementation Shortfall (IS) 4-part decomposition:
    Delay Cost, Market Impact, Fee Cost, Unfilled Opportunity Cost, Total Shortfall.
    """
    tot_shares = 1000.0
    arrival_p = 100.00
    first_quote_p = 100.05  # 5 bps delay

    # Child fills
    f1 = feedback_service.record_fill(
        order_id="slice-1",
        symbol="AMZN",
        action=OrderAction.BUY,
        venue=ExecutionVenue.IBKR,
        fill_price=100.10,
        fill_quantity=500.0,
        arrival_price=arrival_p,
        fee_usd=1.00,
    )
    f2 = feedback_service.record_fill(
        order_id="slice-2",
        symbol="AMZN",
        action=OrderAction.BUY,
        venue=ExecutionVenue.IBKR,
        fill_price=100.30,
        fill_quantity=300.0,
        arrival_price=arrival_p,
        fee_usd=0.60,
    )

    report = feedback_service.record_plan_fills(
        plan_id="plan-amzn-001",
        symbol="AMZN",
        action=OrderAction.BUY,
        total_ordered_shares=tot_shares,
        arrival_price=arrival_p,
        fills=[f1, f2],
        venue="IBKR",
        initial_quote_price=first_quote_p,
        final_market_price=100.50,  # Market at close for 200 unfilled shares
    )

    assert report.total_ordered_shares == 1000.0
    assert report.total_filled_shares == 800.0
    assert report.fill_rate_pct == 80.0
    # VWAP: (500 * 100.10 + 300 * 100.30) / 800 = (50050 + 30090) / 800 = 80140 / 800 = 100.175
    assert report.vwap_executed_price == 100.175
    assert report.realized_slippage_bps == 17.50

    # Shortfall Decomposition checks
    decomp = report.shortfall_decomposition
    assert decomp.delay_cost_bps == 5.0
    assert decomp.market_impact_bps == 12.50
    assert decomp.fee_cost_bps > 0.0
    assert decomp.unfilled_opportunity_cost_bps == 10.0  # (0.50 / 100.0) * (200/1000) * 10000 = 10.0
    assert decomp.total_shortfall_bps > 20.0
    assert decomp.total_shortfall_usd > 200.0
    assert report.execution_efficiency > 0.80


def test_completely_unfilled_plan_shortfall(feedback_service):
    """Verify handling of completely unfilled execution plans."""
    report = feedback_service.record_plan_fills(
        plan_id="plan-empty-001",
        symbol="NFLX",
        action=OrderAction.BUY,
        total_ordered_shares=500.0,
        arrival_price=600.00,
        fills=[],
        venue="ETORO",
        final_market_price=606.00,  # 1.0% = 100 bps opportunity loss
    )

    assert report.total_filled_shares == 0.0
    assert report.fill_rate_pct == 0.0
    assert report.execution_efficiency == 0.0
    assert report.shortfall_decomposition.unfilled_opportunity_cost_bps == 100.0
    assert report.shortfall_decomposition.total_shortfall_usd == 3000.0  # 6.00 * 500


def test_almgren_chriss_dynamic_eta_calibration(feedback_service):
    """Verify Almgren-Chriss Square-Root law and EWMA parameter calibration for eta."""
    sym = "AMD"
    adv = 100000.0
    order_qty = 1000.0  # participation = 0.01 -> sqrt = 0.1
    # Realized slippage = 20.0 bps = 0.0020
    # Observed eta = 0.0020 / 0.1 = 0.02
    initial_default_eta = feedback_service.default_eta  # 0.15
    decay = 0.20

    updated_eta = feedback_service.calibrate_almgren_chriss_eta(
        symbol=sym,
        order_quantity=order_qty,
        adv_20=adv,
        realized_slippage_bps=20.0,
        decay_rate=decay,
    )

    # Expected EWMA: (1 - 0.20) * 0.15 + 0.20 * 0.02 = 0.12 + 0.004 = 0.124
    expected_eta = round((1.0 - decay) * initial_default_eta + decay * 0.02, 4)
    assert abs(updated_eta - expected_eta) < 0.001
    assert feedback_service.get_calibrated_eta(sym) == updated_eta

    # Test expected slippage query
    # qty = 4000 shares -> part = 0.04 -> sqrt = 0.2
    # expected slippage = 0.124 * 0.2 * 10000 = 248.0 bps
    expected_bps = feedback_service.estimate_expected_slippage(sym, 4000.0, adv)
    assert expected_bps > 0.0


def test_venue_quality_benchmarking_and_scoring(feedback_service):
    """Verify cross-venue benchmarking metrics and composite 0-100 quality scoring."""
    # Low-slippage venue (IBKR)
    for _ in range(5):
        feedback_service.record_fill(
            order_id="ibkr-ord",
            symbol="SPY",
            action=OrderAction.BUY,
            venue=ExecutionVenue.IBKR,
            fill_price=500.05,  # 1.0 bps slippage
            fill_quantity=100.0,
            arrival_price=500.00,
            fee_usd=0.35,
        )

    # Higher-slippage venue (ETORO)
    for _ in range(5):
        feedback_service.record_fill(
            order_id="etoro-ord",
            symbol="SPY",
            action=OrderAction.BUY,
            venue=ExecutionVenue.ETORO,
            fill_price=500.60,  # 12.0 bps slippage
            fill_quantity=100.0,
            arrival_price=500.00,
            fee_usd=1.50,
        )

    venue_report = feedback_service.get_venue_quality_report()
    assert "IBKR" in venue_report
    assert "ETORO" in venue_report

    ibkr_metrics = venue_report["IBKR"]
    etoro_metrics = venue_report["ETORO"]

    assert ibkr_metrics.avg_slippage_bps < etoro_metrics.avg_slippage_bps
    assert ibkr_metrics.quality_score > etoro_metrics.quality_score
    assert ibkr_metrics.quality_score >= 80.0


def test_slippage_distribution_statistics(feedback_service):
    """Verify empirical distribution summary statistics (mean, median, std, p95)."""
    # Empty case
    empty_dist = feedback_service.get_slippage_distribution()
    assert empty_dist["count"] == 0.0

    # Ingest multiple fills
    slippages = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
    for idx, s in enumerate(slippages):
        p_arr = 100.0
        p_fill = p_arr * (1.0 + s / 10000.0)
        feedback_service.record_fill(
            order_id=f"dist-{idx}",
            symbol="QQQ",
            action=OrderAction.BUY,
            venue=ExecutionVenue.IBKR,
            fill_price=p_fill,
            fill_quantity=50.0,
            arrival_price=p_arr,
        )

    dist = feedback_service.get_slippage_distribution("QQQ")
    assert dist["count"] == 10.0
    assert dist["mean_bps"] == 11.0
    assert dist["min_bps"] == 2.0
    assert dist["max_bps"] == 20.0
    assert dist["p95_bps"] >= 18.0


def test_e1_sor_and_e2_feedback_bidirectional_integration(feedback_service):
    """
    Verify E1 Smart Order Routing and E2 Execution Feedback work in a closed loop:
    1. Calibrated eta expands slicing execution window.
    2. Slicing child order fills automatically sync back to feedback service.
    """
    sor_service = SmartOrderRoutingService(
        user_id="test_trader",
        feedback_service=feedback_service,
    )

    # Force a high eta for illiquid stock to trigger adaptive window expansion
    feedback_service._impact_states["ILLIQ"] = feedback_service._impact_states.get(
        "ILLIQ",
        type(
            "ImpactState",
            (),
            {"calibrated_eta": 0.85, "sample_count": 10, "last_updated": "NOW", "baseline_eta": 0.15},
        )(),
    )

    # Generate plan with high expected impact -> window should expand above default 30 min
    plan = sor_service.generate_plan(
        symbol="ILLIQ",
        action=OrderAction.BUY,
        requested_quantity=1500.0,
        arrival_price=50.0,
        adv_20=100000.0,  # 1.5% ADV
        random_seed=42,
    )

    assert plan.execution_window_minutes > 30

    # Record a fill on slice 1
    sor_service.record_fill(
        plan=plan,
        slice_index=1,
        filled_quantity=plan.child_orders[0].target_quantity,
        filled_price=50.05,
    )

    # Verify fill was synchronized into E2 feedback service
    synced_fills = [f for f in feedback_service._fills_buffer if f.symbol == "ILLIQ"]
    assert len(synced_fills) == 1
    assert synced_fills[0].symbol == "ILLIQ"
    assert synced_fills[0].realized_slippage_bps == 10.0


def test_custom_settings_repo_overrides():
    """Verify settings repository properly overrides feedback service defaults."""
    mock_settings = MockSettingsRepo({
        "execution_feedback_enabled": True,
        "execution_slippage_alert_threshold_bps": 12.5,
        "almgren_chriss_eta_default": 0.28,
        "execution_dynamic_eta_calibration": False,
    })
    service = OrderExecutionFeedbackService(user_id="custom_user", settings_repo=mock_settings)

    assert service.is_enabled is True
    assert service.slippage_alert_threshold_bps == 12.5
    assert service.default_eta == 0.28
    assert service.dynamic_calibration_enabled is False
