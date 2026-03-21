import pytest
from unittest.mock import MagicMock, patch
from src.agents.fundamental import FundamentalAgent

@pytest.fixture
def mock_agent_deps():
    """Fixture that creates a FundamentalAgent with a mocked LLM gateway."""
    with patch.dict('os.environ', {'API_KEY': 'test_key'}):
        agent = FundamentalAgent(user_id="test_user")
        mock_gw = MagicMock()
        mock_gw.chat.return_value = "Fundamental Analysis Report"
        agent._llm_gateway = mock_gw
        yield agent, mock_gw

def test_fundamental_agent_run(mock_agent_deps):
    agent, mock_gw = mock_agent_deps
    
    context = {
        "ticker": "AAPL",
        "financials": {"revenue": 100, "net_income": 20},
        "news": [{"title": "Good Earnings", "sentiment": "Positive"}]
    }
    
    result = agent.run(context)
    
    assert "Fundamental Analysis Report" in result
    mock_gw.chat.assert_called_once()
    
    # Check prompt construction (indirectly via gateway messages)
    call_args = mock_gw.chat.call_args
    assert "AAPL" in str(call_args)

def test_fundamental_agent_run_empty_context():
    """Test resilience against missing data"""
    agent = FundamentalAgent(user_id="test_user")
    result = agent.run({})
    assert result is not None

def test_fundamental_agent_batch_mode(mock_agent_deps):
    """Test batch processing of multiple tickers."""
    agent, mock_gw = mock_agent_deps
    
    context = {
        "tickers": ["AAPL", "GOOG"],
        "market_data": {
            "AAPL": {"financials": {"revenue": 100}, "news": [{"title": "News A"}]},
            "GOOG": {"financials": {"revenue": 200}, "news": [{"title": "News B"}]}
        }
    }
    
    mock_gw.chat.side_effect = ["Analysis of AAPL", "Analysis of GOOG"]
    
    result = agent.run(context)
    
    assert "### AAPL Analysis" in result
    assert "Analysis of AAPL" in result
    assert "### GOOG Analysis" in result
    assert "Analysis of GOOG" in result
    
    assert mock_gw.chat.call_count == 2
