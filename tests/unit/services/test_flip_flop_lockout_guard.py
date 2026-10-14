import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from src.services.trading_protections_service import TradingProtectionsService
from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService

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

def test_flip_flop_blocks_routine_sell_after_recent_buy():
    """If a BUY occurred 3 hours ago, a routine (non-stop-loss) SELL must be blocked."""
    service = TradingProtectionsService(user_id="test_user")
    service.engine = MagicMock()

    recent_buy_time = datetime.now(timezone.utc) - timedelta(hours=3)
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        ("BUY", recent_buy_time, recent_buy_time.date())
    ]
    service.engine.connect.return_value.__enter__.return_value = mock_conn

    # Check routine SELL (e.g. capital_rotation or routine exit)
    result = service.check("NVDA", "SELL", strategy_name="capital_rotation")
    assert result is not None
    assert "24h Flip-Flop Lockout" in result
    assert "Blocked SELL" in result
    assert "opposite BUY" in result

def test_flip_flop_allows_emergency_stop_loss_after_recent_buy():
    """Emergency stop-loss SELL is exempt from 24h lockout."""
    service = TradingProtectionsService(user_id="test_user")
    service.engine = MagicMock()

    recent_buy_time = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        ("BUY", recent_buy_time, recent_buy_time.date())
    ]
    service.engine.connect.return_value.__enter__.return_value = mock_conn

    # Stop-loss must be permitted!
    result = service.check("NVDA", "SELL", strategy_name="stop_loss")
    assert result is None

    result_trailing = service.check("NVDA", "SELL", strategy_name="trailing_stop_loss")
    assert result_trailing is None

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
