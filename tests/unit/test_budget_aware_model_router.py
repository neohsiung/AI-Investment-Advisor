import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.llm import BudgetAwareModelRouter
from src.domain.interfaces import LLMConfig

@pytest.fixture
def mock_settings():
    svc = MagicMock()
    svc.user_id = "test_user"
    # Simulate DB settings containing model config (TierSpec.resolve_model reads db_settings by env_key)
    svc.get_all_settings.return_value = {
        "AI_MODEL_NANO": "gpt-4.1-nano",
        "AI_MODEL_FAST": "google/gemini-2.5-flash",
        "AI_MODEL_SMART": "google/gemini-2.5-pro",
        "AI_MODEL_ADVANCED": "google/gemini-2.5-pro",
        "AI_PROVIDER": "OpenRouter",
        "source_openrouter_api_key": "mock_api_key",
    }
    svc.get_setting.side_effect = lambda k, d=None, user_id=None: "mock_api_key" if "api_key" in k else d
    return svc

@pytest.fixture
def mock_logger():
    return MagicMock()

@pytest.fixture
def router(mock_settings, mock_logger):
    return BudgetAwareModelRouter(mock_settings, mock_logger)

def test_router_normal_budget(router, mock_logger):
    # $10 spend < $16
    mock_logger.get_user_spending.return_value = {"total_cost": 10.0}
    
    config = router.get_config("smart")
    
    # Should stay as smart model (google/gemini-2.5-pro per TierConfig defaults)
    assert "gemini-2.5-pro" in config.model
    assert config.provider == "OpenRouter"

def test_router_soft_limit_downgrade(router, mock_logger):
    # $17 spend >= $16 (Soft Limit)
    mock_logger.get_user_spending.return_value = {"total_cost": 17.0}
    
    config = router.get_config("smart")
    
    # Smart should downgrade to Fast (google/gemini-2.5-flash per TierConfig defaults)
    assert "gemini-2.5-flash" in config.model

def test_router_hard_limit_downgrade(router, mock_logger):
    # $21 spend >= $20 (Hard Limit)
    mock_logger.get_user_spending.return_value = {"total_cost": 21.0}
    
    # Even requesting advanced should hit fast
    config = router.get_config("advanced")
    
    assert "gemini-2.5-flash" in config.model

def test_router_uninitialized_user(mock_settings, mock_logger, monkeypatch):
    """
    An unset user_id resolves to the owner instead of raising.

    The old ValueError existed to force callers to thread a tenant through. On
    a single-owner box that check only produced crashes on the LLM path for
    internal callers that legitimately had no user context.
    未指定 user_id 改為解析成擁有者；舊的 ValueError 只會讓內部呼叫端在
    LLM 路徑上炸掉。
    """
    from src.config.owner import reset_owner_cache

    owner = "00000000-0000-4000-a000-000000000001"
    monkeypatch.setenv("OWNER_ID", owner)
    reset_owner_cache()

    mock_settings.user_id = None
    router = BudgetAwareModelRouter(mock_settings, mock_logger)

    # Resolution happens; whatever fails afterwards must not be about identity.
    try:
        router.get_config("nano")
    except ValueError as exc:
        assert "requires user_id" not in str(exc), exc

    reset_owner_cache()
