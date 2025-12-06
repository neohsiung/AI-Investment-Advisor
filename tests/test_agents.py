import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.base_agent import BaseAgent
import os
import json

# Define a concrete implementation of BaseAgent for testing
class ConcreteAgent(BaseAgent):
    def run(self, context):
        return "Concrete Result"

@pytest.fixture
def mock_prompt_content():
    return "System Prompt Content"

@patch('src.agents.base_agent.get_db_connection')
def test_base_agent_init_and_config(mock_db, mock_prompt_content, tmp_path):
    # Mock DB for settings
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # Return empty settings to use defaults
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_db.return_value = mock_conn
    
    # Create a dummy prompt file
    prompt_file = tmp_path / "dummy_prompt.txt"
    prompt_file.write_text(mock_prompt_content)
    
    agent = ConcreteAgent(name="TEST", prompt_path=str(prompt_file), use_cache=False)
    
    assert agent.getName() == "TEST" if hasattr(agent, 'getName') else agent.name == "TEST"
    assert agent.system_prompt == mock_prompt_content
    # Check default config
    assert agent.config['provider'] == "Google Gemini"

@patch('src.agents.base_agent.get_db_connection')
@patch('src.agents.base_agent.requests.post')
def test_base_agent_call_real_llm(mock_post, mock_db, mock_prompt_content, tmp_path):
    # Mock DB
    mock_db.return_value.cursor.return_value.fetchall.return_value = []
    
    # Create dummy prompt
    prompt_file = tmp_path / "dummy_prompt.txt"
    prompt_file.write_text(mock_prompt_content)
    
    # Initialize agent
    agent = ConcreteAgent(name="TEST", prompt_path=str(prompt_file), use_cache=False)
    
    # Mock Config to have API Key
    agent.config['api_key'] = "sk-test"
    agent.config['provider'] = "OpenAI" # Test OpenAI path for simplicity
    
    # Mock API Success
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "Real LLM Response"}}]
    }
    
    response = agent._call_real_llm("User Prompt", "Sys Prompt")
    assert response == "Real LLM Response"
    
    # Test API Failure
    mock_post.side_effect = Exception("API Error")
    with pytest.raises(Exception):
        agent._call_real_llm("User Prompt", "Sys Prompt")

@patch('src.agents.base_agent.get_db_connection')
def test_momentum_agent_run(mock_db):
    mock_db.return_value.cursor.return_value.fetchall.return_value = []
    
    # MomentumAgent references hardcoded path likely, so we must mock open
    with patch('builtins.open', mock_open(read_data="Momentum System Prompt")):
        with patch('os.path.exists', return_value=True):
            agent = MomentumAgent(use_cache=False)
            
            # Mock _mock_llm_call to avoid real logic
            with patch.object(agent, '_mock_llm_call', return_value="BUY AAPL"):
                context = {"ticker": "AAPL", "price": 150, "indicators": {}}
                result = agent.run(context)
                assert "BUY" in result

@patch('src.agents.base_agent.get_db_connection')
def test_fundamental_agent_run(mock_db):
    mock_db.return_value.cursor.return_value.fetchall.return_value = []
    
    with patch('builtins.open', mock_open(read_data="Fundamental System Prompt")):
        with patch('os.path.exists', return_value=True):
            agent = FundamentalAgent(use_cache=False)
            
            with patch.object(agent, '_mock_llm_call', return_value="Strong Fundamentals"):
                context = {"ticker": "AAPL", "financials": {}, "news": []}
                result = agent.run(context)
                assert "Fundamentals" in result
