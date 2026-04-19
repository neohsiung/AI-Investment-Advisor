import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import uuid
from src.services.llm_onboarding_service import LLMOnboardingService

@pytest.fixture
def mock_db():
    with patch("src.services.llm_onboarding_service.get_db_connection") as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_session
        yield mock_session

@pytest.fixture
def onboarding_service():
    with patch("src.services.llm_onboarding_service.load_yaml") as mock_load:
        # Mock some default YAML content
        mock_load.side_effect = [
            {"providers": [{"provider_code": "openai", "display_name": "OpenAI"}]},
            {"models": [{"provider_code": "openai", "model_code": "gpt-4", "display_name": "GPT-4"}]}
        ]
        service = LLMOnboardingService()
        yield service, mock_load

def test_onboarding_init(onboarding_service):
    service, mock_load = onboarding_service
    assert service.providers_yaml[0]["provider_code"] == "openai"
    assert service.models_yaml[0]["model_code"] == "gpt-4"

def test_seed_defaults_for_user_missing_configs(mock_db):
    with patch("src.services.llm_onboarding_service.load_yaml", return_value={}):
        service = LLMOnboardingService()
        service.seed_defaults_for_user("user-123")
        # Should return early without hitting DB
        mock_db.query.assert_not_called()

def test_seed_defaults_for_user_success(mock_db, onboarding_service):
    service, _ = onboarding_service
    user_id = str(uuid.uuid4())
    
    # Mock existing checks to return None
    mock_db.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    service.seed_defaults_for_user(user_id)
    
    # Verify provider seeding
    assert mock_db.add.called
    mock_db.commit.assert_called_once()

# @pytest.mark.asyncio
# async def test_async_seed_defaults_for_user_success(onboarding_service):
#     service, _ = onboarding_service
#     user_id = str(uuid.uuid4())
#     
#     mock_session = AsyncMock()
#     mock_result = MagicMock()
#     # Explicitly return None to bypass existing checks
#     mock_result.scalar_one_or_none.side_effect = lambda: None
#     mock_session.execute.return_value = mock_result
#     
#     with patch("src.services.llm_onboarding_service.get_async_db_engine", create=True), \
#          patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=mock_session):
#         await service.async_seed_defaults_for_user(user_id)
#         
#     mock_session.commit.assert_awaited_once()
