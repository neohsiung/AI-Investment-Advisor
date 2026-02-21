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
    with patch('src.services.sentinel_service.AlchemySentinelRepository') as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.is_duplicate_alert.return_value = False
        
        mock_settings = MagicMock(spec=SettingsService)
        mock_settings.user_id = "test_user_123"
        
        mock_council = MagicMock(spec=CouncilService)
        # Actionable decision to bypass Significance Filter
        mock_council.start_session = AsyncMock(return_value={"consensus": "Decision: SELL AAPL immediately."})
        
        sentinel = SentinelService(
            settings_service=mock_settings,
            council_service=mock_council
        )
        
        return {
            "sentinel": sentinel,
            "mock_repo": mock_repo,
            "mock_council": mock_council,
            "mock_settings": mock_settings
        }

@pytest.mark.anyio
async def test_alert_flow_and_format(sentinel_setup):
    sentinel = sentinel_setup["sentinel"]
    mock_council = sentinel_setup["mock_council"]
    
    triggers = [
        {"id": "vix_spike", "text": "🔴 VIX Spike: 45.0 > 30.0"},
        {"id": "rate_up", "text": "🏦 Fed Funds Rate Up"}
    ]
    
    # execution
    with patch('httpx.AsyncClient.post', return_value=MagicMock(status_code=202)) as mock_post:
        await sentinel._do_send_alert(triggers, source="TestSentinel")
    
        # Verify CouncilService called with user_id
        mock_council.start_session.assert_called_once()
        args, kwargs = mock_council.start_session.call_args
        assert kwargs['user_id'] == "test_user_123"
        
        # Verify Notification Format through HTTP
        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs['json']
        content = payload['content']
        
        # Verify content presence
        assert "### 🛡️ Sentinel 監控警報" in content
        assert "• 🔴 VIX Spike: 45.0 > 30.0" in content
        assert "• 🏦 Fed Funds Rate Up" in content
        assert "Decision: SELL AAPL immediately." in content
