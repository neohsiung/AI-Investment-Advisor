"""
Unit tests for Intraday Liquidity Hole & Stop-Hunt Guard (E4 Engine).
"""
from datetime import datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.execution import router as execution_router
from src.services.intraday_liquidity_hunt_guard_service import (
    GuardAction,
    GuardState,
    IntradayLiquidityHuntGuardService,
    KeyLevel,
    KeyLevelType,
    OrderBookSnapshot,
    TradeBar,
)


@pytest.fixture
def guard_service() -> IntradayLiquidityHuntGuardService:
    return IntradayLiquidityHuntGuardService(
        user_id="test_user",
        default_depth_depletion_threshold=0.70,
        default_spread_expansion_threshold=2.0,
        default_stop_hunt_score_threshold=0.65,
        default_cooldown_seconds=60,
    )


def test_normal_microstructure_flow(guard_service: IntradayLiquidityHuntGuardService):
    # Prime with normal snapshots
    for _ in range(10):
        guard_service.record_quote(
            OrderBookSnapshot(
                symbol="AAPL",
                bid_price=150.00,
                ask_price=150.05,
                bid_size=5000.0,
                ask_size=5000.0,
            )
        )

    # Prime with normal trade bar
    for _ in range(5):
        guard_service.record_trade_bar(
            TradeBar(
                symbol="AAPL",
                open_price=150.00,
                high_price=150.20,
                low_price=149.90,
                close_price=150.05,
                volume=10000.0,
            )
        )

    res = guard_service.evaluate_guard(
        symbol="AAPL",
        snapshot=OrderBookSnapshot(
            symbol="AAPL",
            bid_price=150.02,
            ask_price=150.06,
            bid_size=4800.0,
            ask_size=5100.0,
        ),
        bar=TradeBar(
            symbol="AAPL",
            open_price=150.02,
            high_price=150.15,
            low_price=149.95,
            close_price=150.08,
            volume=9500.0,
        ),
        key_levels=[
            KeyLevel(level_type=KeyLevelType.RESISTANCE, price=152.00),
            KeyLevel(level_type=KeyLevelType.SUPPORT, price=148.00),
        ],
    )

    assert res.state == GuardState.NORMAL
    assert res.action == GuardAction.PROCEED_NORMAL
    assert not res.liquidity_hole.is_hole_detected
    assert not res.stop_hunt.is_hunt_detected
    assert res.recommended_delay_seconds == 0
    assert res.adverse_slippage_buffer_bps == 0.0


def test_liquidity_hole_detection(guard_service: IntradayLiquidityHuntGuardService):
    # Establish deep baseline (depth = 10,000, spread = 0.04)
    for _ in range(10):
        guard_service.record_quote(
            OrderBookSnapshot(
                symbol="MSFT",
                bid_price=300.00,
                ask_price=300.04,
                bid_size=5000.0,
                ask_size=5000.0,
            )
        )

    # Sudden vacuum quote: depth drops to 1,000 (90% depletion), spread widens to 0.15 (3.75x)
    shock_snapshot = OrderBookSnapshot(
        symbol="MSFT",
        bid_price=299.90,
        ask_price=300.05,
        bid_size=500.0,
        ask_size=500.0,
    )

    res = guard_service.evaluate_guard(
        symbol="MSFT",
        snapshot=shock_snapshot,
    )

    assert res.state == GuardState.LIQUIDITY_HOLE
    assert res.action == GuardAction.FORCE_PASSIVE_LIMIT
    assert res.liquidity_hole.is_hole_detected
    assert res.liquidity_hole.depth_depletion_ratio >= 0.70
    assert res.liquidity_hole.spread_expansion_ratio >= 2.0
    assert res.recommended_delay_seconds == 30
    assert res.adverse_slippage_buffer_bps == 20.0


def test_stop_hunt_bull_trap_resistance_sweep(guard_service: IntradayLiquidityHuntGuardService):
    # Establish volume baseline ~ 10,000
    for _ in range(5):
        guard_service.record_trade_bar(
            TradeBar(
                symbol="NVDA",
                open_price=120.00,
                high_price=120.50,
                low_price=119.50,
                close_price=120.20,
                volume=10000.0,
            )
        )

    # Bull trap bar: spikes above resistance ($121.00) to $121.40 (0.33% penetration),
    # but violently rejects and closes down at $120.80 (< 121.00, full reversal) on 4x volume spike
    bull_trap_bar = TradeBar(
        symbol="NVDA",
        open_price=120.50,
        high_price=121.40,
        low_price=120.70,
        close_price=120.80,
        volume=40000.0,
    )

    key_levels = [
        KeyLevel(level_type=KeyLevelType.RESISTANCE, price=121.00, description="Session High"),
    ]

    res = guard_service.evaluate_guard(
        symbol="NVDA",
        bar=bull_trap_bar,
        key_levels=key_levels,
    )

    assert res.state == GuardState.HUNT_SWEEP_ALERT
    assert res.action == GuardAction.ABORT_BREAKOUT_CHASE
    assert res.stop_hunt.is_hunt_detected
    assert res.stop_hunt.swept_level == 121.00
    assert res.stop_hunt.level_type == KeyLevelType.RESISTANCE
    assert res.stop_hunt.reversion_ratio >= 1.0
    assert res.stop_hunt.volume_spike_ratio >= 3.0
    assert res.recommended_delay_seconds == 45
    assert res.adverse_slippage_buffer_bps == 25.0


def test_stop_hunt_bear_trap_support_sweep(guard_service: IntradayLiquidityHuntGuardService):
    # Establish volume baseline ~ 10,000
    for _ in range(5):
        guard_service.record_trade_bar(
            TradeBar(
                symbol="TSLA",
                open_price=200.00,
                high_price=201.00,
                low_price=199.50,
                close_price=200.20,
                volume=10000.0,
            )
        )

    # Bear trap bar: dips below support ($198.00) to $197.30 (0.35% penetration),
    # but immediately absorbs and closes back up at $198.40 on 3.5x volume
    bear_trap_bar = TradeBar(
        symbol="TSLA",
        open_price=199.00,
        high_price=198.60,
        low_price=197.30,
        close_price=198.40,
        volume=35000.0,
    )

    key_levels = [
        KeyLevel(level_type=KeyLevelType.SUPPORT, price=198.00, description="Key Demand Zone"),
    ]

    res = guard_service.evaluate_guard(
        symbol="TSLA",
        bar=bear_trap_bar,
        key_levels=key_levels,
    )

    assert res.state == GuardState.HUNT_SWEEP_ALERT
    assert res.action == GuardAction.ABORT_BREAKOUT_CHASE
    assert res.stop_hunt.is_hunt_detected
    assert res.stop_hunt.swept_level == 198.00
    assert res.stop_hunt.level_type == KeyLevelType.SUPPORT
    assert res.stop_hunt.reversion_ratio >= 1.0
    assert res.recommended_delay_seconds == 45
    assert res.adverse_slippage_buffer_bps == 25.0


def test_compound_shock_defensive_pause(guard_service: IntradayLiquidityHuntGuardService):
    # Prime depth & volume
    for _ in range(5):
        guard_service.record_quote(
            OrderBookSnapshot(
                symbol="META",
                bid_price=500.00,
                ask_price=500.05,
                bid_size=4000.0,
                ask_size=4000.0,
            )
        )
        guard_service.record_trade_bar(
            TradeBar(
                symbol="META",
                open_price=500.00,
                high_price=500.50,
                low_price=499.50,
                close_price=500.10,
                volume=8000.0,
            )
        )

    # Simultaneous liquidity hole + bull trap sweep
    shock_snapshot = OrderBookSnapshot(
        symbol="META",
        bid_price=499.80,
        ask_price=500.10,
        bid_size=300.0,
        ask_size=300.0,
    )
    shock_bar = TradeBar(
        symbol="META",
        open_price=500.00,
        high_price=502.00,
        low_price=499.50,
        close_price=500.20,
        volume=32000.0,
    )
    key_levels = [
        KeyLevel(level_type=KeyLevelType.RESISTANCE, price=501.00),
    ]

    res = guard_service.evaluate_guard(
        symbol="META",
        snapshot=shock_snapshot,
        bar=shock_bar,
        key_levels=key_levels,
    )

    assert res.state == GuardState.DEFENSIVE_PAUSE
    assert res.action == GuardAction.DELAY_EXECUTION
    assert res.liquidity_hole.is_hole_detected
    assert res.stop_hunt.is_hunt_detected
    assert res.recommended_delay_seconds == 60
    assert res.adverse_slippage_buffer_bps == 35.0


def test_cooldown_and_manual_reset(guard_service: IntradayLiquidityHuntGuardService):
    # Trigger liquidity hole for AMD
    for _ in range(5):
        guard_service.record_quote(
            OrderBookSnapshot(
                symbol="AMD",
                bid_price=100.00,
                ask_price=100.02,
                bid_size=3000.0,
                ask_size=3000.0,
            )
        )

    guard_service.evaluate_guard(
        symbol="AMD",
        snapshot=OrderBookSnapshot(
            symbol="AMD",
            bid_price=99.80,
            ask_price=100.10,
            bid_size=200.0,
            ask_size=200.0,
        ),
    )

    assert guard_service.get_guard_state("AMD") == GuardState.LIQUIDITY_HOLE

    # Immediate follow-up with normalized quote: still in cooldown
    res_cooldown = guard_service.evaluate_guard(
        symbol="AMD",
        snapshot=OrderBookSnapshot(
            symbol="AMD",
            bid_price=100.00,
            ask_price=100.02,
            bid_size=3000.0,
            ask_size=3000.0,
        ),
    )
    assert res_cooldown.state == GuardState.DEFENSIVE_PAUSE

    # Manual reset
    guard_service.reset_symbol_state("AMD")
    assert guard_service.get_guard_state("AMD") == GuardState.NORMAL

    all_states = guard_service.get_all_guard_states()
    assert "AMD" in all_states
    assert all_states["AMD"]["current_state"] == "NORMAL"


def test_api_guard_endpoints():
    test_app = FastAPI()
    test_app.include_router(execution_router, prefix="/api/v1/execution")
    client = TestClient(test_app)

    # 1. Evaluate endpoint
    eval_payload = {
        "symbol": "GOOGL",
        "snapshot": {
            "symbol": "GOOGL",
            "bid_price": 170.00,
            "ask_price": 170.05,
            "bid_size": 2500.0,
            "ask_size": 2500.0,
        },
        "bar": {
            "symbol": "GOOGL",
            "open_price": 170.00,
            "high_price": 170.20,
            "low_price": 169.90,
            "close_price": 170.05,
            "volume": 5000.0,
        },
        "key_levels": [
            {"level_type": "RESISTANCE", "price": 175.00, "description": "Weekly High"},
        ],
    }

    resp = client.post("/api/v1/execution/guard/evaluate", json=eval_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "GOOGL"
    assert data["state"] == "NORMAL"
    assert data["action"] == "PROCEED_NORMAL"

    # 2. Status endpoint
    resp_status = client.get("/api/v1/execution/guard/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert "GOOGL" in status_data["symbols"]

    # 3. Reset endpoint
    resp_reset = client.post("/api/v1/execution/guard/reset", json={"symbol": "GOOGL"})
    assert resp_reset.status_code == 200
    reset_data = resp_reset.json()
    assert reset_data["status"] == "success"
    assert reset_data["symbol"] == "GOOGL"


def test_guard_disabled_behavior():
    class MockSettings:
        def get(self, key):
            if key == "liquidity_hunt_guard_enabled":
                return False
            return None

    service = IntradayLiquidityHuntGuardService(
        user_id="test_user",
        settings_service=MockSettings(),
    )

    assert service.is_enabled is False

    # Extreme quote and bar that would normally trip guard
    res = service.evaluate_guard(
        symbol="NFLX",
        snapshot=OrderBookSnapshot(
            symbol="NFLX",
            bid_price=600.0,
            ask_price=605.0,
            bid_size=10.0,
            ask_size=10.0,
        ),
        bar=TradeBar(
            symbol="NFLX",
            open_price=600.0,
            high_price=610.0,
            low_price=595.0,
            close_price=600.0,
            volume=50000.0,
        ),
        key_levels=[KeyLevel(level_type=KeyLevelType.RESISTANCE, price=605.0)],
    )

    assert res.state == GuardState.NORMAL
    assert res.action == GuardAction.PROCEED_NORMAL
    assert res.recommended_delay_seconds == 0
    assert res.adverse_slippage_buffer_bps == 0.0

