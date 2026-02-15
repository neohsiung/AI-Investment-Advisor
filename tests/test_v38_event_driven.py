import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.services.sentinel_service import SentinelService
from src.services.notification_service import NotificationService

@pytest.mark.asyncio
async def test_sentinel_process_event():
    # Setup mocks
    mock_notification = MagicMock(spec=NotificationService)
    mock_council = MagicMock()
    mock_council.start_session = asyncio.coroutine(lambda t, c, scope="single", market_volatility=0.0: {"consensus": "Hold steady."})
    
    sentinel = SentinelService(
        notification_service=mock_notification,
        council_service=mock_council
    )
    
    # Simulate an event
    event = {
        "source": "mktrecap",
        "data": {
            "ticker": "AAPL",
            "msg": "Price Spike: +10%",
            "type": "MARKET_SPIKE"
        }
    }
    
    # Process event
    await sentinel.process_event(event)
    
    # Verify notification was called (via notify_all)
    assert mock_notification.notify_all.called
    args, kwargs = mock_notification.notify_all.call_args
    assert "MKTRECAP ALERT" in kwargs["title"]
    assert "Price Spike: +10%" in kwargs["content"]

@pytest.mark.asyncio
async def test_sentinel_vix_logic():
    # Test internal VIX check (unit level)
    mock_market = MagicMock()
    mock_market.get_ohlcv.return_value = {"close": [20, 21, 20, 22, 21, 50]} # Extreme spike at the end
    
    sentinel = SentinelService(market_service=mock_market)
    triggers = sentinel._check_vix_anomaly()
    
    assert any("VIX Spike" in t for t in triggers)
