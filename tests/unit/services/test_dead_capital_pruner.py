"""
Unit tests for Dead-Capital Stagnation Pruner in SentinelService.
死資金停滯修剪與贏家保護單元測試。
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.sentinel_service import SentinelService


@pytest.fixture
def mock_sentinel_dependencies():
    with patch("src.services.sentinel_service.SettingsService") as mock_settings_cls, \
         patch("src.services.sentinel_service.MarketDataService") as mock_market_cls, \
         patch("src.services.sentinel_service.TransactionService") as mock_tx_cls, \
         patch("src.services.sentinel_service.AlchemySentinelRepository"), \
         patch("src.services.sentinel_service.RiskKeywordService"), \
         patch("src.services.sentinel_service.CouncilService"):
        
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda key, default=None, *args, **kwargs: {
            "enable_stagnation_pruning": True,
            "stagnation_prune_min_days": 15,
            "enable_fixed_stops": True,
            "stop_loss_pct": 0.05,
            "enable_trailing_stops": True,
            "trailing_stop_pct": 0.03,
            "max_single_position_weight": 25.0,
            "cash_reserve_buffer_pct": 0.15,
        }.get(key, default)
        mock_settings_cls.return_value = mock_settings

        mock_market = MagicMock()
        mock_market.get_ohlcv.return_value = {"close": [500.0, 510.0]}
        mock_market.get_technical_indicators.return_value = {
            "sma_20": 105.0,
            "rsi": 42.0,
            "macd_signal": "bearish",
            "atr": 2.5,
        }
        mock_market_cls.return_value = mock_market

        mock_tx = MagicMock()
        mock_tx_cls.return_value = mock_tx

        sentinel = SentinelService(user_id="test_user")
        sentinel.settings_service = mock_settings
        sentinel.market_service = mock_market
        sentinel.transaction_service = mock_tx

        yield sentinel, mock_settings, mock_market, mock_tx


@pytest.mark.asyncio
async def test_sentinel_triggers_stagnation_pruning_on_dead_capital(mock_sentinel_dependencies):
    sentinel, *_ = mock_sentinel_dependencies

    # 模擬 1 檔持倉 20 天、損益 0.0% (橫盤)、現價低於 20MA 的死資金部位
    current_allocation = {
        "STAG": {
            "shares": 10.0,
            "current_price": 100.0,
            "avg_price": 100.0,
            "market_value": 1000.0,
            "weight": 10.0,
            "open_date": datetime.now(timezone.utc) - timedelta(days=20),
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=current_allocation)
    sentinel._get_peak_price = AsyncMock(return_value=101.0)
    sentinel._acquire_cooldown = AsyncMock(return_value=True)

    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=False):
        triggers = await sentinel._check_position_exits()

    # 驗證觸發死資金修剪
    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 1
    trig = stagnation_triggers[0]
    assert trig["ticker"] == "STAG"
    assert trig["action"] == "trigger_exit"
    assert trig["sell_quantity"] == 10.0
    assert trig["holding_days"] >= 15
    assert "死資金停滯修剪觸發" in trig["text"]


@pytest.mark.asyncio
async def test_sentinel_exempts_long_term_winners_from_stagnation_pruning(mock_sentinel_dependencies):
    sentinel, *_ = mock_sentinel_dependencies

    # 模擬 1 檔持倉 25 天，但屬於認證長期成長贏家的核心部位 (如 NVDA/AAPL)
    current_allocation = {
        "WINR": {
            "shares": 10.0,
            "current_price": 100.0,
            "avg_price": 100.0,
            "market_value": 1000.0,
            "weight": 10.0,
            "open_date": datetime.now(timezone.utc) - timedelta(days=25),
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=current_allocation)
    sentinel._get_peak_price = AsyncMock(return_value=101.0)
    sentinel._acquire_cooldown = AsyncMock(return_value=True)

    # 認證為長期贏家
    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=True):
        triggers = await sentinel._check_position_exits()

    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 0  # 豁免修剪，全額保護長線複利


@pytest.mark.asyncio
async def test_sentinel_exempts_recently_opened_position(mock_sentinel_dependencies):
    sentinel, *_ = mock_sentinel_dependencies

    # 模擬進場僅 5 天的部位 (未達 15 天觀察期)
    current_allocation = {
        "FRESH": {
            "shares": 10.0,
            "current_price": 100.0,
            "avg_price": 100.0,
            "market_value": 1000.0,
            "weight": 10.0,
            "open_date": datetime.now(timezone.utc) - timedelta(days=5),
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=current_allocation)
    sentinel._get_peak_price = AsyncMock(return_value=101.0)
    sentinel._acquire_cooldown = AsyncMock(return_value=True)

    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=False):
        triggers = await sentinel._check_position_exits()

    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 0
