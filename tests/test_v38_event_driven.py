import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.services.sentinel_service import SentinelService
from src.services.notification_service import NotificationService

def test_sentinel_process_event():
    async def run_test():
        # Setup mocks
        mock_notification = MagicMock(spec=NotificationService)
        mock_council = MagicMock()
        
        async def mock_start_session(*args, **kwargs):
            return {"consensus": "Hold steady."}
        mock_council.start_session = mock_start_session
        
        # Mock Repository to avoid DB connection
        with patch('src.services.sentinel_service.SentinelRepository') as MockRepo:
            mock_repo_instance = MagicMock()
            MockRepo.return_value = mock_repo_instance
            mock_repo_instance.get_all_thresholds.return_value = {
                "vix_high": 25.0,
                "vix_extreme": 40.0,
                "position_drop_pct": -5.0,
                "position_spike_pct": 8.0,
                "news_risk_score": 0.6
            }

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

    asyncio.run(run_test())

def test_sentinel_vix_logic():
    async def run_test():
        # Test internal VIX check (unit level)
        mock_market = MagicMock()
        # Need > 30 points for Z-Score window
        closes = [20.0] * 30 + [50.0] # 30 stable days + 1 spike
        mock_market.get_ohlcv.return_value = {"close": closes}
        
        with patch('src.services.sentinel_service.SentinelRepository') as MockRepo:
            mock_repo_instance = MagicMock()
            MockRepo.return_value = mock_repo_instance
            mock_repo_instance.get_all_thresholds.return_value = {
                 "vix_high": 25.0,
                 "vix_extreme": 40.0
            }
            
            sentinel = SentinelService(market_service=mock_market)
            triggers = sentinel._check_vix_anomaly()
            
            assert any("VIX Spike" in t for t in triggers)

    asyncio.run(run_test())
