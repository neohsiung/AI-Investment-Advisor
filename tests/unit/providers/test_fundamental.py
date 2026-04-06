import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.agents.fundamental import FundamentalAgent

@pytest.fixture
def mock_agent_deps():
    """Fixture that creates a FundamentalAgent with a mocked LLM gateway."""
    with patch.dict('os.environ', {'API_KEY': 'test_key'}):
        agent = FundamentalAgent(user_id="test_user")
        mock_gw = AsyncMock()
        mock_gw.chat.return_value = "Fundamental Analysis Report"
        agent._llm_gateway = mock_gw
        yield agent, mock_gw

@pytest.mark.asyncio
async def test_fundamental_agent_run(mock_agent_deps):
    agent, mock_gw = mock_agent_deps
    
    context = {
        "ticker": "AAPL",
        "financials": {"revenue": 100, "net_income": 20},
        "news": [{"title": "Good Earnings", "sentiment": "Positive"}]
    }
    
    # run_tool_loop (now async) is called by run
    with patch.object(FundamentalAgent, 'run_tool_loop', new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = "Fundamental Analysis Report"
        result = await agent.run(context)
        
        assert "Fundamental Analysis Report" in result
        mock_loop.assert_called_once()
        
        # Check that prompt_data passed to run_tool_loop contains the ticker
        call_kwargs = mock_loop.call_args.kwargs
        assert call_kwargs["context"]["ticker"] == "AAPL"

@pytest.mark.asyncio
async def test_fundamental_agent_run_empty_context():
    """Test resilience against missing data"""
    agent = FundamentalAgent(user_id="test_user")
    result = await agent.run({})
    assert result is not None

@pytest.mark.asyncio
async def test_fundamental_agent_batch_mode(mock_agent_deps):
    """Test batch processing of multiple tickers."""
    agent, mock_gw = mock_agent_deps
    
    context = {
        "tickers": ["AAPL", "GOOG"],
        "market_data": {
            "AAPL": {"financials": {"revenue": 100}, "news": [{"title": "News A"}]},
            "GOOG": {"financials": {"revenue": 200}, "news": [{"title": "News B"}]}
        }
    }
    
    # Mock run_tool_loop with AsyncMock side_effects
    with patch.object(FundamentalAgent, 'run_tool_loop', new_callable=AsyncMock) as mock_loop:
        mock_loop.side_effect = ["Analysis of AAPL", "Analysis of GOOG"]
        
        result = await agent.run(context)
        
        assert "### AAPL Analysis" in result
        assert "Analysis of AAPL" in result
        assert "### GOOG Analysis" in result
        assert "Analysis of GOOG" in result
        
        assert mock_loop.call_count == 2
