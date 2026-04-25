import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.sentinel_service import SentinelService
from src.repositories.sentinel_repository import AlchemySentinelRepository

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_sentinel_failsafe_message():
    # Setup mocks to trigger exception in start_session
    mock_council = MagicMock()
    mock_council.start_session = AsyncMock(side_effect=Exception("LLM Timeout"))
    
    with patch('src.services.sentinel_service.AlchemySentinelRepository'), \
         patch('src.services.sentinel_service.SentinelService._calibrate_thresholds'), \
         patch('src.services.sentinel_service.SettingsService') as MockSettings, \
         patch('src.services.sentinel_service.MarketDataService'), \
         patch('src.services.sentinel_service.InternetSearchService'), \
         patch('src.services.sentinel_service.TransactionService'), \
         patch('src.agents.factory.AgentFactory.create_sentinel_agent'), \
         patch('src.services.notification_service.NotificationService') as MockNotificationService, \
         patch('httpx.AsyncClient.post', return_value=MagicMock(status_code=202)) as mock_post:
        
        mock_settings_instance = MockSettings.return_value
        mock_settings_instance.user_id = "test_user"
        mock_settings_instance.get_all_settings.return_value = {}
        
        # Setup NotificationService mock
        mock_notification_svc = AsyncMock()
        MockNotificationService.create_with_settings.return_value = mock_notification_svc

        
        # We need mock_sentinel_repo to return thresholds
        with patch('src.services.sentinel_service.AlchemySentinelRepository') as MockRepo:
            mock_repo_instance = MagicMock(spec=AlchemySentinelRepository)
            mock_repo_instance.engine = MagicMock()
            mock_repo_instance.get_all_thresholds.return_value = {"news_risk_score": 0.6}
            mock_repo_instance.is_duplicate_alert.return_value = False
            MockRepo.return_value = mock_repo_instance

            sentinel = SentinelService(
                council_service=mock_council,
                user_id="test_user"
            )

            # Mock _redis_buffer so Redis connection failures don't break tests
            _buffer_store = []
            mock_redis_buffer = MagicMock()
            async def _mock_add(uid, t, w): _buffer_store.append(t); return True
            async def _mock_all_pending(uid): return list(_buffer_store)
            async def _mock_flush_due(uid): due = list(_buffer_store); _buffer_store.clear(); return due
            mock_redis_buffer.add = _mock_add
            mock_redis_buffer.all_pending = _mock_all_pending
            mock_redis_buffer.flush_due = _mock_flush_due
            sentinel._redis_buffer = mock_redis_buffer

            # Trigger escalation
            triggers = [{"text": "⚠️ TEST TRIGGER", "id": "test_id"}]
            await sentinel._escalate(triggers)
            await sentinel._flush_buffer(force=True)

            # Check what was notified
            assert mock_notification_svc.notify_all.called
            args, kwargs = mock_notification_svc.notify_all.call_args
            content = kwargs['content']
            print("\n--- CAPTURED NOTIFICATION CONTENT ---")
            print(content)
            print("--- END ---")
            
            assert "安全模式" in content
            assert "目前無法取得" in content

