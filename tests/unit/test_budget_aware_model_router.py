import pytest
from unittest.mock import MagicMock
from src.infrastructure.llm import BudgetAwareModelRouter
from src.domain.interfaces import LLMConfig

@pytest.fixture(autouse=True)
def env_reset(monkeypatch):
    """Ensure environment variables don't pollute TierSpec resolution."""
    for key in ["AI_MODEL_NANO", "AI_MODEL_FAST", "AI_MODEL_SMART", "AI_MODEL_ADVANCED"]:
        monkeypatch.delenv(key, raising=False)
    yield

@pytest.fixture
def mock_settings():
    svc = MagicMock()
    svc.user_id = "test_user"
    svc.get_all_settings.return_value = {}
    # Simulate standard provider/key retrieval
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

def test_router_uninitialized_user(mock_settings, mock_logger):
    mock_settings.user_id = None
    router = BudgetAwareModelRouter(mock_settings, mock_logger)
    
    # Should not crash, just return build_config with uninitialized defaults
    config = router.get_config("nano")
    assert "gpt-4.1-nano" in config.model
