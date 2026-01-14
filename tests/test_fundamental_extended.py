import pytest
from unittest.mock import MagicMock, patch
from src.agents.fundamental import FundamentalAgent

@pytest.fixture
def mock_agent_deps():
    # BaseAgent does not use AgentLLMProvider, it uses _call_real_llm
    # We must ensure API_KEY is present to trigger _call_real_llm
    with patch.dict('os.environ', {'API_KEY': 'test_key'}), \
         patch('src.agents.fundamental.FundamentalAgent._call_real_llm') as mock_llm:
        mock_llm.return_value = "Fundamental Analysis Report"
        yield mock_llm

def test_fundamental_agent_run(mock_agent_deps):
    agent = FundamentalAgent(user_id="test_user")
    
    context = {
        "ticker": "AAPL",
        "financials": {"revenue": 100, "net_income": 20},
        "news": [{"title": "Good Earnings", "sentiment": "Positive"}]
    }
    
    result = agent.run(context)
    
    assert "Fundamental Analysis Report" in result
    mock_agent_deps.assert_called_once()
    
    # Check prompt construction (indirectly)
    call_args = mock_agent_deps.call_args
    assert "AAPL" in str(call_args)

def test_fundamental_agent_run_empty_context():
    """Test resilience against missing data"""
    agent = FundamentalAgent(user_id="test_user")
    result = agent.run({})
    assert result is not None

def test_fundamental_agent_deep_dive_mode():
    """Test specific mode if applicable"""
    # Assuming FundamentalAgent might have different behaviors or prompt adjustments
    # Currently it seems to use a standard prompt.
    pass
