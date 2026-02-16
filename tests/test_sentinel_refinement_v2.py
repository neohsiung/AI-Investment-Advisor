import pytest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.services.sentinel_service import SentinelService
from src.services.notification_service import NotificationService
from src.data.sentinel_repository import SentinelRepository

@pytest.fixture
def run_async():
    def _run(coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    return _run

@pytest.fixture
def mock_repo():
    return MagicMock(spec=SentinelRepository)

@pytest.fixture
def mock_council():
    c = MagicMock()
    c.start_session = MagicMock()
    c.start_session.side_effect = None # Reset side effect if any
    
    # We need start_session to be an async mock or return a future if called with await
    async def _async_start(*args, **kwargs):
        return {"consensus": "Stay Watchful"}
    
    c.start_session.side_effect = _async_start
    return c

@pytest.fixture
def mock_notifier():
    return MagicMock(spec=NotificationService)

@pytest.fixture
def sentinel_service(mock_repo, mock_council, mock_notifier):
    # Patch the internal repo creation
    with patch("src.services.sentinel_service.SentinelRepository", return_value=mock_repo):
        service = SentinelService(
            council_service=mock_council,
            notification_service=mock_notifier,
            settings_service=MagicMock()
        )
        # Force inject the mock repo if the init created a new one
        service.repo = mock_repo
        return service

def test_escalate_deduplication(sentinel_service, mock_repo, mock_notifier, run_async):
    # Setup: Repo says it IS a duplicate
    mock_repo.is_duplicate_alert.return_value = True
    
    async def _test():
        triggers = ["Test Trigger 1", "Test Trigger 2"]
        await sentinel_service._escalate(triggers, source="Test")
        
        # Assert: Should NOT notify or deliberate
        # mock_council.start_session is an AsyncMock/function, verify call
        assert not sentinel_service.council_service.start_session.called or sentinel_service.council_service.start_session.call_count == 0
        
        mock_notifier.notify_all.assert_not_called()
        # Should check duplication
        mock_repo.is_duplicate_alert.assert_called_once()
        # Should NOT log new alert
        mock_repo.log_alert.assert_not_called()

    run_async(_test())

def test_escalate_new_alert(sentinel_service, mock_repo, mock_notifier, run_async):
    # Setup: Repo says it is NOT a duplicate
    mock_repo.is_duplicate_alert.return_value = False
    
    async def _test():
        triggers = ["New Trigger"]
        await sentinel_service._escalate(triggers, source="Test")
        
        # Assert: Should notify and log
        # Verify await call happens
        assert sentinel_service.council_service.start_session.called
        
        mock_notifier.notify_all.assert_called_once()
        mock_repo.log_alert.assert_called_once()
        
        # Check arguments
        args, _ = mock_repo.log_alert.call_args
        assert args[0] == "TEST ALERT: New Trigger"
        assert "New Trigger" in args[1] # Content signature

    run_async(_test())

def test_notification_service_omni_channel_init():
    # Mock ChannelFactory to return specific adapters
    mock_adapters = [MagicMock(), MagicMock()] 
    
    with patch("src.infrastructure.channels.channel_factory.ChannelFactory.create_adapters", return_value=mock_adapters) as mock_factory, \
         patch("src.services.settings_service.SettingsService") as MockSettings:
        
        # Mock settings
        mock_settings_instance = MockSettings.return_value
        mock_settings_instance.get_all_settings.return_value = {"some": "settings"}
        
        service = NotificationService()
        
        # Factory should be called with settings
        mock_factory.assert_called_with({"some": "settings"})
        
        # Adapters should be Factory + Email + Web (+ potentially LINE fallback)
        # We expect at least len(mock_adapters) + 2 (Email/Web)
        # Note: In test env, LINE fallback might trigger if ENV var is set, but let's assume standard flow
        assert len(service.adapters) >= 4
        assert service.adapters[0] == mock_adapters[0]
        
        # Verify EmailAdapter and WebAdapter are appended
        class_names = [a.__class__.__name__ for a in service.adapters]
        assert "EmailAdapter" in class_names
        assert "WebAdapter" in class_names
