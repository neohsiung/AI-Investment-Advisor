import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.agents.cio import CIOAgent

@pytest.fixture
def mock_transaction_repo():
    # Use strict spec to ensure we only call existing methods
    from src.repositories.transaction_repository import ITransactionRepository
    repo = MagicMock(spec=ITransactionRepository)
    # Default returns to avoid non-iterable errors
    repo.get_holdings_summary.return_value = []
    repo.get_latest_leverage.return_value = 1.0
    return repo

@pytest.fixture
def cio_agent(mock_transaction_repo):
    # Pass repo directly
    agent = CIOAgent(user_id="test_user", use_cache=False, transaction_repo=mock_transaction_repo)
    return agent

@pytest.mark.asyncio
async def test_run_strategy_mode(cio_agent):
    context = {"user_id": "test_user", "macro_report": "Bullish"}
    
    # Mock internal methods used in strategy
    # call_llm is now async
    with patch.object(cio_agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '{"sector_strategy": {}, "candidates": []}'
        # We don't verify portfolio context details here, just that it runs
        result = await cio_agent.run(context, mode='strategy')
        
        assert isinstance(result, dict)
        assert "sector_strategy" in result
        assert "candidates" in result

@pytest.mark.asyncio
async def test_run_report_mode(cio_agent):
    context = {"user_id": "test_user", "macro_report": "Bullish"}
    
    # Mock run_tool_loop since report mode uses it
    with patch.object(cio_agent, 'run_tool_loop', return_value='Markdown Report'):
        result = await cio_agent.run(context, mode='report')
        assert result == "Markdown Report"

def test_get_portfolio_context_success(cio_agent, mock_transaction_repo):
    # Setup
    mock_transaction_repo.get_active_tickers.return_value = ["AAPL", "GOOG"]
    mock_transaction_repo.get_holdings_summary.return_value = [("AAPL", 10.0), ("GOOG", 5.0)]
    mock_transaction_repo.get_latest_leverage.return_value = 1.5
    
    lev, summary = cio_agent._get_portfolio_context("user1")
    
    # Assert
    mock_transaction_repo.get_active_tickers.assert_called_with("user1")
    assert lev == 1.5
    assert "AAPL (10.00)" in summary
    assert "GOOG (5.00)" in summary

def test_get_portfolio_context_error(cio_agent, mock_transaction_repo):
    # Setup failure
    mock_transaction_repo.get_active_tickers.side_effect = Exception("DB Error")
    
    lev, summary = cio_agent._get_portfolio_context("user1")
    
    assert lev == 1.0
    assert "Error" in summary
