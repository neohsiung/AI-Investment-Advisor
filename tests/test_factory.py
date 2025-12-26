import pytest
from unittest.mock import MagicMock, patch
import os
from src.agents.factory import AgentFactory
from src.agents.base_agent import BaseAgent

@pytest.fixture
def mock_dspy():
    with patch("src.agents.factory.dspy") as mock:
        yield mock

def test_configure_dspy_with_env(mock_dspy):
    with patch.dict(os.environ, {"LLM_API_KEY": "test_key", "LLM_MODEL_SMART": "test_model"}):
        # Reset state
        AgentFactory._dspy_configured = False
        AgentFactory._configure_dspy()
        
        mock_dspy.settings.configure.assert_called()
        assert AgentFactory._dspy_configured is True

def test_configure_dspy_without_env(mock_dspy):
    with patch.dict(os.environ, {}, clear=True):
        AgentFactory._dspy_configured = False
        AgentFactory._configure_dspy()
        
        mock_dspy.settings.configure.assert_not_called()
        # Should log warning but not crash

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

def test_create_dispatcher_agent():
    with patch("src.agents.factory.DispatcherAgent") as mock_agent:
        agent = AgentFactory.create_agent("Dispatcher")
        assert agent == mock_agent.return_value

def test_create_unknown_agent():
    with pytest.raises(ValueError):
        AgentFactory.create_agent("UnknownAgent")

def test_kwargs_passing():
    with patch("src.agents.factory.MomentumAgent") as mock_agent:
        AgentFactory.create_agent("Momentum", use_cache=False, extra_param="123")
        mock_agent.assert_called_with(use_cache=False, extra_param="123")
