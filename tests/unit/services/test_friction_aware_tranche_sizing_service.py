import pytest
from src.services.friction_aware_tranche_sizing_service import (
    FrictionAwareTrancheSizingService,
    FrictionHurdleMetric,
    TrancheAllocation,
    TrancheDriftReport,
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

@pytest.mark.anyio
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

@pytest.mark.anyio
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

@pytest.mark.anyio
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

@pytest.mark.anyio
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

@pytest.mark.anyio
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
    assert "核心/衛星動態漂移自癒監控" in report

# ─────────────────────────────────────────────────────────────────────────────
# Phase 64A & Phase 64B New Tests: Dynamic Drift Auto-Healing & Live Spread Feed
# ─────────────────────────────────────────────────────────────────────────────

def test_tranche_drift_balanced_within_tolerance():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # 100 shares held, core is 72 shares (72% is within [65%, 75%])
    report = service.evaluate_tranche_drift(
        ticker="NVDA",
        current_price=120.0,
        total_shares=100.0,
        current_core_shares=72.0,
    )
    assert report.drift_state == "BALANCED"
    assert report.action_recommendation == "HOLD"
    assert report.rebalance_shares == 0.0
    assert report.is_healing_viable is False
    assert "位於容差帶" in report.notes

def test_tranche_drift_core_expanded_healing():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # 100 shares held, core has expanded to 85 shares (85% > 75%)
    report = service.evaluate_tranche_drift(
        ticker="NVDA",
        current_price=100.0,
        total_shares=100.0,
        current_core_shares=85.0,
    )
    assert report.drift_state == "CORE_EXPANDED"
    assert report.action_recommendation == "TRIM_CORE_TO_SATELLITE"
    assert report.rebalance_shares == 15.0  # 85 - 70 = 15 shares
    assert report.rebalance_usd == 1500.0
    assert report.is_healing_viable is True

    # Test auto healing simulation (dry run)
    heal_res = service.auto_heal_tranche_drift(
        ticker="NVDA",
        current_price=100.0,
        total_shares=100.0,
        current_core_shares=85.0,
        dry_run=True,
    )
    assert heal_res["dry_run"] is True
    assert heal_res["action"] == "TRIM_CORE_TO_SATELLITE"
    assert heal_res["post_healing"]["core_shares"] == 70.0
    assert heal_res["post_healing"]["satellite_shares"] == 30.0
    assert heal_res["post_healing"]["core_ratio"] == 0.70

def test_tranche_drift_core_deficit_healing():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # 100 shares held, core has dropped to 55 shares (55% < 65%)
    report = service.evaluate_tranche_drift(
        ticker="NVDA",
        current_price=100.0,
        total_shares=100.0,
        current_core_shares=55.0,
    )
    assert report.drift_state == "CORE_DEFICIT"
    assert report.action_recommendation == "TOP_UP_CORE_FROM_SATELLITE"
    assert report.rebalance_shares == 15.0  # 70 - 55 = 15 shares
    assert report.rebalance_usd == 1500.0
    assert report.is_healing_viable is True

    # Test auto healing simulation
    heal_res = service.auto_heal_tranche_drift(
        ticker="NVDA",
        current_price=100.0,
        total_shares=100.0,
        current_core_shares=55.0,
        dry_run=False,
    )
    assert heal_res["dry_run"] is False
    assert heal_res["status"] == "EXECUTED"
    assert heal_res["post_healing"]["core_shares"] == 70.0
    assert heal_res["post_healing"]["satellite_shares"] == 30.0

def test_live_spread_injection_and_fallback():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # 1. Live spread injection
    spread, slippage, fee, friction, source = service.resolve_spread_and_friction(
        "NVDA", live_spread_pct=0.0025
    )
    assert source == "LIVE_ORDERBOOK"
    assert spread == 0.0025
    assert friction == 2.0 * (0.0025 / 2.0 + 0.0010)

    # 2. Static lookup fallback
    spread_st, _, _, friction_st, source_st = service.resolve_spread_and_friction(
        "NVDA", live_spread_pct=None
    )
    assert source_st == "STATIC_LOOKUP"
    assert spread_st == 0.0005  # NVDA from SPREAD_MAP

@pytest.mark.anyio
async def test_evaluate_order_friction_with_live_spread():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    # High live spread 0.0080 (0.80%) pushes friction above expected alpha
    metric = await service.evaluate_order_friction_and_tranche(
        ticker="NVDA",
        action="BUY",
        quantity=5.0,
        current_price=135.0,
        strategy_name="routine_rebalance",
        expected_alpha_pct=0.0090,  # 0.90%
        delta_weight=0.05,
        live_spread_pct=0.0080,
    )
    assert metric.spread_source == "LIVE_ORDERBOOK"
    assert metric.estimated_spread_pct == 0.0080
    assert not metric.passed_hurdle
    assert metric.decision == "BLOCKED_BY_FRICTION"

def test_format_drift_heal_report():
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    heal_res = service.auto_heal_tranche_drift(
        ticker="NVDA",
        current_price=125.0,
        total_shares=100.0,
        current_core_shares=85.0,
        dry_run=True,
    )
    report = service.format_drift_heal_report(heal_res)
    assert "核心/衛星動態漂移自癒執行報告" in report
    assert "NVDA" in report
    assert "自癒模擬試算" in report
    assert "TRIM_CORE_TO_SATELLITE" in report
    assert "70.0%" in report
