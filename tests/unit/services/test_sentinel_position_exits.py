import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.sentinel_service import SentinelService

@pytest.fixture
def mock_dependencies():
    repo = MagicMock()
    repo.engine = MagicMock()
    repo.get_all_thresholds.return_value = {}
    
    market_service = MagicMock()
    market_service.get_current_prices = AsyncMock(return_value={"AAPL": 90.0, "NVDA": 130.0, "MSFT": 105.0})
    
    tx_service = MagicMock()
    tx_service.get_user_tickers.return_value = ["AAPL", "NVDA", "MSFT"]
    tx_service.get_position_lots.return_value = []
    
    settings_service = MagicMock()
    settings_map = {
        "enable_fixed_stops": False,  # Default for long-term investing
        "stop_loss_pct": 8.0,
        "take_profit_pct": 20.0,
        "auto_trade_threshold_sell": 6.0,
        "autonomous_exit_enabled": True,
        "capital_rotation_enabled": True,
        "rotation_min_score_delta": 2.0,
        "rebalance_risk_diversification_enabled": True,
        "max_single_position_weight": 25.0,
    }
    def get_setting(key, default=None, user_id=None):
        return settings_map.get(key, default)
    settings_service.get_setting.side_effect = get_setting
    settings_service._settings_map = settings_map
    
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
def sentinel(mock_dependencies):
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=mock_dependencies["buffer"]), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        service = SentinelService(
            user_id="test_user",
            repo=mock_dependencies["repo"],
            market_service=mock_dependencies["market"],
            transaction_service=mock_dependencies["tx"],
            settings_service=mock_dependencies["settings"],
            keyword_service=mock_dependencies["keyword"],
        )
        return service


@pytest.mark.anyio
async def test_check_position_exits_default_long_term_no_fixed_stops(sentinel):
    """Verify default long-term mode does NOT trigger fixed stop-loss (-10%) or take-profit (+30%)."""
    mock_allocation = {
        "AAPL": {
            "shares": 10.0,
            "quantity": 10.0,
            "weight": 15.0,
            "market_value": 900.0,
            "current_price": 90.0,
            "avg_price": 100.0,  # -10% drawdown
        },
        "NVDA": {
            "shares": 5.0,
            "quantity": 5.0,
            "weight": 15.0,
            "market_value": 650.0,
            "current_price": 130.0,
            "avg_price": 100.0,  # +30% profit
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    sentinel._acquire_cooldown = AsyncMock(return_value=False)  # multi-factor on cooldown
    sentinel._check_capital_rotation_opportunities = AsyncMock(return_value=[])
    
    triggers = await sentinel._check_position_exits()
    # In long-term mode, neither -10% nor +30% should trigger mechanical fixed exits
    assert len(triggers) == 0


@pytest.mark.anyio
async def test_check_position_exits_stop_loss_when_enabled(sentinel, mock_dependencies):
    """Verify stop loss triggers when position return falls below -stop_loss_pct AND enable_fixed_stops is True."""
    mock_dependencies["settings"]._settings_map["enable_fixed_stops"] = True
    mock_allocation = {
        "AAPL": {
            "shares": 10.0,
            "quantity": 10.0,
            "weight": 15.0,
            "market_value": 900.0,
            "current_price": 90.0,
            "avg_price": 100.0,
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    sentinel._check_capital_rotation_opportunities = AsyncMock(return_value=[])
    
    triggers = await sentinel._check_position_exits()
    assert len(triggers) == 1
    assert triggers[0]["ticker"] == "AAPL"
    assert triggers[0]["strategy_name"] == "stop_loss"
    assert triggers[0]["trigger_type"] == "stop_loss"
    assert triggers[0]["return_pct"] == -10.0
    assert triggers[0]["sell_quantity"] == 10.0


@pytest.mark.anyio
async def test_check_position_exits_take_profit_when_enabled(sentinel, mock_dependencies):
    """Verify take profit triggers when position return exceeds +take_profit_pct AND enable_fixed_stops is True."""
    mock_dependencies["settings"]._settings_map["enable_fixed_stops"] = True
    mock_allocation = {
        "NVDA": {
            "shares": 5.0,
            "quantity": 5.0,
            "weight": 15.0,
            "market_value": 650.0,
            "current_price": 130.0,
            "avg_price": 100.0,
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    sentinel._check_capital_rotation_opportunities = AsyncMock(return_value=[])
    
    triggers = await sentinel._check_position_exits()
    assert len(triggers) == 1
    assert triggers[0]["ticker"] == "NVDA"
    assert triggers[0]["strategy_name"] == "take_profit"
    assert triggers[0]["trigger_type"] == "take_profit"
    assert triggers[0]["return_pct"] == 30.0
    assert triggers[0]["sell_quantity"] == 5.0


@pytest.mark.anyio
async def test_check_position_exits_normal_holding(sentinel):
    """Verify normal holding within range does not trigger hard exits."""
    mock_allocation = {
        "MSFT": {
            "shares": 8.0,
            "quantity": 8.0,
            "weight": 10.0,
            "market_value": 840.0,
            "current_price": 105.0,
            "avg_price": 100.0,
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    sentinel._acquire_cooldown = AsyncMock(return_value=False)
    sentinel._check_capital_rotation_opportunities = AsyncMock(return_value=[])
    
    triggers = await sentinel._check_position_exits()
    assert len(triggers) == 0


@pytest.mark.anyio
async def test_check_position_exits_multi_factor(sentinel):
    """Verify multi-factor thesis exit triggers when ExitCompositor composite_score >= sell_threshold."""
    mock_allocation = {
        "MSFT": {
            "shares": 8.0,
            "quantity": 8.0,
            "weight": 10.0,
            "market_value": 840.0,
            "current_price": 105.0,
            "avg_price": 100.0,
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    sentinel._acquire_cooldown = AsyncMock(return_value=True)
    sentinel._check_capital_rotation_opportunities = AsyncMock(return_value=[])
    
    mock_exit_compositor = MagicMock()
    mock_exit_compositor.score_exit = AsyncMock(return_value={
        "composite_score": 7.8,
        "breakdown": [{"agent": "momentum_reversal", "confidence": 9.0}],
        "rationale": "Breakdown below 20MA and thesis violated",
    })
    
    with patch("src.services.exit_compositor_service.ExitCompositorService", return_value=mock_exit_compositor):
        triggers = await sentinel._check_position_exits()
        assert len(triggers) == 1
        assert triggers[0]["ticker"] == "MSFT"
        assert triggers[0]["strategy_name"] == "position_exit"
        assert triggers[0]["composite_score"] == 7.8


@pytest.mark.anyio
async def test_check_position_exits_capital_rotation_success(sentinel):
    """Verify capital rotation triggers when a superior candidate has score advantage >= delta."""
    mock_allocation = {
        "INTC": {
            "shares": 20.0,
            "quantity": 20.0,
            "weight": 10.0,
            "market_value": 600.0,
            "current_price": 30.0,
            "avg_price": 35.0,
        }
    }
    sentinel._acquire_cooldown = AsyncMock(return_value=True)
    
    # Candidate opportunity with high score (8.8)
    candidates_override = [
        {"ticker": "TSM", "composite_score": 8.8}
    ]
    
    # Holding has exit_score = 4.5 -> retention conviction = 10.0 - 4.5 = 5.5
    # Delta = 8.8 - 5.5 = 3.3 >= rotation_min_score_delta (2.0)
    mock_exit_compositor = MagicMock()
    mock_exit_compositor.score_exit = AsyncMock(return_value={
        "composite_score": 4.5,
        "breakdown": [{"agent": "fundamental", "confidence": 4.5}],
    })
    
    with patch("src.services.exit_compositor_service.ExitCompositorService", return_value=mock_exit_compositor):
        triggers = await sentinel._check_capital_rotation_opportunities(
            mock_allocation, candidates_override=candidates_override
        )
        assert len(triggers) == 1
        trig = triggers[0]
        assert trig["ticker"] == "INTC"
        assert trig["target_ticker"] == "TSM"
        assert trig["strategy_name"] == "capital_rotation"
        assert trig["candidate_score"] == 8.8
        assert trig["holding_conviction"] == 5.5
        assert trig["score_delta"] == 3.3


@pytest.mark.anyio
async def test_check_position_exits_capital_rotation_below_delta(sentinel):
    """Verify capital rotation does NOT trigger if candidate advantage is below rotation_min_score_delta."""
    mock_allocation = {
        "INTC": {
            "shares": 20.0,
            "quantity": 20.0,
            "weight": 10.0,
            "market_value": 600.0,
            "current_price": 30.0,
            "avg_price": 30.0,
        }
    }
    sentinel._acquire_cooldown = AsyncMock(return_value=True)
    
    # Candidate score 7.5
    candidates_override = [
        {"ticker": "QCOM", "composite_score": 7.5}
    ]
    
    # Holding has exit_score = 3.0 -> retention conviction = 7.0
    # Delta = 7.5 - 7.0 = 0.5 < rotation_min_score_delta (2.0)
    mock_exit_compositor = MagicMock()
    mock_exit_compositor.score_exit = AsyncMock(return_value={
        "composite_score": 3.0,
        "breakdown": [],
    })
    
    with patch("src.services.exit_compositor_service.ExitCompositorService", return_value=mock_exit_compositor):
        triggers = await sentinel._check_capital_rotation_opportunities(
            mock_allocation, candidates_override=candidates_override
        )
        assert len(triggers) == 0


@pytest.mark.anyio
async def test_check_allocation_drift_rebalance_disabled(sentinel, mock_dependencies):
    """Verify allocation drift skips concentration rebalance when rebalance_risk_diversification_enabled is False."""
    mock_dependencies["settings"]._settings_map["rebalance_risk_diversification_enabled"] = False
    mock_allocation = {
        "AAPL": {
            "shares": 50.0,
            "quantity": 50.0,
            "weight": 35.0,  # exceeds 25% max
            "market_value": 4500.0,
            "current_price": 90.0,
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    
    triggers = await sentinel._check_allocation_drift()
    assert len(triggers) == 0


@pytest.mark.anyio
async def test_handle_position_exits_submits_trades(sentinel):
    """Verify _handle_position_exits passes exit triggers to AutomatedTradingService."""
    exit_triggers = [
        {
            "id": "stop_loss_AAPL_test",
            "action": "trigger_exit",
            "ticker": "AAPL",
            "sell_quantity": 10.0,
            "strategy_name": "stop_loss",
            "current_price": 90.0,
            "avg_price": 100.0,
            "return_pct": -10.0,
        }
    ]
    sentinel._acquire_cooldown = AsyncMock(return_value=True)
    
    mock_auto_trade = MagicMock()
    mock_auto_trade.evaluate_and_execute_trade = AsyncMock(return_value={"status": "success"})
    
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=mock_auto_trade):
        await sentinel._handle_position_exits(exit_triggers)
        
        mock_auto_trade.evaluate_and_execute_trade.assert_called_once()
        call_kwargs = mock_auto_trade.evaluate_and_execute_trade.call_args.kwargs
        assert call_kwargs["ticker"] == "AAPL"
        assert call_kwargs["action"] == "SELL"
        assert call_kwargs["quantity"] == 10.0
        assert call_kwargs["strategy_name"] == "stop_loss"
        assert call_kwargs["confidence_score"] == 10.0


@pytest.mark.anyio
async def test_handle_position_exits_capital_rotation_executes_buy(sentinel):
    """Verify _handle_position_exits on capital_rotation executes SELL and then BUY target."""
    exit_triggers = [
        {
            "id": "capital_rotation_INTC_TSM_test",
            "action": "trigger_exit",
            "ticker": "INTC",
            "target_ticker": "TSM",
            "sell_quantity": 20.0,
            "strategy_name": "capital_rotation",
            "current_price": 30.0,
            "composite_score": 6.0,
            "candidate_score": 8.8,
            "rationale": "Rotate INTC into TSM",
        }
    ]
    sentinel._acquire_cooldown = AsyncMock(return_value=True)
    
    mock_auto_trade = MagicMock()
    mock_auto_trade.evaluate_and_execute_trade = AsyncMock(return_value={"status": "success"})
    
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=mock_auto_trade):
        await sentinel._handle_position_exits(exit_triggers)
        
        assert mock_auto_trade.evaluate_and_execute_trade.call_count == 2
        calls = mock_auto_trade.evaluate_and_execute_trade.call_args_list
        
        # First call: SELL INTC
        assert calls[0].kwargs["ticker"] == "INTC"
        assert calls[0].kwargs["action"] == "SELL"
        assert calls[0].kwargs["quantity"] == 20.0
        assert calls[0].kwargs["strategy_name"] == "capital_rotation"
        
        # Second call: BUY TSM with proceeds ($600.0)
        assert calls[1].kwargs["ticker"] == "TSM"
        assert calls[1].kwargs["action"] == "BUY"
        assert calls[1].kwargs["quantity"] == 600.0
        assert calls[1].kwargs["confidence_score"] == 8.8
        assert calls[1].kwargs["strategy_name"] == "capital_rotation"


@pytest.mark.anyio
async def test_handle_position_exits_cooldown_dedup(sentinel):
    """Verify _handle_position_exits skips duplicate executions within cooldown."""
    exit_triggers = [
        {
            "id": "stop_loss_AAPL_test",
            "action": "trigger_exit",
            "ticker": "AAPL",
            "sell_quantity": 10.0,
            "strategy_name": "stop_loss",
            "current_price": 90.0,
            "avg_price": 100.0,
            "return_pct": -10.0,
        }
    ]
    sentinel._acquire_cooldown = AsyncMock(return_value=False)
    
    mock_auto_trade = MagicMock()
    mock_auto_trade.evaluate_and_execute_trade = AsyncMock()
    
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=mock_auto_trade):
        await sentinel._handle_position_exits(exit_triggers)
        mock_auto_trade.evaluate_and_execute_trade.assert_not_called()


@pytest.mark.anyio
async def test_check_position_exits_trailing_stop_loss(sentinel, mock_dependencies):
    """Verify Trailing Stop Loss triggers when price draws down > 6% from its high-water mark."""
    mock_dependencies["settings"]._settings_map["enable_trailing_stops"] = True
    mock_dependencies["settings"]._settings_map["trailing_stop_pct"] = 6.0

    # Stock bought at $100, previously reached $130, now pulled back to $121 (drawdown: (121-130)/130 = -6.92%)
    sentinel._position_peaks["NVDA"] = 130.0

    mock_allocation = {
        "NVDA": {
            "shares": 10.0,
            "quantity": 10.0,
            "weight": 12.0,
            "current_price": 121.0,
            "avg_price": 100.0,
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    sentinel._check_capital_rotation_opportunities = AsyncMock(return_value=[])

    triggers = await sentinel._check_position_exits()
    assert len(triggers) == 1
    t = triggers[0]
    assert t["ticker"] == "NVDA"
    assert t["strategy_name"] == "trailing_stop_loss"
    assert t["trigger_type"] == "trailing_stop_loss"
    assert t["sell_quantity"] == 10.0
    assert t["peak_price"] == 130.0
    assert t["drawdown_from_peak_pct"] == -6.92
    assert "移動停損觸發" in t["text"]


@pytest.mark.anyio
async def test_check_position_exits_ratchet_take_profit(sentinel, mock_dependencies):
    """Verify Ratchet Take-Profit triggers 50% partial exit when return exceeds +25%."""
    mock_dependencies["settings"]._settings_map["enable_fixed_stops"] = True
    mock_dependencies["settings"]._settings_map["enable_ratchet_take_profit"] = True

    mock_allocation = {
        "TSLA": {
            "shares": 10.0,
            "quantity": 10.0,
            "weight": 15.0,
            "current_price": 130.0,
            "avg_price": 100.0,
        }
    }
    sentinel._get_current_allocation = AsyncMock(return_value=mock_allocation)
    sentinel._check_capital_rotation_opportunities = AsyncMock(return_value=[])

    triggers = await sentinel._check_position_exits()
    assert len(triggers) == 1
    t = triggers[0]
    assert t["ticker"] == "TSLA"
    assert t["strategy_name"] == "take_profit"
    assert t["sell_quantity"] == 5.0  # 50% scale out
    assert "階梯停利觸發" in t["text"]

