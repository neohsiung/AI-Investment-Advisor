import pytest
from unittest.mock import MagicMock, patch
from src.services.workflow_service import DailyWorkflow, WeeklyWorkflow

@pytest.fixture
def mock_deps():
    repo = MagicMock()
    trans = MagicMock()
    market = MagicMock()
    return {"repo": repo, "trans": trans, "market": market}

def test_daily_workflow_execution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    # Instantiate with mocks
    workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
    
    # Patch AgentFactory
    with patch('src.services.workflow_service.AgentFactory') as MockFactory:
        mock_mom = MagicMock()
        mock_mom.run.return_value = "STRONG BUY"
        MockFactory.create_momentum_agent.return_value = mock_mom
        
        result = workflow.run(dry_run=True)
        
        assert "STRONG BUY" in result
        mock_deps['trans'].get_user_tickers.assert_called_with(user_id)
        # Verify Factory called with correct params
        MockFactory.create_momentum_agent.assert_called_with(ttl_hours=1, use_cache=True)

def test_daily_workflow_skip_empty_portfolio(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = []
    
    workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
    
    result = workflow.run()
    assert result == "SKIPPED"

def test_weekly_workflow_execution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    workflow = WeeklyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory:
         
        mock_macro = MagicMock()
        mock_macro.run.return_value = "Macro ok"
        MockFactory.create_macro_agent.return_value = mock_macro
        
        mock_fund = MagicMock()
        mock_fund.run.return_value = "Fund ok"
        MockFactory.create_fundamental_agent.return_value = mock_fund
        
        mock_mom = MagicMock()
        mock_mom.run.return_value = "Mom ok"
        MockFactory.create_momentum_agent.return_value = mock_mom
        
        mock_cio = MagicMock()
        mock_cio.run.return_value = "Final Report"
        MockFactory.create_cio_agent.return_value = mock_cio # Note: CIO created in __init__
        
        # Re-instantiate workflow to catch the __init__ call for CIO
        workflow = WeeklyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])

        result = workflow.run(dry_run=True)
        
        assert result == "Final Report"
        mock_macro.run.assert_called()
        mock_cio.run.assert_called()

def test_report_distribution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    # Patch before instantiation for CIO
    with patch('src.services.workflow_service.AgentFactory') as MockFactory, \
         patch('src.services.workflow_service.get_db_connection') as MockDB, \
         patch('src.notifier.EmailNotifier') as MockEmail:
        
        mock_mom = MagicMock()
        mock_mom.run.return_value = "STRONG BUY"
        MockFactory.create_momentum_agent.return_value = mock_mom
        
        mock_cio = MagicMock()
        MockFactory.create_cio_agent.return_value = mock_cio

        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        
        MockDB.return_value = MagicMock()
        
        workflow.run(dry_run=False)
        
        MockEmail.return_value.send_report.assert_called()
        MockDB.return_value.execute.assert_called()
