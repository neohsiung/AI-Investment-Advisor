
import pytest
from unittest.mock import MagicMock, patch
import os
from src.agents.base_agent import BaseAgent

# Mock Concrete Implementation of Abstract BaseAgent
class ConcreteAgent(BaseAgent):
    async def run(self, context, mode=None):
        return "ok"

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock()
    repo.get_all.return_value = []
    return repo

def test_config_priority_db_over_env(mock_settings_repo):
    """
    DB-only: _load_config reads from llm_tier_bindings (via build_config_chain).
    The conftest autouse fixture provides a mock candidate with provider='mock',
    model='mock-model'. Verify the config is built from that candidate.
    """
    with patch.object(BaseAgent, '_load_prompt', return_value="System Prompt"):
        agent = ConcreteAgent(name="TestAgent", prompt_path="dummy",
                              user_id="test_user", settings_repo=mock_settings_repo)

    # Config comes from the conftest autouse mock candidate
    assert agent.config["provider"] == "mock"
    assert agent.config["model"] == "mock-model"

def test_config_fallback_to_env(mock_settings_repo):
    """
    DB-only: there is no env fallback. The conftest autouse fixture ensures
    build_config_chain returns a mock candidate, so agent can always initialize.
    """
    mock_settings_repo.get_all.return_value = []

    with patch.object(BaseAgent, '_load_prompt', return_value="System Prompt"):
        agent = ConcreteAgent(name="TestAgent", prompt_path="dummy",
                              user_id="test_user", settings_repo=mock_settings_repo)

    # DB-only: env vars are not used; config comes from the mock candidate
    assert "provider" in agent.config
    assert "model" in agent.config

def test_user_specific_override(mock_settings_repo):
    """
    DB-only: user-specific config comes from llm_tier_bindings, not settings_repo.
    The conftest autouse fixture provides a mock candidate for all users/tiers.
    """
    with patch.object(BaseAgent, '_load_prompt', return_value="System Prompt"):
        agent = ConcreteAgent(name="TestAgent", prompt_path="dummy",
                              user_id="test_user", settings_repo=mock_settings_repo)

    # Config is from the mock candidate, not the legacy settings path
    assert agent.config["provider"] == "mock"
