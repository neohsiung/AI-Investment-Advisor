import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from src.services.sentinel_service import SentinelService
from src.services.notification_service import NotificationService
from src.repositories.sentinel_repository import AlchemySentinelRepository

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def mock_repo():
    repo = MagicMock(spec=AlchemySentinelRepository)
    repo.get_all_thresholds.return_value = {}
    repo.is_duplicate_alert.return_value = False
    return repo

@pytest.fixture
def mock_council():
    c = MagicMock()
    c.start_session = AsyncMock(return_value={"consensus": "Stay Watchful"})
    return c

@pytest.fixture
def mock_notifier():
    n = MagicMock(spec=NotificationService)
    n.notify_all = AsyncMock(return_value={})
    return n

@pytest.fixture
def sentinel_service(mock_repo, mock_council, mock_notifier):
    # Patch the internal repo creation
    with patch("src.services.sentinel_service.AlchemySentinelRepository", return_value=mock_repo):
        service = SentinelService(
            council_service=mock_council,
            notification_service=mock_notifier,
            settings_service=MagicMock()
        )
        # Force inject the mock repo if the init created a new one
        service.repo = mock_repo
        return service

@pytest.mark.anyio
async def test_escalate_deduplication(sentinel_service, mock_repo, mock_notifier):
    # Setup: Repo says it IS a duplicate
    mock_repo.is_duplicate_alert.return_value = True
    
    # We need to use dict triggers
    triggers = [{"text": "Test Trigger 1", "id": "t1"}, {"text": "Test Trigger 2", "id": "t2"}]
    
    # source="Test" makes it "external" which triggers immediate flush
    await sentinel_service._escalate(triggers, source="Test")
    
    # Assert: Should NOT notify or deliberate
    assert sentinel_service.council_service.start_session.call_count == 0
    mock_notifier.notify_all.assert_not_called()
    
    # Should check duplication
    assert mock_repo.is_duplicate_alert.called

@pytest.mark.anyio
async def test_escalate_new_alert(sentinel_service, mock_repo, mock_notifier):
    # Setup: Repo says it is NOT a duplicate
    mock_repo.is_duplicate_alert.return_value = False
    
    triggers = [{"text": "New Trigger", "id": "new_t"}]
    await sentinel_service._escalate(triggers, source="Test")
    
    # Assert: Should notify and log
    mock_notifier.notify_all.assert_called_once()
    assert mock_repo.log_alert.called
    
    # Check arguments
    args, _ = mock_repo.log_alert.call_args
    # topic = f"{source.upper()} ALERT: {'; '.join(display_texts)}"
    assert args[0] == "TEST ALERT: New Trigger"
    assert args[1] == "New Trigger"

def test_notification_service_omni_channel_init():
    # Mock ChannelFactory to return specific adapters
    mock_adapters = [MagicMock(), MagicMock()] 
    
    with patch("src.infrastructure.channels.channel_factory.ChannelFactory.create_adapters", return_value=mock_adapters) as mock_factory, \
         patch("src.services.settings_service.SettingsService") as MockSettings, \
         patch("src.services.notification_filters.InterestBasedFilter") as MockFilter:
        
        # Mock settings
        mock_settings_instance = MockSettings.return_value
        mock_settings_instance.get_all_settings.return_value = {"some": "settings"}
        
        # Test create_with_settings instead of direct init if we want to test factory integration
        service = NotificationService.create_with_settings(mock_settings_instance)
        
        # Factory should be called with settings
        mock_factory.assert_called_with({"some": "settings"})
        
        # Service should have the adapters
        assert len(service.adapters) == len(mock_adapters)
        assert service.adapters == mock_adapters
