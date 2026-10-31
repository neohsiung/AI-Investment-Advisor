import pytest
from unittest.mock import MagicMock
from src.services.trend_hysteresis_lockout_service import (
    TrendHysteresisLockoutService,
    TrendHysteresisMetric,
    HysteresisState,
)

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def clean_hysteresis_state():
    TrendHysteresisLockoutService._in_memory_state.clear()
    yield
    TrendHysteresisLockoutService._in_memory_state.clear()

@pytest.mark.asyncio
async def test_hysteresis_bullish_breakout():
    service = TrendHysteresisLockoutService(user_id="test_user")
    # Confidence >= 8.0 and Price > MA20 + 1.5%
    # NVDA MA20 benchmark is 132.0; price 136.0 is +3.03% (> +1.5%)
    metric = await service.evaluate_ticker_trend("NVDA", current_price=136.0, confidence_score=8.5)
    assert metric.current_state == HysteresisState.BULL_ACTIVE.value
    assert metric.allowed_action == "BUY"
    assert metric.price_deviation_pct > 0.015

@pytest.mark.asyncio
async def test_hysteresis_bearish_breakdown():
    service = TrendHysteresisLockoutService(user_id="test_user")
    # Confidence <= 5.0 and Price < MA20 - 1.5%
    # NVDA MA20 benchmark is 132.0; price 128.0 is -3.03% (< -1.5%)
    metric = await service.evaluate_ticker_trend("NVDA", current_price=128.0, confidence_score=4.0)
    assert metric.current_state == HysteresisState.BEAR_ACTIVE.value
    assert metric.allowed_action == "SELL"
    assert metric.price_deviation_pct < -0.015

@pytest.mark.asyncio
async def test_hysteresis_deadband_preserves_hold():
    service = TrendHysteresisLockoutService(user_id="test_user")
    # Inside deadband: confidence 6.5 (between 5.0 and 8.0), price 132.5 (+0.38%)
    metric = await service.evaluate_ticker_trend("NVDA", current_price=132.5, confidence_score=6.5)
    assert metric.current_state == HysteresisState.HOLD_BUFFER.value
    assert metric.allowed_action == "HOLD"
    assert "deadband" in metric.reason.lower() or "hysteresis" in metric.reason.lower()

@pytest.mark.asyncio
async def test_macro_trend_long_only_lock_blocks_routine_sell():
    service = TrendHysteresisLockoutService(user_id="test_user")
    # NVDA is in macro bull: SMA50 125.0 > SMA200 110.0 and Price 135.0 > SMA50
    allowed, block_reason, details = await service.evaluate_trade_action(
        ticker="NVDA",
        action="SELL",
        strategy_name="routine_rebalance",
        current_price=135.0,
    )
    assert not allowed
    assert "MacroTrendLock" in block_reason or "secular bull" in block_reason.lower()

@pytest.mark.asyncio
async def test_macro_trend_long_only_lock_exempts_emergency_stop():
    service = TrendHysteresisLockoutService(user_id="test_user")
    allowed, block_reason, details = await service.evaluate_trade_action(
        ticker="NVDA",
        action="SELL",
        strategy_name="trailing_stop_loss",
        current_price=135.0,
    )
    assert allowed
    assert block_reason is None

@pytest.mark.asyncio
async def test_deadband_blocks_buy_noise():
    service = TrendHysteresisLockoutService(user_id="test_user")
    # Trying to BUY inside deadband with low confidence (6.0 < 8.0)
    allowed, block_reason, details = await service.evaluate_trade_action(
        ticker="NVDA",
        action="BUY",
        strategy_name="momentum_entry",
        current_price=132.5,
        confidence_score=6.0,
    )
    assert not allowed
    assert "Schmitt Trigger Deadband" in block_reason

@pytest.mark.asyncio
async def test_emergency_hedge_buy_is_exempt_from_the_deadband_like_an_unnamed_buy():
    """ADR-005: naming the SQQQ hedge BUY must not make it subject to the deadband it was exempt from when unnamed."""
    service = TrendHysteresisLockoutService(user_id="test_user")
    for strategy in (None, "emergency_hedge"):
        allowed, block_reason, _ = await service.evaluate_trade_action(
            ticker="NVDA", action="BUY", strategy_name=strategy, current_price=132.5, confidence_score=6.0)
        assert allowed and block_reason is None, strategy

@pytest.mark.asyncio
async def test_format_trend_report():
    service = TrendHysteresisLockoutService(user_id="test_user")
    metric = await service.evaluate_ticker_trend("NVDA", current_price=135.0, confidence_score=8.5)
    report = service.format_trend_report(metric)
    assert "遲滯回差帶過濾與大趨勢單向鎖定儀表" in report
    assert "NVDA" in report
    assert "SMA50" in report
    assert "SMA200" in report
