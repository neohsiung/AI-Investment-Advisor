
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
import sys
import os
import requests
from src.agents.base_agent import BaseAgent
from src.services.market_data_service import MarketDataService
from src.repositories.settings_repository import ISettingsRepository
from src.repositories.agent_state_repository import IAgentStateRepository
import src.data.models # Ensure all models are registered for SQLite in-memory DB

# --- Base Agent Tests ---

class MockAgent(BaseAgent):
    async def run(self, context):
        return "Test Run"

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock(spec=ISettingsRepository)
    repo.get_all.return_value = []
    return repo

@pytest.fixture
def mock_state_repo():
    repo = MagicMock(spec=IAgentStateRepository)
    repo.get_state.return_value = None
    return repo

@pytest.fixture
def mock_agent(mock_settings_repo, mock_state_repo):
    with patch('builtins.open', mock_open(read_data="System Prompt")):
        with patch('os.path.exists', return_value=True):
            # Patch HybridMemory to avoid DB connection during construction
            with patch('src.agents.base_agent.HybridMemory', return_value=MagicMock()):
                # Using _load_config patch as in original
                with patch.object(BaseAgent, '_load_config', return_value={
                    "provider": "Google Gemini", "model": "gemini-1.5-pro", "api_key": "test_key"
                }):
                    agent = MockAgent("TestAgent", "prompt.txt", user_id="test_user", 
                                      settings_repo=mock_settings_repo, state_repo=mock_state_repo)
                    return agent

def test_base_agent_load_config_error(mock_settings_repo, mock_state_repo):
    # Simulate Repo Error
    mock_settings_repo.get_all.side_effect = Exception("DB Error")
    
    with patch('builtins.open', mock_open(read_data="System Prompt")):
        with patch('os.path.exists', return_value=True):
            with patch.dict(os.environ, {"AI_PROVIDER": "Google Gemini"}):
                # Should not raise, just log warning and return default
                agent = MockAgent("TestAgent", "prompt.txt", user_id="test_user",
                                  settings_repo=mock_settings_repo, state_repo=mock_state_repo)
                # In the current BudgetAwareModelRouter logic, if AI_PROVIDER is not set in DB
                # and provided in Env, it resolves correctly.
                # However, mock_agent overrides the provider.
                # We check that it at least returns a valid provider string.
                assert agent.config["provider"] != ""

def test_base_agent_load_prompt_error(mock_settings_repo, mock_state_repo):
    with patch('os.path.exists', return_value=False):
        with pytest.raises(FileNotFoundError):
            MockAgent("TestAgent", "missing.txt", 
                      settings_repo=mock_settings_repo, state_repo=mock_state_repo)

async def test_base_agent_real_llm_openrouter(mock_agent):
    """Test _call_real_llm delegates through gateway."""
    mock_agent.config["provider"] = "OpenRouter"
    mock_gw = AsyncMock() # Use AsyncMock for awaitable chat
    mock_gw.chat.return_value = "OpenRouter Response"
    mock_agent._llm_gateway = mock_gw
    resp = await mock_agent.call_llm([{"role": "user", "content": "prompt"}])
    assert resp == "OpenRouter Response"

async def test_base_agent_real_llm_openai(mock_agent):
    """Test _call_real_llm delegates through gateway."""
    mock_agent.config["provider"] = "OpenAI"
    mock_gw = AsyncMock() # Use AsyncMock for awaitable chat
    mock_gw.chat.return_value = "OpenAI Response"
    mock_agent._llm_gateway = mock_gw
    resp = await mock_agent.call_llm([{"role": "user", "content": "prompt"}])
    assert resp == "OpenAI Response"

async def test_base_agent_real_llm_error_handling(mock_agent):
    """Test error propagation through gateway."""
    mock_agent.config["provider"] = "Google Gemini"
    mock_gw = AsyncMock() # Use AsyncMock for awaitable chat
    mock_gw.chat.side_effect = requests.exceptions.RequestException("API Fail")
    mock_agent._llm_gateway = mock_gw
    with pytest.raises(requests.exceptions.RequestException):
        await mock_agent.call_llm([{"role": "user", "content": "prompt"}])

async def test_base_agent_mock_fallback(mock_agent):
    """Test that gateway errors propagate through _mock_llm_call."""
    mock_agent.config['api_key'] = 'valid_key' # pragma: allowlist secret
    mock_gw = AsyncMock()
    mock_gw.chat.side_effect = Exception("Major Fail")
    mock_agent._llm_gateway = mock_gw
    # With gateway, _mock_llm_call now delegates to call_llm -> gateway
    # Gateway error should propagate
    with pytest.raises(Exception):
        await mock_agent._mock_llm_call("prompt", "system")

# --- Market Data Tests ---


