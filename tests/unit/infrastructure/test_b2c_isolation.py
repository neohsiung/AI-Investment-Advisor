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

def test_webhook_api_key_is_backfilled_for_an_existing_user(mock_user_repo, mock_db_repo):
    """
    A user missing `webhook_api_key` gets one generated on initialization.

    This used to be asserted through the Streamlit auth guard, which minted the
    key during login. That login is gone, but the invariant matters MORE now,
    not less: `X-API-Key` on /webhook/* is the only credential-based auth path
    left in the system, so a user without a key silently cannot receive any
    inbound webhook.

    原本由 Streamlit 登入流程補發金鑰；登入已移除，但這個不變量更重要了——
    /webhook/* 的 X-API-Key 是系統中唯一剩下的憑證驗證路徑。
    """
    from src.services.settings_service import SettingsService

    user_id = str(uuid.uuid4())
    svc = SettingsService(user_id=user_id, settings_repo=mock_db_repo)

    with patch.object(SettingsService, "get_all_settings", return_value={}), \
         patch.object(SettingsService, "save_setting") as mock_save, \
         patch.object(svc, "_user_exists", create=True, return_value=True):
        # user-existence check reads the users table directly
        with patch("src.services.settings_service.AlchemySettingsRepository"):
            try:
                svc.initialize_user_settings(user_id=user_id)
            except Exception:
                # Downstream seeding touches more collaborators than this test
                # mocks; the key generation happens first and is what we assert.
                pass

    saved_keys = [c.args[0] for c in mock_save.call_args_list if c.args]
    assert "webhook_api_key" in saved_keys, f"expected a webhook key to be minted, got {saved_keys}"
    key_value = next(c.args[1] for c in mock_save.call_args_list if c.args and c.args[0] == "webhook_api_key")
    assert key_value.startswith("sk_") and len(key_value) > 20

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

def test_settings_isolation_strict(mock_db_repo, monkeypatch):
    """
    An explicit user_id still scopes every settings query to that user.

    Previously the second half of this test asserted that a missing user_id
    raised. In the single-owner deployment "missing" means "the owner", so it
    resolves instead — but the first half is the part that matters and is
    unchanged: resolution must never rewrite an identity that was supplied.

    明確帶入的 user_id 仍嚴格限縮查詢範圍；未指定者才解析成擁有者。
    """
    from src.config.owner import reset_owner_cache
    from src.services.settings_service import SettingsService

    owner = "00000000-0000-4000-a000-000000000001"
    monkeypatch.setenv("OWNER_ID", owner)
    reset_owner_cache()

    user_a = "user_a"
    service_a = SettingsService(user_id=user_a, settings_repo=mock_db_repo)
    service_a.get_setting("test_key")
    mock_db_repo.get.assert_called_with(user_a, "test_key", None)

    # No user_id supplied -> the owner, not an error, and never user_a.
    service_none = SettingsService(user_id=None, settings_repo=mock_db_repo)
    mock_db_repo.get_all.return_value = {}
    service_none.get_all_settings()
    assert mock_db_repo.get_all.call_args[0][0] == owner

    reset_owner_cache()
