import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.base_agent import BaseAgent
import os
import json

# Define a concrete implementation of BaseAgent for testing
class ConcreteAgent(BaseAgent):
    def run(self, context):
        return "Concrete Result"

@pytest.fixture
def mock_prompt_content():
    return "System Prompt Content with {{ variable }}"

@patch('src.agents.base_agent.get_db_connection')
def test_base_agent_init_and_config(mock_db, mock_prompt_content, tmp_path):
    # Mock DB for settings
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.execute.return_value.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_db.return_value = mock_conn

    # Create a dummy prompt file
    prompt_file = tmp_path / "dummy_prompt.txt"
    with open(prompt_file, 'w') as f:
        f.write(mock_prompt_content)

    agent = ConcreteAgent(name="TEST", prompt_path=str(prompt_file), use_cache=False)

    assert agent.name == "TEST"
    assert agent.system_prompt == mock_prompt_content
    # Check default config
    assert agent.config['provider'] == "Google Gemini"

@patch('src.agents.base_agent.get_db_connection')
def test_base_agent_render_prompt(mock_db, mock_prompt_content, tmp_path):
    mock_db.return_value.execute.return_value.fetchall.return_value = []
    prompt_file = tmp_path / "dummy_prompt.txt"
    with open(prompt_file, 'w') as f:
        f.write("Hello {{ name }}")
    
    agent = ConcreteAgent(name="TEST", prompt_path=str(prompt_file), use_cache=False)
    rendered = agent.render_system_prompt({"name": "World"})
    assert "Hello World" in rendered

@patch('src.agents.base_agent.get_db_connection')
def test_momentum_agent_run(mock_db):
    mock_db.return_value.execute.return_value.fetchall.return_value = []

    # MomentumAgent references hardcoded path likely, so we must mock open
    with patch('builtins.open', mock_open(read_data="Momentum System Prompt")):
        with patch('os.path.exists', return_value=True):
            agent = MomentumAgent(use_cache=False)

            # Mock _mock_llm_call to avoid real logic
            with patch.object(agent, '_mock_llm_call', return_value="BUY AAPL"):
                # v3 Context Structure
                context = {
                    "ticker": "AAPL", 
                    "price_data": {"current_price": 150}, 
                    "indicators": {"rsi": 30}
                }
                result = agent.run(context)
                assert result == "BUY AAPL"
                # Ensure context conversion handled inside run if needed (logic test)

@patch('src.agents.base_agent.get_db_connection')
def test_fundamental_agent_run(mock_db):
    mock_db.return_value.execute.return_value.fetchall.return_value = []

    with patch('builtins.open', mock_open(read_data="Fundamental System Prompt")):
        with patch('os.path.exists', return_value=True):
            agent = FundamentalAgent(use_cache=False)

            with patch.object(agent, '_mock_llm_call', return_value="Strong Fundamentals"):
                context = {"ticker": "AAPL", "financials": {"pe": 15}, "news": []}
                result = agent.run(context)
                assert result == "Strong Fundamentals"

@patch('src.agents.base_agent.get_db_connection')
def test_macro_agent_run(mock_db):
    mock_db.return_value.execute.return_value.fetchall.return_value = []

    with patch('builtins.open', mock_open(read_data="Macro System Prompt")):
        with patch('os.path.exists', return_value=True):
            agent = MacroAgent(use_cache=False)
            with patch.object(agent, '_mock_llm_call', return_value="Risk Off"):
                context = {"macro_data": {"GDP": 2.5}}
                result = agent.run(context)
                assert result == "Risk Off"

@patch('src.agents.base_agent.get_db_connection')
def test_cio_agent_run(mock_db):
    # Mock DB for Settings AND Portfolio Context (transactions, snapshots)
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    
    # 1. Settings
    mock_conn.execute.return_value.fetchall.side_effect = [
        [], # Settings
        [("1.2",)], # Leverage Ratio (using fetchone logic in code but mock return list of tuples for fetchall or similar)
    ]
    
    # Fix: CIOAgent calls text() which returns ResultProxy. fetchone() returns tuple.
    # We need to be careful about side_effect sequence.
    # Calls: 
    # 1. BaseAgent init -> load_settings -> execute(...).fetchall()
    # 2. CIOAgent run -> _get_portfolio_context -> execute(snapshot).fetchone()
    # 3. CIOAgent run -> _get_portfolio_context -> pd.read_sql -> execute(transactions)
    
    # Let's simplify by mocking _get_portfolio_context
    
    with patch('builtins.open', mock_open(read_data="CIO System Prompt")):
        with patch('os.path.exists', return_value=True):
            agent = CIOAgent(use_cache=False)
            
            # Mock _get_portfolio_context to avoid complex DB mocking
            with patch.object(agent, '_get_portfolio_context', return_value=(1.1, "AAPL (10)")):
                with patch.object(agent, '_mock_llm_call', return_value="Final Decision"):
                    context = {
                        "user_id": "test_user",
                        "momentum_reports": "Mom says Buy",
                        "fundamental_reports": "Fund says Hold",
                        "macro_report": "Macro says Down"
                    }
                    result = agent.run(context)
                    assert result == "Final Decision"
