"""
Unit tests for PyramidingService (波段動能金字塔加碼服務).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.pyramiding_service import PyramidingService, PyramidingDecision


@pytest.fixture
def mock_market():
    market = MagicMock()
    market.get_technical_indicators.return_value = {
        "rsi": 64.5,
        "macd": "bullish",
        "sma": {
            "sma_20": 105.0,
            "sma_50": 100.0,
            "sma_200": 90.0,
        },
        "volume": {
            "current": 1500000,
            "avg_20": 1200000,
        },
    }
    return market


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings_map = {
        "enable_pyramiding": True,
        "max_pyramid_stages": 2,
        "pyramid_stage1_min_pnl_pct": 8.0,
        "pyramid_stage2_min_pnl_pct": 16.0,
        "pyramid_stage1_scale_ratio": 0.25,
        "pyramid_stage2_scale_ratio": 0.15,
        "max_single_position_pct": 0.18,
    }
    settings.get_setting.side_effect = lambda k, default=None, uid=None: settings_map.get(k, default)
    return settings


@pytest.fixture
def service(mock_settings, mock_market):
    return PyramidingService(
        user_id="test_user",
        settings_service=mock_settings,
        market_data_service=mock_market,
    )


@pytest.mark.anyio
async def test_pyramiding_disabled(service, mock_settings):
    """When enable_pyramiding is false, no scale-in decisions are produced."""
    mock_settings.get_setting.side_effect = lambda k, default=None, uid=None: False if k == "enable_pyramiding" else default
    res = await service.evaluate_position(
        ticker="NVDA",
        current_shares=10.0,
        current_price=120.0,
        avg_price=100.0,
        current_peak=120.0,
        active_stop_price=105.0,
        portfolio_total_equity=10000.0,
    )
    assert res is None


@pytest.mark.anyio
async def test_unrealized_loss_or_low_profit_blocks_pyramiding(service):
    """Positions in loss or insufficient profit (< 8%) must NEVER be scaled into."""
    # Loss: bought at 100, now 95 (-5%)
    res_loss = await service.evaluate_position(
        ticker="NVDA",
        current_shares=10.0,
        current_price=95.0,
        avg_price=100.0,
        current_peak=100.0,
        active_stop_price=90.0,
        portfolio_total_equity=10000.0,
    )
    assert res_loss is None

    # Modest profit: bought at 100, now 105 (+5% < 8%)
    res_modest = await service.evaluate_position(
        ticker="NVDA",
        current_shares=10.0,
        current_price=105.0,
        avg_price=100.0,
        current_peak=105.0,
        active_stop_price=100.5,
        portfolio_total_equity=10000.0,
    )
    assert res_modest is None


@pytest.mark.anyio
async def test_stop_below_cost_blocks_pyramiding(service):
    """Even if profit is +12%, if active stop has not locked in cost (e.g. stop < entry), block pyramiding."""
    res = await service.evaluate_position(
        ticker="NVDA",
        current_shares=10.0,
        current_price=112.0,
        avg_price=100.0,
        current_peak=112.0,
        active_stop_price=96.0,  # Below entry cost!
        portfolio_total_equity=10000.0,
    )
    assert res is None


@pytest.mark.anyio
async def test_stage1_scale_in_success(service):
    """Eligible winner with +12% gain, stop at 104 > 100, healthy RSI triggers Stage 1 pyramiding (25% size)."""
    res = await service.evaluate_position(
        ticker="NVDA",
        current_shares=10.0,
        current_price=112.0,
        avg_price=100.0,
        current_peak=112.0,
        active_stop_price=104.0,  # Locked above entry cost!
        portfolio_total_equity=10000.0,
        current_weight_pct=11.2,
    )
    assert res is not None
    assert res.should_scale_in is True
    assert res.stage == 1
    # 25% of 10 shares = 2.5 shares
    assert res.add_shares == 2.5
    assert res.add_amount_usd == round(2.5 * 112.0, 2)
    assert res.confidence_score >= 8.5
    assert "金字塔動能加碼 Stage 1" in res.rationale


@pytest.mark.anyio
async def test_stage2_scale_in_decreasing_size(service):
    """When Stage 1 is already complete, Stage 2 triggers at higher gain (+20% >= 16%) with smaller size (15%)."""
    service._in_memory_stages["NVDA"] = 1  # Already in Stage 1

    res = await service.evaluate_position(
        ticker="NVDA",
        current_shares=12.5,  # 10 base + 2.5 from Stage 1
        current_price=122.0,
        avg_price=100.0,
        current_peak=122.0,
        active_stop_price=115.0,
        portfolio_total_equity=10000.0,
        current_weight_pct=15.25,
    )
    assert res is not None
    assert res.stage == 2
    # 15% of 12.5 shares = 1.88 shares (decreasing pyramid sizing)
    assert res.add_shares == 1.88
    assert res.add_amount_usd == round(1.88 * 122.0, 2)
    assert "金字塔動能加碼 Stage 2" in res.rationale


@pytest.mark.anyio
async def test_max_stages_blocks_further_scaling(service):
    """When max stages (2) reached, no further pyramiding is permitted."""
    service._in_memory_stages["NVDA"] = 2  # Already completed 2 stages

    res = await service.evaluate_position(
        ticker="NVDA",
        current_shares=14.38,
        current_price=135.0,
        avg_price=100.0,
        current_peak=135.0,
        active_stop_price=125.0,
        portfolio_total_equity=10000.0,
    )
    assert res is None


@pytest.mark.anyio
async def test_rsi_overbought_or_weak_blocks_pyramiding(service, mock_market):
    """RSI > 78 (exhaustion) or < 52 (momentum loss) prevents scaling in."""
    # RSI = 82 (Overbought)
    mock_market.get_technical_indicators.return_value["rsi"] = 82.0
    res_high = await service.evaluate_position(
        ticker="NVDA",
        current_shares=10.0,
        current_price=112.0,
        avg_price=100.0,
        current_peak=112.0,
        active_stop_price=104.0,
        portfolio_total_equity=10000.0,
    )
    assert res_high is None

    # RSI = 45 (Weak momentum)
    mock_market.get_technical_indicators.return_value["rsi"] = 45.0
    res_low = await service.evaluate_position(
        ticker="NVDA",
        current_shares=10.0,
        current_price=112.0,
        avg_price=100.0,
        current_peak=112.0,
        active_stop_price=104.0,
        portfolio_total_equity=10000.0,
    )
    assert res_low is None


@pytest.mark.anyio
async def test_concentration_cap_clamping(service):
    """When proposed add exceeds max single position cap (18%), clamp size to remaining allowance."""
    # Portfolio equity = 10,000, Max position cap 18% = 1,800 USD
    # Current position: 15 shares * $112 = 1,680 USD (16.8% weight)
    # Remaining capacity = 1,800 - 1,680 = 120 USD (~1.07 shares)
    # Normal 25% add would be 3.75 shares ($420 USD) -> exceeds 18%
    # Clamping should scale down to ~1.07 shares
    res = await service.evaluate_position(
        ticker="NVDA",
        current_shares=15.0,
        current_price=112.0,
        avg_price=100.0,
        current_peak=112.0,
        active_stop_price=105.0,
        portfolio_total_equity=10000.0,
        current_weight_pct=16.8,
    )
    assert res is not None
    assert res.add_shares == 1.07
    assert res.projected_weight_pct <= 18.01


@pytest.mark.anyio
async def test_stage_persistence_with_redis(service):
    """Verify stage advance reads from and writes to Redis cache."""
    stored = {}
    async def fake_get(key):
        return stored.get(key)
    async def fake_set(key, val, ex=None):
        stored[key] = str(val)

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(side_effect=fake_get)
    mock_redis.set = AsyncMock(side_effect=fake_set)

    with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis):
        # Stage 0 initially
        stage0 = await service.get_current_stage("AAPL")
        assert stage0 == 0

        # Advance to Stage 1
        await service.record_stage_advance("AAPL", 1)
        stage1 = await service.get_current_stage("AAPL")
        assert stage1 == 1
        mock_redis.set.assert_called_once()
