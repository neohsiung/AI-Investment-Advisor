
import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
import requests
from src.agents.base_agent import BaseAgent
from src.services.market_data_service import MarketDataService
from src.repositories.settings_repository import ISettingsRepository
from src.repositories.agent_state_repository import IAgentStateRepository

# --- Base Agent Tests ---

class MockAgent(BaseAgent):
    def run(self, context):
        return "Test Run"

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock(spec=ISettingsRepository)
    repo.get_global.return_value = []
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
            # We mock _load_config implicitly by ensuring settings_repo returns something empty or valid,
            # BUT BaseAgent._load_config calls repo. If we want to mock what config ends up being,
            # we can patch _load_config OR populate mock_settings_repo.
            # Let's populate mock_settings_repo for better integration test
            mock_settings_repo.get_global.return_value = []
            
            # Using _load_config patch as in original to force specific config structure for testing
            with patch.object(BaseAgent, '_load_config', return_value={
                "provider": "Google Gemini", "model": "gemini-1.5-pro", "api_key": "test_key" # pragma: allowlist secret
            }):
                agent = MockAgent("TestAgent", "prompt.txt", 
                                  settings_repo=mock_settings_repo, state_repo=mock_state_repo)
                return agent

def test_base_agent_load_config_error(mock_settings_repo, mock_state_repo):
    # Simulate Repo Error
    mock_settings_repo.get_global.side_effect = Exception("DB Error")
    
    with patch('builtins.open', mock_open(read_data="System Prompt")):
        with patch('os.path.exists', return_value=True):
            with patch.dict(os.environ, {"AI_PROVIDER": "Google Gemini"}):
                # Should not raise, just log warning and return default
                agent = MockAgent("TestAgent", "prompt.txt",
                                  settings_repo=mock_settings_repo, state_repo=mock_state_repo)
                # Default fallback in BaseAgent is empty or checks os.environ
                # BaseAgent._load_config sets defaults if not in DB
                assert agent.config["provider"] == "Google Gemini" # Default

def test_base_agent_load_prompt_error(mock_settings_repo, mock_state_repo):
    with patch('os.path.exists', return_value=False):
        with pytest.raises(FileNotFoundError):
            MockAgent("TestAgent", "missing.txt", 
                      settings_repo=mock_settings_repo, state_repo=mock_state_repo)

def test_base_agent_real_llm_openrouter(mock_agent):
    mock_agent.config["provider"] = "OpenRouter"
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter Response"}}]
        }
        resp = mock_agent._call_real_llm("prompt", "system")
        assert resp == "OpenRouter Response"

def test_base_agent_real_llm_openai(mock_agent):
    mock_agent.config["provider"] = "OpenAI"
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "OpenAI Response"}}]
        }
        resp = mock_agent._call_real_llm("prompt", "system")
        assert resp == "OpenAI Response"

def test_base_agent_real_llm_error_handling(mock_agent):
    mock_agent.config["provider"] = "Google Gemini"
    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.RequestException("API Fail")
        with pytest.raises(requests.exceptions.RequestException):
            mock_agent._call_real_llm("prompt", "system")

def test_base_agent_mock_fallback(mock_agent):
    mock_agent.config['api_key'] = 'valid_key' # pragma: allowlist secret
    with patch.object(mock_agent, '_call_real_llm', side_effect=Exception("Major Fail")):
        # fallback to mock
        resp = mock_agent._mock_llm_call("prompt", "system")
        assert "Simulation Mode" in resp or "TestAgent" in resp

# --- Market Data Tests ---


