"""
Unit tests for Sentinel Capital Rotation Hotfix:
Pre-Flight Gate, Candidate Sanitization, and Cascade Prevention.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.sentinel_service import SentinelService
from src.services.unified_risk_gateway_service import RiskGatewayResult, RiskSeverity


@pytest.fixture
def mock_dependencies():
    repo = MagicMock()
    repo.engine = MagicMock()
    repo.get_all_thresholds.return_value = {}

    market_service = MagicMock()
    market_service.get_current_prices = AsyncMock(return_value={"META": 500.0, "NVDA": 130.0, "TSM": 180.0})

    tx_service = MagicMock()
    tx_service.get_user_tickers.return_value = ["META"]
    tx_service.get_position_lots.return_value = []

    settings_service = MagicMock()
    settings_map = {
        "capital_rotation_enabled": True,
        "rotation_min_score_delta": 2.0,
        "autonomous_exit_enabled": True,
    }
    settings_service.get_setting.side_effect = lambda k, default=None, user_id=None: settings_map.get(k, default)

    keyword_service = MagicMock()
    mock_buffer = MagicMock()
    mock_buffer.try_acquire = AsyncMock(return_value=True)

    return {
        "repo": repo,
        "market": market_service,
        "tx": tx_service,
        "settings": settings_service,
        "keyword": keyword_service,
        "buffer": mock_buffer,
    }


@pytest.fixture
def mock_sentinel(mock_dependencies):
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=mock_dependencies["buffer"]), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        service = SentinelService(
            user_id="test_user_hotfix",
            repo=mock_dependencies["repo"],
            market_service=mock_dependencies["market"],
            transaction_service=mock_dependencies["tx"],
            settings_service=mock_dependencies["settings"],
            keyword_service=mock_dependencies["keyword"],
        )
        return service


@pytest.mark.asyncio
async def test_rotation_candidate_disqualified_by_trading_protections(mock_sentinel):
    """Test that a candidate in 24h flip-flop lockout is disqualified during candidate screening."""
    active_holdings = {
        "META": {"shares": 10.0, "current_price": 500.0, "avg_price": 450.0, "weight": 0.5}
    }
    candidates = [
        {"ticker": "NVDA", "composite_score": 9.5}  # High score, but in flip-flop lockout
    ]

    mock_sentinel._acquire_cooldown = AsyncMock(return_value=True)

    with patch("src.services.trading_protections_service.TradingProtectionsService.check") as mock_check:
        # Simulate NVDA is blocked by 24h flip-flop lockout
        mock_check.side_effect = lambda ticker, action, strategy_name, **kw: (
            "NVDA 24h Flip-Flop Lockout: Blocked BUY" if ticker == "NVDA" else None
        )

        triggers = await mock_sentinel._check_capital_rotation_opportunities(
            current_allocation=active_holdings,
            candidates_override=candidates,
        )

        assert len(triggers) == 0, "Candidate in flip-flop lockout should be disqualified and produce no triggers"


@pytest.mark.asyncio
async def test_rotation_swap_aborted_when_target_buy_blocked_by_preflight_gateway(mock_sentinel):
    """Test that if candidate is approved by opportunity cost, pre-flight gate blocks trigger if target BUY fails risk gateway."""
    active_holdings = {
        "META": {"shares": 10.0, "current_price": 500.0, "avg_price": 450.0, "weight": 0.5}
    }
    candidates = [
        {"ticker": "TSM", "composite_score": 9.0}
    ]

    mock_sentinel._acquire_cooldown = AsyncMock(return_value=True)

    # Allow candidate through initial protection check
    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
         patch("src.services.exit_compositor_service.ExitCompositorService.score_exit") as mock_exit, \
         patch("src.services.opportunity_cost_service.OpportunityCostService.evaluate_swap") as mock_swap, \
         patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService.evaluate_trade_risk") as mock_gw:

        mock_exit.return_value = {"composite_score": 5.0, "breakdown": []}
        
        # Opportunity cost says should swap
        mock_decision = MagicMock()
        mock_decision.should_swap = True
        mock_decision.raw_delta = 4.0
        mock_decision.net_opportunity_delta = 3.5
        mock_decision.friction_hurdle = 0.5
        mock_decision.reason = "Clear advantage"
        mock_swap.return_value = mock_decision

        # But UnifiedRiskGateway blocks the BUY
        mock_gw.return_value = RiskGatewayResult(
            allowed=False,
            severity=RiskSeverity.BLOCKED,
            primary_blocker="TradingProtections",
            reasons=["TSM cooldown: alpha drawdown cooldown active"],
            guard_details={},
            evaluated_at="2026-10-15T00:00:00Z",
        )

        triggers = await mock_sentinel._check_capital_rotation_opportunities(
            current_allocation=active_holdings,
            candidates_override=candidates,
        )

        assert len(triggers) == 0, "Trigger must be aborted if Pre-Flight UnifiedRiskGateway blocks the target BUY"


@pytest.mark.asyncio
async def test_execute_exit_triggers_aborts_rotation_sell_when_preflight_fails(mock_sentinel):
    """Test that _handle_position_exits will NOT sell the holding if Pre-Flight check on target BUY fails."""
    trigger = {
        "id": "capital_rotation_META_NVDA",
        "action": "trigger_exit",
        "ticker": "META",
        "target_ticker": "NVDA",
        "strategy_name": "capital_rotation",
        "sell_quantity": 2.0,
        "current_price": 500.0,
        "candidate_score": 9.0,
        "composite_score": 7.0,
        "rationale": "Rotate META to NVDA",
    }

    mock_sentinel._acquire_cooldown = AsyncMock(return_value=True)
    mock_auto_trade = MagicMock()
    mock_auto_trade.evaluate_and_execute_trade = AsyncMock()

    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=mock_auto_trade), \
         patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService.evaluate_trade_risk") as mock_gw:
        # Pre-flight fails
        mock_gw.return_value = RiskGatewayResult(
            allowed=False,
            severity=RiskSeverity.BLOCKED,
            primary_blocker="TradingProtections",
            reasons=["NVDA 24h Flip-Flop Lockout"],
            guard_details={},
            evaluated_at="2026-10-15T00:00:00Z",
        )

        await mock_sentinel._handle_position_exits([trigger])

        # Verify that SELL was NEVER executed
        mock_auto_trade.evaluate_and_execute_trade.assert_not_called()


@pytest.mark.asyncio
async def test_execute_exit_triggers_locks_rotation_on_catastrophic_buy_failure(mock_sentinel):
    """Test that if SELL succeeds but BUY unexpectedly fails, rotation is locked for 6 hours."""
    trigger = {
        "id": "capital_rotation_META_NVDA",
        "action": "trigger_exit",
        "ticker": "META",
        "target_ticker": "NVDA",
        "strategy_name": "capital_rotation",
        "sell_quantity": 2.0,
        "current_price": 500.0,
        "candidate_score": 9.0,
        "composite_score": 7.0,
        "rationale": "Rotate META to NVDA",
    }

    mock_sentinel._acquire_cooldown = AsyncMock(return_value=True)
    mock_sentinel._clear_position_peak_and_stop = AsyncMock()
    
    mock_auto_trade = MagicMock()
    # First call (SELL) succeeds, Second call (BUY) fails
    mock_auto_trade.evaluate_and_execute_trade = AsyncMock(side_effect=[
        {"status": "executed", "order_id": "123"},
        {"status": "error", "reason": "Broker API timeout"},
    ])

    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=mock_auto_trade), \
         patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService.evaluate_trade_risk") as mock_gw:
        
        mock_gw.return_value = RiskGatewayResult(
            allowed=True,
            severity=RiskSeverity.NORMAL,
            primary_blocker=None,
            reasons=[],
            guard_details={},
            evaluated_at="2026-10-15T00:00:00Z",
        )

        await mock_sentinel._handle_position_exits([trigger])

        # Verify SELL was called, BUY was called
        assert mock_auto_trade.evaluate_and_execute_trade.call_count == 2
        # Verify 6-hour (21600s) cooldown lock was acquired on failure
        mock_sentinel._acquire_cooldown.assert_any_call(
            f"capital_rotation_eval:{mock_sentinel.user_id}", 21600, fail_open=False
        )
