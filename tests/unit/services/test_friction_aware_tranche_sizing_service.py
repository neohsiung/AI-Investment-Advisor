import pytest
from src.services.friction_aware_tranche_sizing_service import (
    FrictionAwareTrancheSizingService,
    FrictionHurdleMetric,
    TrancheAllocation,
)

@pytest.fixture
def anyio_backend():
    return "asyncio"

def test_tranche_allocation_70_30_split():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # 100 shares held
    alloc = service.calculate_tranche_allocation("NVDA", total_shares=100.0, is_emergency_stop=False)
    assert alloc.total_shares == 100.0
    assert alloc.core_shares == 70.0
    assert alloc.satellite_shares == 30.0
    assert alloc.max_sellable_satellite_shares == 30.0
    assert alloc.is_core_locked is True

def test_tranche_allocation_emergency_stop_exempt():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # 100 shares held, emergency stop
    alloc = service.calculate_tranche_allocation("NVDA", total_shares=100.0, is_emergency_stop=True)
    assert alloc.max_sellable_satellite_shares == 100.0
    assert alloc.is_core_locked is False

def test_round_trip_friction_estimation():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    spread, slippage, fee, friction = service.estimate_round_trip_friction("NVDA")
    # For NVDA: spread 0.05%, slippage 0.10%, friction = 2 * (0.05%/2 + 0.10%) = 0.25%
    assert 0.0020 <= friction <= 0.0030
    assert fee == 0.0

@pytest.mark.asyncio
async def test_friction_hurdle_blocks_low_alpha_rebalance():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # Expected alpha 0.40% < hurdle 0.80%
    metric = await service.evaluate_order_friction_and_tranche(
        ticker="NVDA",
        action="BUY",
        quantity=5.0,
        current_price=135.0,
        strategy_name="routine_rebalance",
        expected_alpha_pct=0.0040,  # 0.40%
        delta_weight=0.02,
    )
    assert not metric.passed_hurdle
    assert metric.decision == "BLOCKED_BY_FRICTION"
    assert "TurnoverFriction" in metric.reason

@pytest.mark.asyncio
async def test_friction_hurdle_passes_high_alpha():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # Expected alpha 2.0% > hurdle 0.80%
    metric = await service.evaluate_order_friction_and_tranche(
        ticker="NVDA",
        action="BUY",
        quantity=5.0,
        current_price=135.0,
        strategy_name="routine_rebalance",
        expected_alpha_pct=0.020,  # 2.0%
        delta_weight=0.05,
    )
    assert metric.passed_hurdle
    assert metric.decision == "PERMITTED"

@pytest.mark.asyncio
async def test_routine_sell_clamped_to_satellite_tranche():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # Total held: 100 shares. Satellite limit: 30 shares. Proposed sell: 50 shares.
    metric = await service.evaluate_order_friction_and_tranche(
        ticker="NVDA",
        action="SELL",
        quantity=50.0,
        current_price=135.0,
        strategy_name="routine_rebalance",
        total_held_shares=100.0,
        expected_alpha_pct=0.020,
    )
    assert metric.adjusted_shares == 30.0
    assert metric.decision == "CLAMPED_TO_SATELLITE"
    assert "TrancheSizing" in metric.reason

@pytest.mark.asyncio
async def test_emergency_sell_not_clamped():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # Proposed sell: 100 shares on stop_loss
    metric = await service.evaluate_order_friction_and_tranche(
        ticker="NVDA",
        action="SELL",
        quantity=100.0,
        current_price=135.0,
        strategy_name="trailing_stop_loss",
        total_held_shares=100.0,
    )
    assert metric.passed_hurdle
    assert metric.adjusted_shares == 100.0
    assert metric.decision == "PERMITTED"

@pytest.mark.asyncio
async def test_format_tranche_report():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    metric = await service.evaluate_order_friction_and_tranche(
        ticker="NVDA",
        action="SELL",
        quantity=10.0,
        current_price=135.0,
        total_held_shares=100.0,
    )
    report = service.format_tranche_report(metric)
    assert "做市商摩擦成本與核心/衛星倉位分級儀表" in report
    assert "NVDA" in report
    assert "70% 核心底倉" in report
    assert "30% 衛星波段" in report
