import pytest
import uuid
import sys
from unittest.mock import MagicMock, patch, ANY, AsyncMock

# v4.3.1: Moved global mocks to prevent environment poisoning
# Instead of global sys.modules modification, we use it within the test or fixture as needed.
@pytest.fixture(autouse=True, scope="module")
def mock_heavy_dependencies():
    with patch.dict("sys.modules", {
        "src.services.sentinel_service": MagicMock(),
        "src.services.council_service": MagicMock(),
        "src.agents.factory": MagicMock(),
        "dspy": MagicMock()
    }):
        yield

# Removed top-level imports to allow mock_heavy_dependencies fixture to work correctly during test execution

@pytest.fixture
def mock_db_repo():
    # Patch AlchemySettingsRepository in both the repo module and the service modules where it's used
    with patch("src.repositories.settings_repository.AlchemySettingsRepository") as mock_repo_class:
        instance = mock_repo_class.return_value
        instance.find_user_by_webhook_secret = MagicMock()
        instance.get = MagicMock()
        instance.set = MagicMock()
        instance.get_all = MagicMock(return_value=[])
        
        # Also patch it where SettingsService might have imported it
        with patch("src.services.settings_service.AlchemySettingsRepository", mock_repo_class):
            yield instance

@pytest.fixture
def mock_user_repo():
    with patch("src.repositories.user_repository.AlchemyUserRepository") as mock:
        yield mock.return_value

def test_auth_guard_lazy_key_generation(mock_user_repo, mock_db_repo):
    """測試 AuthGuard 是否為現有使用者自動補全金鑰 (Transition Support)"""
    user_id = str(uuid.uuid4())
    mock_user_data = {"email": "test@example.com", "id": user_id}
    
    # Mock auth_manager directly in the module
    with patch("src.utils.auth_guard.auth_manager") as mock_auth:
        mock_auth.get_status.return_value = "AUTHENTICATED"
        mock_auth.get_current_user.return_value = mock_user_data
        
        # Simulate existing user found in DB
        mock_user_repo.get_by_identity.return_value = {"id": user_id, "email": "test@example.com"}
        
        # Mock SettingsService inside require_authentication
        with patch("src.services.settings_service.SettingsService") as MockSvc:
            svc_inst = MockSvc.return_value
            svc_inst.get_setting.return_value = None
            
            # import streamlit as st mock is needed since AuthGuard uses it
            from src.utils.auth_guard import require_authentication
            with patch("src.utils.auth_guard.st"):
                updated_user = require_authentication()
            
            assert updated_user["id"] == user_id
            # Ensure save_setting was called to save the new key
            svc_inst.save_setting.assert_called_with("webhook_api_key", ANY)

@pytest.mark.asyncio
async def test_webhook_dynamic_routing(mock_db_repo):
    """測試 Webhook 是否能根據 API Key 動態路由至正確使用者"""
    api_key = "sk_test_12345"
    user_id = "user_uuid_abc"
    
    # Setup mock_db_repo for the lookup
    mock_db_repo.find_user_by_webhook_secret.return_value = user_id
    
    # Mock request with AsyncMock for .json()
    mock_request = MagicMock()
    mock_request.headers = {"X-API-Key": api_key}
    mock_request.json = AsyncMock(return_value={"event": "test"})
    
    from src.services.webhook_service import WebhookService
    svc = WebhookService()
    
    # Patch EventAnalysisWorkflow where it is imported FROM (workflow_service)
    # Since handle_generic_webhook does 'from src.services.workflow_service import ...'
    with patch("src.services.workflow_service.EventAnalysisWorkflow") as MockWorkflow:
        workflow_inst = MockWorkflow.return_value
        # Ensure run returns a real coroutine
        async def mock_run(*args, **kwargs): return "COMPLETED"
        workflow_inst.run.side_effect = mock_run
        
        response = await svc.handle_generic_webhook("test_source", mock_request)
        
    assert response["status"] == "accepted"
    assert response["user_id"] == user_id
    
    # Verify Workflow was instantiated with correct user_id
    MockWorkflow.assert_called_with(
        user_id=user_id,
        event_source="test_source",
        event_data=ANY
    )

def test_settings_isolation_strict(mock_db_repo):
    """測試 SettingsService 是否嚴格執行隔離，移除 system 回退"""
    from src.services.settings_service import SettingsService
    user_a = "user_a"
    service_a = SettingsService(user_id=user_a, settings_repo=mock_db_repo)
    
    service_a.get_setting("test_key")
    mock_db_repo.get.assert_called_with(user_a, "test_key", None)
    
    # Ensure it raises error if no user_id is provided
    from src.services.settings_service import SettingsService
    service_none = SettingsService(user_id=None, settings_repo=mock_db_repo)
    with pytest.raises(ValueError, match="No user_id provided"):
        service_none.get_all_settings()
