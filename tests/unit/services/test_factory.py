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
    with patch("src.agents.factory.AlchemySettingsRepository") as MockRepo:
        # Simulate DB returning an API key for the user
        MockRepo.return_value.get.return_value = "test_key"
        # Reset state
        AgentFactory._dspy_configured = False
        AgentFactory._configure_dspy(user_id="test_user")

        # Since has_dspy is mocked to True and we have an api_key, configure should be called
        mock_dspy.settings.configure.assert_called()
        assert AgentFactory._dspy_configured is True

def test_configure_dspy_without_env(mock_dspy, enable_has_dspy):
    with patch.dict(os.environ, {}, clear=True):
        # Also mock the settings repo to return empty
        with patch("src.agents.factory.AlchemySettingsRepository") as MockRepo:
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

# ─────────────────────────────────────────────────────────────────────────────
# create_agent() construction
#
# These patched `src.agents.factory.<ClassName>` — the classes as imported into
# the factory module. The factory no longer imports them: it resolves the agent
# through config/agents/*.md and src/agents/impls.py, which imports each class
# lazily from its own module at call time. The patch targets therefore moved to
# where the classes actually live.
#
# The assertions themselves are unchanged in substance: create_agent(name) must
# still produce the right class and forward kwargs.
#
# 原本 patch 的是 factory 模組中匯入的類別；factory 已改為透過 manifest 與
# impls.py 在呼叫時才由各自模組匯入，故 patch 目標移到類別實際所在位置。
# 斷言本身的意義未變：create_agent(name) 仍須產生正確類別並轉傳 kwargs。
# ─────────────────────────────────────────────────────────────────────────────

def test_create_momentum_agent():
    with patch("src.agents.swarm.momentum_swarm.MomentumSwarm") as mock_agent:
        agent = AgentFactory.create_agent("Momentum", user_id="test_user")
        assert agent == mock_agent.return_value

def test_create_fundamental_agent():
    with patch("src.agents.swarm.fundamental_swarm.FundamentalSwarm") as mock_agent:
        agent = AgentFactory.create_agent("Fundamental", user_id="test_user")
        assert agent == mock_agent.return_value

def test_create_macro_agent():
    with patch("src.agents.macro.MacroAgent") as mock_agent:
        agent = AgentFactory.create_agent("Macro", user_id="test_user")
        assert agent == mock_agent.return_value

def test_create_cio_agent():
    with patch("src.agents.cio.CIOAgent") as mock_agent:
        agent = AgentFactory.create_agent("CIO", mode="daily", user_id="test_user")
        assert agent == mock_agent.return_value

def test_create_engineer_agent():
    with patch("src.agents.system_engineer_agent.SystemEngineerAgent") as mock_agent:
        agent = AgentFactory.create_agent("Engineer", user_id="test_user")
        assert agent == mock_agent.return_value

def test_create_sentiment_agent():
    with patch("src.agents.swarm.sentiment_swarm.SentimentSwarm") as mock_agent:
        agent = AgentFactory.create_agent("Sentiment", user_id="test_user")
        assert agent == mock_agent.return_value

def test_create_unknown_agent():
    with pytest.raises(ValueError):
        AgentFactory.create_agent("UnknownAgent", user_id="test_user")

def test_kwargs_passing():
    with patch("src.agents.swarm.momentum_swarm.MomentumSwarm") as mock_agent:
        AgentFactory.create_agent("Momentum", extra_param="123", user_id="test_user")
        _, kwargs = mock_agent.call_args
        assert kwargs["user_id"] == "test_user"
        assert kwargs["extra_param"] == "123"

def test_agents_the_old_chain_could_not_build():
    """
    "Momentum Scout" and "Verifier" are named by config/workflows/*.yaml, but the
    if/elif chain this replaced had no branch for either — it raised
    "Unknown agent type" for both. Declaring them in config/agents/ makes them
    constructible.
    workflow YAML 會指名這兩個代理，但原本的 if/elif 鏈沒有對應分支，一律拋錯。
    """
    with patch("src.agents.swarm.momentum_swarm.MomentumSwarm") as mock_swarm:
        assert AgentFactory.create_agent("Momentum Scout", user_id="u1") == mock_swarm.return_value
    with patch("src.agents.risk.RiskAgent") as mock_risk:
        assert AgentFactory.create_agent("Verifier", user_id="u1") == mock_risk.return_value


def test_unknown_agent_error_names_the_available_agents():
    """A bare "Unknown agent type" left the operator guessing what was valid."""
    with pytest.raises(ValueError) as exc:
        AgentFactory.create_agent("Nope", user_id="u1")
    assert "cio" in str(exc.value)


def test_create_agent_with_tier_override():
    with patch("src.agents.cio.CIOAgent") as mock_agent:
        # Test default is 'smart'
        AgentFactory.create_cio_agent(user_id="test_user")
        args, kwargs = mock_agent.call_args
        assert kwargs['tier'] == 'smart'
        
        # Test override is 'advanced'
        AgentFactory.create_cio_agent(tier="advanced", user_id="test_user")
        args, kwargs = mock_agent.call_args
        assert kwargs['tier'] == 'advanced'
