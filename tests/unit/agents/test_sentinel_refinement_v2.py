import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from src.services.sentinel_service import SentinelService

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_escalate_deduplication():
    mock_repo = MagicMock()
    mock_repo.engine = MagicMock()
    mock_repo.get_all_thresholds.return_value = {}
    mock_repo.is_duplicate_alert.return_value = True
    
    mock_council = MagicMock()
    mock_council.start_session = AsyncMock(return_value={"consensus": "Stay Watchful"})
    
    mock_redis = MagicMock()
    mock_redis.all_pending = AsyncMock(return_value=[])
    mock_redis.add = AsyncMock()
    mock_redis.flush_all = AsyncMock(return_value=[{"text": "Test Trigger 1", "id": "t1", "priority": 2}])
    
    mock_settings = MagicMock()
    mock_settings.user_id = None

    with patch("src.services.sentinel_service.AlchemySentinelRepository", return_value=mock_repo), \
         patch("src.services.sentinel_service.AlchemySnapshotRepository", return_value=mock_repo), \
         patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=mock_redis), \
         patch("src.services.sentinel_service.MarketDataService") as mock_market_factory, \
         patch("src.agents.factory.AgentFactory.create_sentinel_agent") as mock_factory:
        
        mock_market = mock_market_factory.return_value
        mock_market.get_macro_data.return_value = {"market_indicators": {"^VIX": 20.0}}
        
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value='{"priority": 2, "target_agent": "CIO", "rationale": "Test"}')
        mock_factory.return_value = mock_agent
        
        service = SentinelService(user_id="test_user", council_service=mock_council, settings_service=mock_settings, repo=mock_repo, snapshot_repo=mock_repo)
        
        triggers = [{"text": "Test Trigger 1", "id": "t1"}]
        
        with patch('src.services.notification_service.NotificationService') as mock_noti_cls:
            mock_noti_instance = MagicMock()
            mock_noti_instance.notify_all = AsyncMock()
            mock_noti_cls.create_with_settings.return_value = mock_noti_instance

            await service._escalate(triggers, source="Test")
            await service._flush_buffer(force=True, source="Test")
            
            # Since is_duplicate_alert is True, it should not notify
            assert mock_council.start_session.call_count == 0
            assert mock_noti_instance.notify_all.called == False

@pytest.mark.anyio
async def test_escalate_new_alert():
    mock_repo = MagicMock()
    mock_repo.engine = MagicMock()
    mock_repo.get_all_thresholds.return_value = {}
    mock_repo.is_duplicate_alert.return_value = False
    
    mock_council = MagicMock()
    mock_council.start_session = AsyncMock(return_value={"consensus": "⚠️ Priority: BUY AAPL"})
    
    mock_redis = MagicMock()
    mock_redis.all_pending = AsyncMock(return_value=[])
    mock_redis.add = AsyncMock()
    mock_redis.flush_all = AsyncMock(return_value=[{"text": "New Trigger", "id": "new_t", "priority": 2}])
    
    mock_settings = MagicMock()
    mock_settings.user_id = None

    with patch("src.services.sentinel_service.AlchemySentinelRepository", return_value=mock_repo), \
         patch("src.services.sentinel_service.AlchemySnapshotRepository", return_value=mock_repo), \
         patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=mock_redis), \
         patch("src.services.sentinel_service.MarketDataService") as mock_market_factory, \
         patch("src.agents.factory.AgentFactory.create_sentinel_agent") as mock_factory:
        
        mock_market = mock_market_factory.return_value
        mock_market.get_macro_data.return_value = {"market_indicators": {"^VIX": 20.0}}
        
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value='{"priority": 2, "target_agent": "CIO", "rationale": "Test"}')
        mock_factory.return_value = mock_agent
        
        service = SentinelService(user_id="test_user", council_service=mock_council, settings_service=mock_settings, repo=mock_repo, snapshot_repo=mock_repo)
        
        triggers = [{"text": "New Trigger", "id": "new_t"}]
        
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        
        with patch('src.services.notification_service.NotificationService') as mock_noti_cls:
            mock_noti_instance = MagicMock()
            mock_noti_instance.notify_all = AsyncMock()
            mock_noti_cls.create_with_settings.return_value = mock_noti_instance

            await service._escalate(triggers, source="Test")
            await service._flush_buffer(force=True, source="Test")
            
            # Assert: Should notify and log
            assert mock_repo.log_alert.called
            assert mock_noti_instance.notify_all.called
