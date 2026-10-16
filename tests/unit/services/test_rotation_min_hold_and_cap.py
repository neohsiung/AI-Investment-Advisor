"""Capital rotation: minimum holding period (fail closed on unknown age) and the batch order cap on rotation buys."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.services.sentinel_service import SentinelService
from src.services.unified_risk_gateway_service import RiskGatewayResult, RiskSeverity

SETTINGS = {"capital_rotation_enabled": True, "rotation_min_score_delta": 2.0, "autonomous_exit_enabled": True,
            "rotation_min_holding_days": 5, "batch_deploy_max_order_usd": 100.0}


@pytest.fixture
def sentinel():
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None, user_id=None: SETTINGS.get(k, default)
    tx = MagicMock()
    tx.get_position_lots.return_value = []
    buf = MagicMock(); buf.try_acquire = AsyncMock(return_value=True)
    repo = MagicMock(); repo.engine = MagicMock(); repo.get_all_thresholds.return_value = {}
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=buf), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        s = SentinelService(user_id="u_rot", repo=repo, market_service=MagicMock(), transaction_service=tx,
                            settings_service=settings, keyword_service=MagicMock())
    s._acquire_cooldown = AsyncMock(return_value=True)
    return s


def _buys(days_ago):
    return pd.DataFrame([{"ticker": "GOOGL", "action": "BUY",
                          "trade_date": datetime.now() - timedelta(days=days_ago)}]) if days_ago is not None \
        else pd.DataFrame(columns=["ticker", "action", "trade_date"])


async def _rotate(s, buys_df, info_extra=None):
    s.transaction_service.get_transactions.return_value = buys_df
    holdings = {"GOOGL": {"shares": 0.3, "current_price": 340.0, "avg_price": 340.0, "weight": 5.0, **(info_extra or {})}}
    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
         patch("src.services.exit_compositor_service.ExitCompositorService.score_exit",
               new=AsyncMock(return_value={"composite_score": 4.3, "breakdown": []})) as score_exit, \
         patch("src.services.opportunity_cost_service.OpportunityCostService.evaluate_swap") as swap, \
         patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService.evaluate_trade_risk",
               new=AsyncMock(return_value=RiskGatewayResult(True, RiskSeverity.NORMAL, None, [], {}, "t"))):
        d = MagicMock(should_swap=True, raw_delta=2.4, net_opportunity_delta=2.38, friction_hurdle=2.0, reason="ok")
        swap.return_value = d
        trig = await s._check_capital_rotation_opportunities(current_allocation=holdings,
                                                             candidates_override=[{"ticker": "NVDA", "composite_score": 8.0}])
    return trig, score_exit, swap


@pytest.mark.asyncio
async def test_position_bought_today_is_not_rotated_out(sentinel):
    trig, score_exit, swap = await _rotate(sentinel, _buys(0))
    assert trig == []
    swap.assert_not_called()          # never even evaluated: too young to sell


@pytest.mark.asyncio
async def test_old_enough_position_can_rotate(sentinel):
    trig, _, _ = await _rotate(sentinel, _buys(10))
    assert len(trig) == 1 and trig[0]["ticker"] == "GOOGL" and trig[0]["target_ticker"] == "NVDA"


@pytest.mark.asyncio
async def test_unknown_holding_age_fails_closed(sentinel):
    trig, _, swap = await _rotate(sentinel, _buys(None))
    assert trig == []
    swap.assert_not_called()


@pytest.mark.asyncio
async def test_open_date_in_allocation_info_is_used(sentinel):
    trig, _, _ = await _rotate(sentinel, _buys(None), {"open_date": datetime.now() - timedelta(days=9)})
    assert len(trig) == 1


@pytest.mark.asyncio
async def test_rotation_buy_is_capped_at_batch_order_limit(sentinel):
    trigger = {"id": "r", "action": "trigger_exit", "ticker": "META", "target_ticker": "NVDA",
               "strategy_name": "capital_rotation", "sell_quantity": 0.5, "current_price": 500.0,   # proceeds $250
               "candidate_score": 8.0, "composite_score": 7.0, "rationale": "rotate"}
    sentinel._clear_position_peak_and_stop = AsyncMock()
    auto = MagicMock()
    auto.evaluate_and_execute_trade = AsyncMock(return_value={"status": "executed"})
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=auto), \
         patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService.evaluate_trade_risk",
               new=AsyncMock(return_value=RiskGatewayResult(True, RiskSeverity.NORMAL, None, [], {}, "t"))):
        await sentinel._handle_position_exits([trigger])
    buy = [c for c in auto.evaluate_and_execute_trade.call_args_list if c.kwargs.get("action") == "BUY"]
    assert len(buy) == 1 and buy[0].kwargs["quantity"] == pytest.approx(100.0)
