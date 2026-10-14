import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.unified_risk_gateway_service import (
    UnifiedRiskGatewayService,
    RiskGatewayResult,
    RiskSeverity,
)
from src.services.trend_hysteresis_lockout_service import TrendHysteresisLockoutService

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def clean_hysteresis_state():
    TrendHysteresisLockoutService._in_memory_state.clear()
    yield
    TrendHysteresisLockoutService._in_memory_state.clear()

@pytest.mark.asyncio
async def test_risk_gateway_step10_trend_hysteresis_blocks_buy_noise():
    gateway = UnifiedRiskGatewayService(user_id="test_user")
    # Low confidence (5.5 < 8.0) and inside deadband
    with patch(
        "src.services.trading_protections_service.TradingProtectionsService.check",
        return_value=None,
    ), patch(
        "src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate",
        new_callable=AsyncMock,
        return_value=MagicMock(is_blackout=False),
    ):
        res = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="BUY",
            amount_usd=100.0,
            current_price=132.5,
            strategy_name="routine_momentum",
            confidence_score=5.5,
        )
        assert not res.allowed
        assert res.primary_blocker == "TrendHysteresisLockout"
        assert "trend_hysteresis" in res.guard_details

@pytest.mark.asyncio
async def test_risk_gateway_step10_macro_bull_blocks_routine_sell():
    gateway = UnifiedRiskGatewayService(user_id="test_user")
    # NVDA is in macro bull (SMA50 125 > SMA200 110, spot 135 > 125)
    with patch(
        "src.services.trading_protections_service.TradingProtectionsService.check",
        return_value=None,
    ), patch(
        "src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate",
        new_callable=AsyncMock,
        return_value=MagicMock(is_blackout=False),
    ):
        res = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="SELL",
            amount_usd=100.0,
            current_price=135.0,
            strategy_name="routine_rebalance",
        )
        assert not res.allowed
        assert res.primary_blocker == "TrendHysteresisLockout"
        assert "MacroTrendLock" in res.reasons[0]

@pytest.mark.asyncio
async def test_risk_gateway_step10_macro_bull_exempts_stop_loss():
    gateway = UnifiedRiskGatewayService(user_id="test_user")
    with patch(
        "src.services.trading_protections_service.TradingProtectionsService.check",
        return_value=None,
    ), patch(
        "src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate",
        new_callable=AsyncMock,
        return_value=MagicMock(is_blackout=False),
    ):
        res = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="SELL",
            amount_usd=100.0,
            current_price=135.0,
            strategy_name="trailing_stop_loss",
        )
        assert res.allowed
        assert res.primary_blocker is None

@pytest.mark.asyncio
async def test_risk_gateway_step11_turnover_friction_blocks_low_alpha():
    gateway = UnifiedRiskGatewayService(user_id="test_user")
    with patch(
        "src.services.trading_protections_service.TradingProtectionsService.check",
        return_value=None,
    ), patch(
        "src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate",
        new_callable=AsyncMock,
        return_value=MagicMock(is_blackout=False),
    ), patch(
        "src.services.trend_hysteresis_lockout_service.TrendHysteresisLockoutService.evaluate_trade_action",
        new_callable=AsyncMock,
        return_value=(True, None, {}),
    ), patch(
        "src.services.friction_aware_tranche_sizing_service.FrictionAwareTrancheSizingService.evaluate_order_friction_and_tranche"
    ) as mock_tranche:
        from src.services.friction_aware_tranche_sizing_service import FrictionHurdleMetric, TrancheAllocation
        mock_alloc = TrancheAllocation("NVDA", 100.0, 70.0, 30.0, 0.70, 0.30, 30.0, True)
        mock_tranche.return_value = FrictionHurdleMetric(
            ticker="NVDA",
            action="BUY",
            proposed_shares=10.0,
            current_price=135.0,
            estimated_spread_pct=0.0005,
            estimated_slippage_pct=0.0010,
            estimated_fee_pct=0.0,
            round_trip_friction_pct=0.0025,
            raw_alpha_gain_pct=0.0030,
            net_alpha_pct=0.0005,
            hurdle_threshold_pct=0.0080,
            passed_hurdle=False,
            tranche_info=mock_alloc,
            adjusted_shares=10.0,
            decision="BLOCKED_BY_FRICTION",
            reason="[TurnoverFriction] Order blocked: Net Alpha +0.05% < hurdle 0.80%",
        )

        res = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="BUY",
            amount_usd=100.0,
            current_price=135.0,
            strategy_name="routine_rebalance",
        )
        assert not res.allowed
        assert res.primary_blocker == "TurnoverFrictionHurdle"
        assert "TurnoverFriction" in res.reasons[0]
