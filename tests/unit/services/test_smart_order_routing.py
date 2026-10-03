"""
Unit Test Suite: Smart Order Routing & Liquidity-Aware Execution Service (E1)
=============================================================================
Verifies ADV constraints, TWAP randomized slicing, VWAP U-Curve weighting,
real-time slippage monitoring, and circuit breaker tripping.
"""
import pytest

from src.services.smart_order_routing_service import (
    ChildOrderStatus,
    ExecutionStrategy,
    OrderAction,
    SmartOrderRoutingService,
)


class MockSettingsRepo:
    def __init__(self, settings: dict):
        self.settings = settings

    def get(self, user_id: str, key: str):
        return self.settings.get(key)


@pytest.fixture
def sor_service():
    return SmartOrderRoutingService(user_id="test_user")


def test_adv_constraint_and_rollover_clamping(sor_service):
    """Verify orders exceeding ADV threshold are clamped with remainder diverted to rollover queue."""
    # ADV: 100,000 shares; limit = 1.5% -> 1,500 shares max
    plan = sor_service.generate_plan(
        symbol="AAPL",
        action=OrderAction.BUY,
        requested_quantity=3500.0,
        arrival_price=150.0,
        adv_20=100000.0,
        random_seed=42,
    )

    assert plan.symbol == "AAPL"
    assert plan.action == OrderAction.BUY
    assert plan.total_requested_quantity == 3500.0
    assert plan.adv_limit_pct == 0.015
    assert plan.approved_quantity == 1500.0
    assert plan.unfilled_rollover_quantity == 2000.0
    assert plan.status == "PLANNED"


def test_order_within_adv_fully_approved(sor_service):
    """Verify orders within ADV limit are approved with zero rollover."""
    plan = sor_service.generate_plan(
        symbol="MSFT",
        action=OrderAction.BUY,
        requested_quantity=800.0,
        arrival_price=400.0,
        adv_20=100000.0,
        random_seed=42,
    )

    assert plan.approved_quantity == 800.0
    assert plan.unfilled_rollover_quantity == 0.0


def test_small_order_direct_limit_routing(sor_service):
    """Verify small dollar orders bypass multi-slice execution to avoid commission drag."""
    # Value: 2 shares * $100 = $200 (< $500 threshold)
    plan = sor_service.generate_plan(
        symbol="INTC",
        action=OrderAction.BUY,
        requested_quantity=2.0,
        arrival_price=100.0,
        adv_20=500000.0,
        random_seed=42,
    )

    assert plan.strategy == ExecutionStrategy.DIRECT_LIMIT
    assert plan.num_slices == 1
    assert len(plan.child_orders) == 1
    assert plan.child_orders[0].target_quantity == 2.0
    assert plan.child_orders[0].planned_delay_seconds == 0.0


def test_adaptive_twap_slicing_and_exact_sum(sor_service):
    """Verify TWAP slices sum up exactly to approved quantity and exhibit non-decreasing timestamps."""
    approved_target = 600.0
    plan = sor_service.generate_plan(
        symbol="NVDA",
        action=OrderAction.BUY,
        requested_quantity=approved_target,
        arrival_price=120.0,
        adv_20=1000000.0,
        execution_window_minutes=30,
        num_slices=6,
        force_strategy=ExecutionStrategy.TWAP,
        random_seed=123,
    )

    assert plan.strategy == ExecutionStrategy.TWAP
    assert plan.num_slices == 6
    assert len(plan.child_orders) == 6

    # Verify exact conservation of shares
    total_sliced = sum(c.target_quantity for c in plan.child_orders)
    assert abs(total_sliced - approved_target) < 1e-4

    # Verify monotonicity of scheduled delays
    delays = [c.planned_delay_seconds for c in plan.child_orders]
    assert delays[0] == 0.0
    for i in range(1, len(delays)):
        assert delays[i] >= delays[i - 1]


def test_vwap_u_curve_weighting(sor_service):
    """Verify VWAP strategy applies bimodal U-Curve distribution (open/close peaks > midday)."""
    approved_target = 1000.0
    plan = sor_service.generate_plan(
        symbol="TSLA",
        action=OrderAction.BUY,
        requested_quantity=approved_target,
        arrival_price=220.0,
        adv_20=2000000.0,
        execution_window_minutes=60,
        num_slices=7,
        force_strategy=ExecutionStrategy.VWAP,
        random_seed=42,
    )

    assert plan.strategy == ExecutionStrategy.VWAP
    assert plan.num_slices == 7

    # Verify exact conservation of shares
    total_sliced = sum(c.target_quantity for c in plan.child_orders)
    assert abs(total_sliced - approved_target) < 1e-4

    # Verify U-Curve: Boundary slices (first & last) should be strictly greater than center slice (index 3)
    first_slice_qty = plan.child_orders[0].target_quantity
    mid_slice_qty = plan.child_orders[3].target_quantity
    last_slice_qty = plan.child_orders[6].target_quantity

    assert first_slice_qty > mid_slice_qty
    assert last_slice_qty > mid_slice_qty


def test_fill_recording_and_slippage_metrics(sor_service):
    """Verify recording slice fills correctly computes VWAP executed price, slippage bps, and efficiency."""
    plan = sor_service.generate_plan(
        symbol="SPY",
        action=OrderAction.BUY,
        requested_quantity=200.0,
        arrival_price=500.0,
        adv_20=5000000.0,
        num_slices=2,
        force_strategy=ExecutionStrategy.TWAP,
        random_seed=42,
    )

    q1 = plan.child_orders[0].target_quantity
    q2 = plan.child_orders[1].target_quantity

    # Fill slice 1 at 500.50 (+10 bps)
    sor_service.record_fill(plan, slice_index=1, filled_quantity=q1, filled_price=500.50)
    assert plan.status == "EXECUTING"
    assert plan.circuit_breaker_triggered is False
    assert plan.child_orders[0].slippage_bps == 10.0

    # Fill slice 2 at 501.00 (+20 bps)
    sor_service.record_fill(plan, slice_index=2, filled_quantity=q2, filled_price=501.00)
    assert plan.status == "COMPLETED"
    assert plan.circuit_breaker_triggered is False
    assert plan.child_orders[1].slippage_bps == 20.0

    # Cumulative execution verification
    expected_avg_price = (q1 * 500.50 + q2 * 501.00) / (q1 + q2)
    assert abs(plan.avg_executed_price - expected_avg_price) < 1e-3
    assert plan.total_slippage_bps > 0
    assert 0.80 <= plan.execution_efficiency <= 1.0


def test_circuit_breaker_on_excessive_buy_slippage(sor_service):
    """Verify circuit breaker trips on excessive slippage, cancels remaining pending child orders."""
    # Default limit is 35 bps
    plan = sor_service.generate_plan(
        symbol="SMCI",
        action=OrderAction.BUY,
        requested_quantity=300.0,
        arrival_price=100.0,
        adv_20=200000.0,
        num_slices=3,
        force_strategy=ExecutionStrategy.TWAP,
        random_seed=42,
    )

    # Slice 1 fills with 60 bps slippage (100.60 vs 100.00) -> Breaches 35 bps limit!
    q1 = plan.child_orders[0].target_quantity
    sor_service.record_fill(plan, slice_index=1, filled_quantity=q1, filled_price=100.60)

    assert plan.circuit_breaker_triggered is True
    assert plan.status == "CIRCUIT_BREAKER_TRIGGERED"
    assert "breached maximum tolerance" in (plan.circuit_breaker_reason or "")

    # Remaining slices must be CANCELLED
    assert plan.child_orders[0].status == ChildOrderStatus.FILLED
    assert plan.child_orders[1].status == ChildOrderStatus.CANCELLED
    assert plan.child_orders[2].status == ChildOrderStatus.CANCELLED


def test_sell_order_slippage_and_breaker(sor_service):
    """Verify sell order calculates slippage correctly (arrival - fill) and trips circuit breaker."""
    plan = sor_service.generate_plan(
        symbol="AMD",
        action=OrderAction.SELL,
        requested_quantity=400.0,
        arrival_price=150.0,
        adv_20=500000.0,
        num_slices=2,
        force_strategy=ExecutionStrategy.TWAP,
        random_seed=42,
    )

    q1 = plan.child_orders[0].target_quantity
    # Sold at 148.50 (loss of $1.50 = 100 bps slippage > 35 bps threshold)
    sor_service.record_fill(plan, slice_index=1, filled_quantity=q1, filled_price=148.50)

    assert plan.circuit_breaker_triggered is True
    assert plan.child_orders[0].slippage_bps == 100.0
    assert plan.child_orders[1].status == ChildOrderStatus.CANCELLED


def test_settings_repo_custom_overrides():
    """Verify custom settings from repository are respected."""
    mock_repo = MockSettingsRepo({
        "sor_enabled": True,
        "sor_adv_max_pct": 0.025,             # 2.5%
        "sor_max_slippage_bps": 50.0,         # 50 bps
        "sor_default_execution_window_minutes": 45,
        "sor_twap_jitter_pct": 0.20,
    })
    svc = SmartOrderRoutingService(user_id="u1", settings_repo=mock_repo)

    assert svc.adv_max_pct == 0.025
    assert svc.max_slippage_bps == 50.0
    assert svc.default_execution_window_minutes == 45
    assert svc.twap_jitter_pct == 0.20

    # With ADV 100,000, 2.5% allows up to 2,500 shares
    plan = svc.generate_plan(
        symbol="GOOGL",
        action=OrderAction.BUY,
        requested_quantity=3000.0,
        arrival_price=180.0,
        adv_20=100000.0,
    )
    assert plan.approved_quantity == 2500.0
    assert plan.unfilled_rollover_quantity == 500.0
    assert plan.execution_window_minutes == 45


def test_empty_or_zero_quantity_edge_cases(sor_service):
    """Verify zero or invalid quantities yield graceful completed plan without errors."""
    plan = sor_service.generate_plan(
        symbol="META",
        action="BUY",
        requested_quantity=0.0,
        arrival_price=500.0,
        adv_20=100000.0,
    )
    assert plan.approved_quantity == 0.0
    assert plan.num_slices == 0
    assert plan.child_orders == []
    assert plan.status == "COMPLETED"
