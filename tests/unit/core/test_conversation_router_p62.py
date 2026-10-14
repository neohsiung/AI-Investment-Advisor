import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.conversation_router import ConversationRouter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_router_gex_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /gex SPY
    with patch("src.services.option_gamma_exposure_gex_service.OptionGammaExposureGEXService.evaluate_ticker_gex") as mock_eval:
        mock_metric = MagicMock()
        mock_metric.ticker = "SPY"
        mock_metric.spot_price = 580.0
        mock_metric.net_gex = 15000000.0
        mock_metric.call_gex = 20000000.0
        mock_metric.put_gex = -5000000.0
        mock_metric.zero_gamma_flip_point = 570.0
        mock_metric.distance_to_flip_pct = 0.017
        mock_metric.max_oi_pin_strike = 580.0
        mock_metric.pinning_gravity_score = 0.8
        mock_metric.days_to_opex = 3
        mock_metric.regime = "POSITIVE_GAMMA_STICKY"
        mock_metric.volatility_damping_multiplier = 0.85
        mock_metric.requires_protection = False
        mock_metric.rationale = "Test GEX rationale"
        mock_metric.evaluated_at = "2026-10-14T08:00:00Z"
        mock_eval.return_value = mock_metric

        res = await router._handle_system_command(adapter, "chan1", "/gex SPY", "test_user")
        assert res is not None
        assert "做市商淨伽馬暴露" in res
        assert "SPY" in res
        assert "$580.00" in res

@pytest.mark.anyio
async def test_router_pair_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /pair NVDA AMD
    with patch("src.services.kalman_pairs_cointegration_service.KalmanPairsCointegrationService.evaluate_pairs_cointegration") as mock_eval:
        mock_metric = MagicMock()
        mock_metric.ticker_y = "NVDA"
        mock_metric.ticker_x = "AMD"
        mock_metric.price_y = 230.0
        mock_metric.price_x = 160.0
        mock_metric.dynamic_beta = 1.42
        mock_metric.dynamic_alpha = 3.2
        mock_metric.residual_spread = 0.85
        mock_metric.spread_zscore = 1.65
        mock_metric.ou_half_life_days = 11.2
        mock_metric.regime = "DIVERGENCE_ARBITRAGE_ENTRY"
        mock_metric.arbitrage_action = "PAIR_SHORT_Y_LONG_X"
        mock_metric.target_hedge_ratio_x_per_y = 1.42
        mock_metric.requires_circuit_breaker = False
        mock_metric.rationale = "Test Pairs rationale"
        mock_metric.evaluated_at = "2026-10-14T08:00:00Z"
        mock_eval.return_value = mock_metric

        res = await router._handle_system_command(adapter, "chan1", "/pair NVDA AMD", "test_user")
        assert res is not None
        assert "卡爾曼濾波動態協整" in res
        assert "NVDA" in res
        assert "AMD" in res
        assert "1.42" in res
