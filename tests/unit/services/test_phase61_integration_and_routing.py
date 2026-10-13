"""
Integration tests for Phase 61: UnifiedRiskGateway, StaggeredDipBuying, and ConversationRouter.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.unified_risk_gateway_service import (
    UnifiedRiskGatewayService,
    RiskSeverity,
)
from src.services.dynamic_iv_surface_skew_hedging_service import (
    IVSurfaceTickerMetric,
)
from src.services.microstructure_order_flow_imbalance_service import (
    OFITickerMetric,
)
from src.services.staggered_dip_buying_service import (
    StaggeredDipBuyingService,
)
from src.services.conversation_router import ConversationRouter


@pytest.mark.asyncio
async def test_risk_gateway_blocks_on_liquidity_vacuum_freeze():
    gateway = UnifiedRiskGatewayService(user_id="test_user")

    # Mock all other guards to pass so we isolate the OFI freeze check
    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
         patch("src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate", new_callable=AsyncMock) as mock_cal, \
         patch("src.services.vpin_toxicity_guard_service.VPINToxicityGuardService.evaluate_ticker", new_callable=AsyncMock) as mock_vpin, \
         patch("src.services.bayesian_jump_diffusion_guard_service.BayesianJumpDiffusionGuardService.evaluate_ticker", new_callable=AsyncMock) as mock_jump, \
         patch("src.services.slippage_guard_service.SlippageGuardService.is_opening_auction_window", return_value=(False, None)), \
         patch("src.services.dynamic_iv_surface_skew_hedging_service.DynamicIVSurfaceSkewHedgingService.assess_iv_surface", new_callable=AsyncMock) as mock_iv, \
         patch("src.services.microstructure_order_flow_imbalance_service.MicrostructureOrderFlowImbalanceService.is_vacuum_frozen", new_callable=AsyncMock) as mock_freeze:

        mock_cal.return_value = MagicMock(is_blackout=False)
        mock_vpin.return_value = MagicMock(is_toxic=False, recommended_action="PROCEED")
        mock_jump.return_value = MagicMock(is_acute_jump=False)
        mock_iv.return_value = IVSurfaceTickerMetric(
            ticker="NVDA",
            regime="NORMAL_SMILE",
            put_iv_25d=0.25,
            call_iv_25d=0.22,
            skew_ratio=1.13,
            front_month_iv=0.23,
            back_month_iv=0.24,
            term_structure_slope=0.01,
            tail_risk_index=0.20,
            risk_budget_multiplier=1.0,
            recommended_downward_shift_pct=0.0,
            rationale="Normal",
        )
        # Simulate active liquidity vacuum freeze
        mock_freeze.return_value = (True, "Spread shock 3.5x active", 95)

        res = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="BUY",
            amount_usd=100.0,
        )

        assert res.allowed is False
        assert res.severity == RiskSeverity.BLOCKED
        assert res.primary_blocker == "LiquidityVacuumFreeze"
        assert any("liquidity vacuum freeze active" in r for r in res.reasons)


@pytest.mark.asyncio
async def test_risk_gateway_degrades_on_extreme_iv_inversion():
    gateway = UnifiedRiskGatewayService(user_id="test_user")

    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
         patch("src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate", new_callable=AsyncMock) as mock_cal, \
         patch("src.services.vpin_toxicity_guard_service.VPINToxicityGuardService.evaluate_ticker", new_callable=AsyncMock) as mock_vpin, \
         patch("src.services.bayesian_jump_diffusion_guard_service.BayesianJumpDiffusionGuardService.evaluate_ticker", new_callable=AsyncMock) as mock_jump, \
         patch("src.services.slippage_guard_service.SlippageGuardService.is_opening_auction_window", return_value=(False, None)), \
         patch("src.services.dynamic_iv_surface_skew_hedging_service.DynamicIVSurfaceSkewHedgingService.assess_iv_surface", new_callable=AsyncMock) as mock_iv, \
         patch("src.services.microstructure_order_flow_imbalance_service.MicrostructureOrderFlowImbalanceService.is_vacuum_frozen", new_callable=AsyncMock) as mock_freeze:

        mock_cal.return_value = MagicMock(is_blackout=False)
        mock_vpin.return_value = MagicMock(is_toxic=False, recommended_action="PROCEED")
        mock_jump.return_value = MagicMock(is_acute_jump=False)
        mock_freeze.return_value = (False, None, 0)

        # Simulate Extreme IV tail inversion
        mock_iv.return_value = IVSurfaceTickerMetric(
            ticker="NVDA",
            regime="EXTREME_TAIL_INVERSION",
            put_iv_25d=0.55,
            call_iv_25d=0.30,
            skew_ratio=1.83,
            front_month_iv=0.48,
            back_month_iv=0.42,
            term_structure_slope=-0.06,
            tail_risk_index=0.85,
            risk_budget_multiplier=0.40,
            recommended_downward_shift_pct=0.0070,
            rationale="Extreme panic",
        )

        res = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="BUY",
            amount_usd=100.0,
        )

        assert res.allowed is False
        assert res.severity == RiskSeverity.DEGRADED
        assert res.primary_blocker == "ExtremeIVTailInversion"
        assert any("Extreme tail risk inversion active" in r for r in res.reasons)


@pytest.mark.asyncio
async def test_staggered_dip_buying_applies_iv_skew_shift():
    # Setup mock support service
    mock_support = MagicMock()
    mock_levels = MagicMock(
        current_price=125.0,
        key_support_price=120.0,
        anchored_vwap=122.0,
        point_of_control=123.0,
        value_area_low=121.0,
        value_area_high=126.0,
    )
    mock_support.calculate_institutional_support.return_value = mock_levels

    # Mock IV surface service with shift of 0.0050 (50 bps)
    mock_iv_svc = MagicMock()
    mock_iv_metric = IVSurfaceTickerMetric(
        ticker="NVDA",
        regime="EXTREME_TAIL_INVERSION",
        put_iv_25d=0.55,
        call_iv_25d=0.30,
        skew_ratio=1.83,
        front_month_iv=0.48,
        back_month_iv=0.42,
        term_structure_slope=-0.06,
        tail_risk_index=0.85,
        risk_budget_multiplier=0.40,
        recommended_downward_shift_pct=0.0050,
        rationale="Extreme IV panic shift",
    )
    mock_iv_svc.assess_iv_surface = AsyncMock(return_value=mock_iv_metric)
    mock_iv_svc.is_enabled = AsyncMock(return_value=True)

    svc = StaggeredDipBuyingService(
        user_id="test_user",
        support_service=mock_support,
        iv_surface_service=mock_iv_svc,
        risk_gateway=None,
    )

    plan = await svc.calculate_staggered_plan_for_ticker(
        ticker="NVDA",
        target_budget_usd=100.0,
        current_price=125.0,
    )

    assert plan.iv_skew_regime == "EXTREME_TAIL_INVERSION"
    assert plan.iv_skew_shift_pct == 0.0050
    assert any("[IV尾部避險平移: -50 bps" in t.rationale for t in plan.tiers)


@pytest.mark.asyncio
async def test_conversation_router_ivskew_and_ofi_direct_commands():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /ivskew
    reply_iv = await router.route(
        adapter=adapter,
        channel_user_id="tg_123",
        text="/ivskew",
        resolved_user_id="usr_test",
    )
    assert reply_iv is not None
    assert "動態隱含波動率曲面偏度與極端尾部避險儀表" in reply_iv

    # Test /ofi
    reply_ofi = await router.route(
        adapter=adapter,
        channel_user_id="tg_123",
        text="/ofi",
        resolved_user_id="usr_test",
    )
    assert reply_ofi is not None
    assert "微觀訂單流失衡率 (OFI) 與流動性真空防禦儀表" in reply_ofi
