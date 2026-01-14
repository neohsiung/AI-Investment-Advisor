import pytest
from unittest.mock import MagicMock, patch
import os
from src.agents.factory import AgentFactory
from src.agents.base_agent import BaseAgent

@pytest.fixture
def mock_dspy():
    with patch("src.agents.factory.dspy") as mock:
        mock.OpenAI = MagicMock()  # Ensure OpenAI attribute exists
        yield mock

@pytest.fixture
def enable_has_dspy():
    with patch("src.agents.factory.has_dspy", True):
        yield

def test_configure_dspy_with_env(mock_dspy, enable_has_dspy):
    with patch.dict(os.environ, {"LLM_API_KEY": "test_key", "LLM_MODEL_SMART": "test_model"}):
        # Reset state
        AgentFactory._dspy_configured = False
        AgentFactory._configure_dspy()
        
        # Since has_dspy is mocked to True and we have an api_key, configure should be called
        mock_dspy.settings.configure.assert_called()
        assert AgentFactory._dspy_configured is True

def test_configure_dspy_without_env(mock_dspy, enable_has_dspy):
    with patch.dict(os.environ, {}, clear=True):
        # Also mock the settings repo to return empty
        with patch("src.agents.factory.SqliteSettingsRepository") as MockRepo:
            MockRepo.return_value.get_global.return_value = []
            AgentFactory._dspy_configured = False
            AgentFactory._configure_dspy()
            
            # No API key available, so configure should NOT be called
            mock_dspy.settings.configure.assert_not_called()

def test_configure_dspy_no_dspy_module():
    with patch("src.agents.factory.has_dspy", False):
        AgentFactory._dspy_configured = False
        AgentFactory._configure_dspy()
        # Should just return without error
        assert AgentFactory._dspy_configured is True

def test_create_momentum_agent():
    with patch("src.agents.factory.MomentumAgent") as mock_agent:
        agent = AgentFactory.create_agent("Momentum")
        assert agent == mock_agent.return_value

def test_create_fundamental_agent():
    with patch("src.agents.factory.FundamentalAgent") as mock_agent:
        agent = AgentFactory.create_agent("Fundamental")
        assert agent == mock_agent.return_value

def test_create_macro_agent():
    with patch("src.agents.factory.MacroAgent") as mock_agent:
        agent = AgentFactory.create_agent("Macro")
        assert agent == mock_agent.return_value

def test_create_cio_agent():
    with patch("src.agents.factory.CIOAgent") as mock_agent:
        agent = AgentFactory.create_agent("CIO", mode="daily")
        assert agent == mock_agent.return_value

def test_create_engineer_agent():
    with patch("src.agents.factory.SystemEngineerAgent") as mock_agent:
        agent = AgentFactory.create_agent("Engineer")
        assert agent == mock_agent.return_value

def test_create_sentiment_agent():
    with patch("src.agents.factory.SentimentAgent") as mock_agent:
        agent = AgentFactory.create_agent("Sentiment")
        assert agent == mock_agent.return_value

def test_create_unknown_agent():
    with pytest.raises(ValueError):
        AgentFactory.create_agent("UnknownAgent")

def test_kwargs_passing():
    with patch("src.agents.factory.MomentumAgent") as mock_agent:
        AgentFactory.create_agent("Momentum", use_cache=False, extra_param="123")
        mock_agent.assert_called_with(use_cache=False, user_id="system", extra_param="123")

def test_create_agent_with_tier_override():
    with patch("src.agents.factory.CIOAgent") as mock_agent:
        # Test default is 'smart'
        AgentFactory.create_cio_agent()
        args, kwargs = mock_agent.call_args
        assert kwargs['tier'] == 'smart'
        
        # Test override is 'advanced'
        AgentFactory.create_cio_agent(tier="advanced")
        args, kwargs = mock_agent.call_args
        assert kwargs['tier'] == 'advanced'
