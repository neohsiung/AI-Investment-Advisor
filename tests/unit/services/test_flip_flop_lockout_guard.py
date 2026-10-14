import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.trading_protections_service import TradingProtectionsService
from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService
from src.services.automated_trading_service import AutomatedTradingService

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    return engine

def test_flip_flop_blocks_buy_after_recent_sell():
    """If a SELL occurred 2 hours ago, a BUY on the same ticker must be blocked."""
    service = TradingProtectionsService(user_id="test_user")
    service.engine = MagicMock()

    recent_sell_time = datetime.now(timezone.utc) - timedelta(hours=2)
    mock_conn = MagicMock()
    # Row: action, created_at, trade_date
    mock_conn.execute.return_value.fetchall.return_value = [
        ("SELL", recent_sell_time, recent_sell_time.date())
    ]
    service.engine.connect.return_value.__enter__.return_value = mock_conn

    # Check BUY
    result = service.check("NVDA", "BUY")
    assert result is not None
    assert "24h Flip-Flop Lockout" in result
    assert "Blocked BUY" in result
    assert "opposite SELL" in result

def test_trading_protections_fails_open_on_sell():
    """TradingProtectionsService check must never trap positions on SELL."""
    service = TradingProtectionsService(user_id="test_user")
    service.engine = MagicMock()

    recent_buy_time = datetime.now(timezone.utc) - timedelta(hours=3)
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        ("BUY", recent_buy_time, recent_buy_time.date())
    ]
    service.engine.connect.return_value.__enter__.return_value = mock_conn

    # SELL returns None in TradingProtectionsService
    result = service.check("NVDA", "SELL", strategy_name="capital_rotation")
    assert result is None

@pytest.mark.anyio
async def test_automated_trading_blocks_routine_sell_after_recent_buy():
    """AutomatedTradingService skips routine SELL if a BUY occurred within intraday cooldown."""
    settings_repo = MagicMock()
    settings_repo.get.side_effect = lambda uid, key: {
        "ai_trading_enabled": "true",
        "intraday_churn_cooldown_hours": "24.0",
        "auto_trade_threshold": "5",
        "auto_trade_min_threshold": "1",
    }.get(key)

    tx_repo = MagicMock()
    recent_buy_tx = MagicMock()
    recent_buy_tx.ticker = "NVDA"
    recent_buy_tx.action = "BUY"
    recent_buy_tx.entry_category = "trade"
    recent_buy_tx.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    recent_buy_tx.trade_date = (datetime.now(timezone.utc) - timedelta(hours=2)).date()
    tx_repo.get_all_by_user.return_value = [recent_buy_tx]

    auto_svc = AutomatedTradingService(settings_repo=settings_repo, tx_repo=tx_repo)
    res = await auto_svc.evaluate_and_execute_trade(
        user_id="test_user",
        ticker="NVDA",
        action="SELL",
        quantity=1.0,
        confidence_score=8,
        strategy_name="capital_rotation",
    )
    assert res is not None
    assert res.get("status") == "blocked"
    assert "Intraday churn throttler" in res.get("reason", "")

def test_flip_flop_allows_trade_after_cooldown_expired():
    """If the opposite trade occurred 26 hours ago (> 24h cooldown), trade is allowed."""
    service = TradingProtectionsService(user_id="test_user")
    service.engine = MagicMock()

    old_sell_time = datetime.now(timezone.utc) - timedelta(hours=26)
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        ("SELL", old_sell_time, old_sell_time.date())
    ]
    service.engine.connect.return_value.__enter__.return_value = mock_conn

    # BUY should now be allowed (assuming other guards pass)
    with patch.object(service, '_check_max_drawdown', return_value=None), \
         patch.object(service, '_check_ticker_cooldown', return_value=None), \
         patch.object(service, '_check_consecutive_loss_lockout', return_value=None):
        result = service.check("NVDA", "BUY")
        assert result is None

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_unified_risk_gateway_blocks_flip_flop():
    """UnifiedRiskGatewayService must reject orders flagged by flip-flop guard."""
    gateway = UnifiedRiskGatewayService(user_id="test_user")
    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value="NVDA 24h Flip-Flop Lockout: Blocked BUY"):
        res = await gateway.evaluate_trade_risk("NVDA", "BUY", amount_usd=100.0)
        assert res.allowed is False
        assert "TradingProtections" in res.primary_blocker
        assert any("24h Flip-Flop Lockout" in r for r in res.reasons)
