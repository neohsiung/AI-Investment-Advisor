import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.sentinel_service import SentinelService
from src.services.council_service import CouncilService
from src.services.settings_service import SettingsService
from src.services.notification_service import NotificationService

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def sentinel_setup():
    with patch('src.services.sentinel_service.AlchemySentinelRepository') as mock_repo_cls, \
         patch('src.services.sentinel_service.SentinelService._calibrate_thresholds'), \
         patch('src.services.fred_service.FredService'), \
         patch('src.services.supply_chain_service.SupplyChainService'), \
         patch('src.agents.factory.AgentFactory', autospec=True) as MockFactory:
 
        mock_repo = mock_repo_cls.return_value
        mock_repo.is_duplicate_alert.return_value = False
        


        # Configure SentinelAgent mock too just in case
        mock_sentinel_agent = MagicMock()
        mock_sentinel_agent.run = AsyncMock(return_value={"priority": "P1", "target_agent": "CIO"})
        MockFactory.create_sentinel_agent.return_value = mock_sentinel_agent

        mock_settings = MagicMock(spec=SettingsService)
        mock_settings.user_id = "test_user_123"
        mock_settings.settings_repo = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        
        mock_council = MagicMock(spec=CouncilService)
        # Actionable decision to bypass Significance Filter
        mock_council.start_session = AsyncMock(return_value={"consensus": "Decision: SELL AAPL immediately."})
        
        sentinel = SentinelService(
            user_id="test_user_123",
            settings_service=mock_settings,
            council_service=mock_council
        )

        
        yield {
            "sentinel": sentinel,
            "mock_repo": mock_repo,
            "mock_council": mock_council,
            "mock_settings": mock_settings
        }


@pytest.mark.anyio
async def test_alert_flow_and_format(sentinel_setup):
    sentinel = sentinel_setup["sentinel"]
    sentinel.current_vix = 40.0
    mock_council = sentinel_setup["mock_council"]
    
    triggers = [
        {"id": "vix_spike", "text": "🔴 VIX Spike: 45.0 > 30.0"},
        {"id": "rate_up", "text": "🏦 Fed Funds Rate Up"}
    ]
    
    # execution
    # Verify notify_all is used (v7.0 consolidation)
    with patch("src.services.notification_settings_manager.NotificationSettingsManager.get_active_notification_channels") as mock_channels, \
         patch('src.services.notification_service.NotificationService.notify_all', new_callable=AsyncMock) as mock_notify:
        
        mock_channels.return_value = ["web"]
        await sentinel._do_send_alert(triggers, source="TestSentinel")
    
        # Verify CouncilService called with user_id
        mock_council.start_session.assert_called_once()
        args, kwargs = mock_council.start_session.call_args
        assert kwargs['user_id'] == "test_user_123"
        
        # Verify Notification Format
        assert mock_notify.called
        call_kwargs = mock_notify.call_args.kwargs
        
        # v4.2.2: Verify user_id is the internal user_id from settings_service
        assert call_kwargs['user_id'] == "test_user_123", (
            f"Expected internal user_id 'test_user_123', got '{call_kwargs['user_id']}'"
        )
        
        content = call_kwargs['content']
        # Verify content presence
        assert "TESTSENTINEL" in content
        assert "🔴 VIX Spike: 45.0 > 30.0" in content
        assert "🏦 Fed Funds Rate Up" in content
        assert "Decision: SELL AAPL immediately." in content
