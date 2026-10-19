"""
BDD: synthetic / unavailable data must never block an order and must be marked.
行為規格：合成或無資料不得擋單，且必須帶標記。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService

_BLOCKERS = {"NegativeGammaVolatilityAccelerator", "KalmanPairsStructuralBreak"}


async def _evaluate(strategy_name):
    gateway = UnifiedRiskGatewayService(user_id="test_user")
    with patch(
        "src.services.trading_protections_service.TradingProtectionsService.check",
        return_value=None,
    ), patch(
        "src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate",
        new_callable=AsyncMock,
        return_value=MagicMock(is_blackout=False),
    ), patch(
        "src.services.option_gamma_exposure_gex_service.OptionGammaExposureGEXService.is_enabled",
        new_callable=AsyncMock, return_value=True,
    ), patch(
        "src.services.kalman_pairs_cointegration_service.KalmanPairsCointegrationService.is_enabled",
        new_callable=AsyncMock, return_value=True,
    ), patch(
        "src.services.option_gamma_exposure_gex_service.OptionGammaExposureGEXService.get_options_chain",
        new_callable=AsyncMock, return_value=None,
    ), patch(
        "src.services.kalman_pairs_cointegration_service.KalmanPairsCointegrationService.get_price_series_pair",
        new_callable=AsyncMock,
        return_value=([100.0 * (1 + 0.02 * i) for i in range(60)], [100.0] * 60, True),
    ):
        return await gateway.evaluate_trade_risk(
            ticker="NVDA", action="BUY", amount_usd=100.0, current_price=135.0,
            strategy_name=strategy_name, confidence_score=9.0,
        )


class TestSyntheticDataNeverBlocks:
    @pytest.mark.asyncio
    async def test_given_synthetic_chain_when_buy_evaluated_then_not_blocked_and_marked(self):
        # Given no real option chain
        # When a BUY is evaluated
        res = await _evaluate("routine_momentum")
        # Then the GEX guard did not block and is marked not applicable with the reason
        assert res.primary_blocker not in _BLOCKERS
        gex = res.guard_details["gamma_exposure_gex"]
        assert gex["status"] == "not_applicable"
        assert gex["fallback_reason"] == "no_options_chain_provider"
        assert "regime" not in gex and "net_gex" not in gex

    @pytest.mark.asyncio
    async def test_given_synthetic_pair_series_when_pairs_buy_evaluated_then_not_blocked_and_marked(self):
        # Given a synthetic price series that would look like an extreme z-score break
        # When a pairs BUY is evaluated
        res = await _evaluate("pairs_arbitrage")
        # Then the Kalman guard did not block and is marked not applicable
        assert res.primary_blocker != "KalmanPairsStructuralBreak"
        kp = res.guard_details["kalman_pairs"]
        assert kp["status"] == "not_applicable"
        assert kp["fallback_reason"] == "synthetic_series"
        assert "spread_zscore" not in kp
