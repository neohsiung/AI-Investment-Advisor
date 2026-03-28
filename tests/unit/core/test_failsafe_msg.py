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
         patch('src.services.sentinel_service.SettingsService'), \
         patch('src.services.sentinel_service.MarketDataService'), \
         patch('src.services.sentinel_service.InternetSearchService'), \
         patch('src.services.sentinel_service.TransactionService'), \
         patch('src.agents.factory.AgentFactory.create_sentinel_agent'), \
         patch('httpx.AsyncClient.post', return_value=MagicMock(status_code=202)) as mock_post:
        
        # We need mock_sentinel_repo to return thresholds
        with patch('src.services.sentinel_service.AlchemySentinelRepository') as MockRepo:
            mock_repo_instance = MagicMock(spec=AlchemySentinelRepository)
            mock_repo_instance.engine = MagicMock()
            mock_repo_instance.get_all_thresholds.return_value = {"news_risk_score": 0.6}
            MockRepo.return_value = mock_repo_instance

            sentinel = SentinelService(
                council_service=mock_council,
                user_id="test_user"
            )

            # Trigger escalation
            triggers = [{"text": "⚠️ TEST TRIGGER", "id": "test_id"}]
            await sentinel._escalate(triggers)
            await sentinel._flush_buffer(force=True)

            # Check what was posted
            assert mock_post.called
            args, kwargs = mock_post.call_args
            payload = kwargs['json']
            content = payload['content']
            print("\n--- CAPTURED NOTIFICATION CONTENT ---")
            print(content)
            print("--- END ---")
            
            assert "安全模式" in content
            assert "目前無法取得" in content
