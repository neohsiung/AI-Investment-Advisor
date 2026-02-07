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

def test_fundamental_agent_batch_mode(mock_agent_deps):
    """Test batch processing of multiple tickers."""
    agent = FundamentalAgent(user_id="test_user")
    
    context = {
        "tickers": ["AAPL", "GOOG"],
        "market_data": {
            "AAPL": {"financials": {"revenue": 100}, "news": [{"title": "News A"}]},
            "GOOG": {"financials": {"revenue": 200}, "news": [{"title": "News B"}]}
        }
    }
    
    # Mock return value changes per call? Or just static.
    # mock_agent_deps is the mock_llm function.
    mock_agent_deps.side_effect = ["Analysis of AAPL", "Analysis of GOOG"]
    
    result = agent.run(context)
    
    assert "### AAPL Analysis" in result
    assert "Analysis of AAPL" in result
    assert "### GOOG Analysis" in result
    assert "Analysis of GOOG" in result
    
    assert mock_agent_deps.call_count == 2
