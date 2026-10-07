import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
from datetime import datetime, timezone

from src.services.alpha_decay_service import AlphaDecayService, AlphaDecayAssessment
from src.services.sentinel_service import SentinelService


@pytest.fixture
def mock_sentinel():
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer"), \
         patch("src.repositories.sentinel_repository.AlchemySentinelRepository"):

        settings_svc = MagicMock()
        settings_svc.get_setting.side_effect = lambda key, default=None, *args: {
            "enable_stagnation_pruning": True,
            "stagnation_prune_min_days": 15,
            "stop_loss_pct": -8.0,
            "take_profit_pct": 20.0,
        }.get(key, default)

        market_svc = MagicMock()
        market_svc.get_current_price.return_value = 100.0
        market_svc.get_technical_indicators.return_value = {
            "sma_20": 105.0,
            "rsi": 40.0,
            "macd_signal": "bearish",
        }
        # SPY +10% over period
        market_svc.get_ohlcv.return_value = {
            "close": [500.0, 550.0]
        }

        tx_svc = MagicMock()
        tx_df = pd.DataFrame([
            {"ticker": "STAG", "action": "BUY", "trade_date": "2026-08-01 00:00:00"}
        ])
        tx_svc.get_transactions.return_value = tx_df

        sentinel = SentinelService(
            user_id="test_user",
            settings_service=settings_svc,
            market_service=market_svc,
            transaction_service=tx_svc,
        )
        return sentinel


@pytest.mark.asyncio
async def test_stagnation_pruning_triggers_on_flat_deadlock(mock_sentinel):
    """Positions held > 15 days with flat return and dead momentum trigger stagnation pruning."""
    positions = {
        "STAG": {
            "shares": 10.0,
            "current_price": 99.0,
            "avg_price": 100.0,  # -1.0% return
            "weight": 0.10,
            "open_date": datetime(2026, 8, 1, tzinfo=timezone.utc),
        }
    }
    mock_sentinel._get_current_allocation = AsyncMock(return_value=positions)

    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=False):
        triggers = await mock_sentinel._check_position_exits()

    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 1
    trig = stagnation_triggers[0]
    assert trig["ticker"] == "STAG"
    assert trig["sell_quantity"] == 10.0
    assert "死資金停滯修剪觸發" in trig["text"]
    assert trig["strategy_name"] == "stagnation_pruning"


@pytest.mark.asyncio
async def test_stagnation_pruning_triggers_on_alpha_drag(mock_sentinel):
    """Positions trailing SPY by >= 5% despite positive nominal return trigger stagnation pruning."""
    positions = {
        "DRAG": {
            "shares": 5.0,
            "current_price": 102.0,
            "avg_price": 100.0,  # +2.0% return vs SPY +10.0% -> alpha lag -8.0%
            "weight": 0.08,
            "open_date": datetime(2026, 8, 1, tzinfo=timezone.utc),
        }
    }
    mock_sentinel._get_current_allocation = AsyncMock(return_value=positions)

    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=False):
        triggers = await mock_sentinel._check_position_exits()

    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 1
    trig = stagnation_triggers[0]
    assert trig["ticker"] == "DRAG"
    assert "大盤落後 Alpha 拖累" in trig["text"]


@pytest.mark.asyncio
async def test_stagnation_pruning_triggers_on_sub_stop_underperformer(mock_sentinel):
    """Positions down -5% (not hitting -8% stop loss) with broken 20MA trigger stagnation pruning."""
    positions = {
        "SUBSTOP": {
            "shares": 8.0,
            "current_price": 95.0,
            "avg_price": 100.0,  # -5.0% return
            "weight": 0.08,
            "open_date": datetime(2026, 8, 1, tzinfo=timezone.utc),
        }
    }
    mock_sentinel._get_current_allocation = AsyncMock(return_value=positions)

    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=False):
        triggers = await mock_sentinel._check_position_exits()

    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 1
    assert stagnation_triggers[0]["ticker"] == "SUBSTOP"


@pytest.mark.asyncio
async def test_stagnation_pruning_exempts_certified_winner(mock_sentinel):
    """Certified long-term compounders are protected from stagnation pruning."""
    positions = {
        "WINNER": {
            "shares": 10.0,
            "current_price": 100.0,
            "avg_price": 100.0,  # flat return
            "weight": 0.15,
            "open_date": datetime(2026, 8, 1, tzinfo=timezone.utc),
        }
    }
    mock_sentinel._get_current_allocation = AsyncMock(return_value=positions)

    # Exempt via LongTermWinnerService
    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=True):
        triggers = await mock_sentinel._check_position_exits()

    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 0


@pytest.mark.asyncio
async def test_stagnation_pruning_exempts_young_holding(mock_sentinel):
    """Positions held less than grace period (15 days) are not pruned."""
    positions = {
        "FRESH": {
            "shares": 10.0,
            "current_price": 100.0,
            "avg_price": 100.0,
            "weight": 0.10,
            "open_date": datetime.now(timezone.utc),  # 0 days old
        }
    }
    mock_sentinel._get_current_allocation = AsyncMock(return_value=positions)

    with patch("src.services.long_term_winner_service.LongTermWinnerService.is_winner", return_value=False):
        triggers = await mock_sentinel._check_position_exits()

    stagnation_triggers = [t for t in triggers if t.get("strategy_name") == "stagnation_pruning"]
    assert len(stagnation_triggers) == 0
