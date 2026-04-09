
import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.base_agent import BaseAgent
from src.repositories.settings_repository import ISettingsRepository
from src.repositories.agent_state_repository import IAgentStateRepository
import json

# Define a concrete implementation of BaseAgent for testing
class ConcreteAgent(BaseAgent):
    def run(self, context, mode=None):
        return "Concrete Result"

@pytest.fixture
def mock_prompt_content():
    return "System Prompt Content with {{ variable }}"

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock(spec=ISettingsRepository)
    repo.get_all.return_value = []
    repo.get_all.return_value = []
    return repo

@pytest.fixture
def mock_state_repo():
    repo = MagicMock(spec=IAgentStateRepository)
    repo.get_state.return_value = None
    return repo

def test_base_agent_init_and_config(mock_settings_repo, mock_state_repo, mock_prompt_content, tmp_path):
    # Setup Mock Repo responses
    # Mocking rows for BaseAgent._load_config_from_db
    class MockRow:
        def __init__(self, k, v):
            self.k = k
            self.v = v
            self._mapping = {'key': k, 'value': v}
        def __getitem__(self, idx):
            return [self.k, self.v][idx]
    mock_settings_repo.get_all.return_value = [MockRow("AI_PROVIDER", "TestProvider")]

    # Create a dummy prompt file
    prompt_file = tmp_path / "dummy_prompt.txt"
    with open(prompt_file, 'w') as f:
        f.write(mock_prompt_content)

    with patch("src.agents.base_agent.BudgetAwareModelRouter") as mock_router:
        mock_router.side_effect = Exception("Router Disabled for Test")
        agent = ConcreteAgent(name="TEST", prompt_path=str(prompt_file), use_cache=False, 
                              user_id="test_user",
                              settings_repo=mock_settings_repo, state_repo=mock_state_repo)

    assert agent.name == "TEST"
    assert agent.system_prompt == mock_prompt_content
    # Check loaded config
    assert agent.config['provider'] == "TestProvider"
    mock_settings_repo.get_all.assert_called_with("test_user")

def test_base_agent_render_prompt(mock_settings_repo, mock_state_repo, tmp_path):
    prompt_file = tmp_path / "dummy_prompt.txt"
    with open(prompt_file, 'w') as f:
        f.write("Hello {{ name }}")
    
    agent = ConcreteAgent(name="TEST", prompt_path=str(prompt_file), use_cache=False,
                          user_id="test_user",
                          settings_repo=mock_settings_repo, state_repo=mock_state_repo)
    rendered = agent.render_system_prompt({"name": "World"})
    assert "Hello World" in rendered

@pytest.mark.asyncio
async def test_momentum_agent_run(mock_settings_repo, mock_state_repo):
    # Use _load_prompt patch to avoid builtins.open
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Momentum System Prompt"):
        agent = MomentumAgent(user_id="test_user", use_cache=False, settings_repo=mock_settings_repo, state_repo=mock_state_repo)

        # Inject gateway mock for LLM call
        from unittest.mock import MagicMock
        mock_gw = MagicMock()
        mock_gw.chat.return_value = "BUY AAPL"
        agent._llm_gateway = mock_gw

        context = {
            "ticker": "AAPL", 
            "price_data": {"current_price": 150}, 
            "indicators": {"rsi": 30}
        }
        result = await agent.run(context)
        assert result == "BUY AAPL"

@pytest.mark.asyncio
async def test_fundamental_agent_run(mock_settings_repo, mock_state_repo):
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Fundamental System Prompt"):
        agent = FundamentalAgent(user_id="test_user", use_cache=False, settings_repo=mock_settings_repo, state_repo=mock_state_repo)

        from unittest.mock import MagicMock
        mock_gw = MagicMock()
        mock_gw.chat.return_value = "Strong Fundamentals"
        agent._llm_gateway = mock_gw

        context = {"ticker": "AAPL", "financials": {"pe": 15}, "news": []}
        result = await agent.run(context)
        assert result == "Strong Fundamentals"

@pytest.mark.asyncio
async def test_macro_agent_run(mock_settings_repo, mock_state_repo):
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Macro System Prompt"):
        agent = MacroAgent(user_id="test_user", use_cache=False, settings_repo=mock_settings_repo, state_repo=mock_state_repo)

        from unittest.mock import MagicMock
        mock_gw = MagicMock()
        mock_gw.chat.return_value = "Risk Off"
        agent._llm_gateway = mock_gw

        context = {"macro_data": {"GDP": 2.5}}
        result = await agent.run(context)
        assert result == "Risk Off"

@pytest.mark.asyncio
async def test_cio_agent_run(mock_settings_repo, mock_state_repo):
    # Mock Transaction Repo needed for CIO
    mock_trans_repo = MagicMock()
    
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="CIO System Prompt"):
        agent = CIOAgent(user_id="test_user", use_cache=False, transaction_repo=mock_trans_repo, 
                         settings_repo=mock_settings_repo, state_repo=mock_state_repo)
        
        # Inject gateway mock for LLM call
        mock_gw = MagicMock()
        mock_gw.chat.return_value = "Final Decision"
        agent._llm_gateway = mock_gw

        # Mock _get_portfolio_context
        with patch.object(agent, '_get_portfolio_context', return_value=(1.1, "AAPL (10)")):
            context = {
                "user_id": "test_user",
                "momentum_reports": "Mom says Buy",
                "fundamental_reports": "Fund says Hold",
                "macro_report": "Macro says Down"
            }
            result = await agent.run(context)
            assert result == "Final Decision"
