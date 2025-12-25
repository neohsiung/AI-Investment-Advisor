import pytest
from unittest.mock import MagicMock, patch
from src.agents.cio import CIOAgent

@pytest.fixture
def mock_transaction_repo():
    return MagicMock()

@pytest.fixture
def cio_agent(mock_transaction_repo):
    with patch('src.agents.cio.SqliteTransactionRepository', return_value=mock_transaction_repo):
        agent = CIOAgent(use_cache=False, transaction_repo=mock_transaction_repo)
        return agent

def test_run_strategy_mode(cio_agent):
    context = {"user_id": "test_user", "macro_report": "Bullish"}
    
    # Mock internal methods
    with patch.object(cio_agent, '_get_portfolio_context', return_value=(1.5, "AAPL (10)")):
        with patch.object(cio_agent, 'call_llm', return_value='{"sector_strategy": {}, "candidates": []}'):
            result = cio_agent.run(context, mode='strategy')
            
            assert isinstance(result, dict)
            assert "sector_strategy" in result
            assert "candidates" in result

def test_run_report_mode(cio_agent):
    context = {"user_id": "test_user", "macro_report": "Bullish"}
    
    with patch.object(cio_agent, '_get_portfolio_context', return_value=(1.5, "AAPL (10)")):
        with patch.object(cio_agent, 'call_llm', return_value='Markdown Report'):
            result = cio_agent.run(context, mode='report')
            
            assert result == "Markdown Report"

def test_get_portfolio_context_no_user(cio_agent):
    lev, summary = cio_agent._get_portfolio_context(None)
    assert lev == 1.0
    assert "No User ID" in summary

def test_get_portfolio_context_error(cio_agent):
    # Mocking the internal db connection block (which we kept temporary)
    with patch('src.data.database.get_db_connection', side_effect=Exception("DB Error")):
        lev, summary = cio_agent._get_portfolio_context("user1")
        assert lev == 1.0
        assert "Error" in summary
