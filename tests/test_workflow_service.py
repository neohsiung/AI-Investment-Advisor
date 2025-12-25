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
    
    # Patch agents used internally
    with patch('src.services.workflow_service.MomentumAgent') as MockMom:
        MockMom.return_value.run.return_value = "STRONG BUY"
        
        result = workflow.run(dry_run=True)
        
        assert "STRONG BUY" in result
        mock_deps['trans'].get_user_tickers.assert_called_with(user_id)
        MockMom.assert_called()

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
    
    with patch('src.services.workflow_service.MomentumAgent') as MockMom, \
         patch('src.services.workflow_service.FundamentalAgent') as MockFund, \
         patch('src.services.workflow_service.MacroAgent') as MockMacro, \
         patch('src.services.workflow_service.CIOAgent') as MockCIO, \
         patch('src.services.workflow_service.SystemEngineerAgent') as MockEng:
        
        MockMacro.return_value.run.return_value = "Macro ok"
        MockFund.return_value.run.return_value = "Fund ok"
        MockMom.return_value.run.return_value = "Mom ok"
        MockCIO.return_value.run.return_value = "Final Report"
        
        result = workflow.run(dry_run=True)
        
        assert result == "Final Report"
        MockMacro.assert_called()
        MockCIO.assert_called()

def test_report_distribution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
    
    # Patch where they are defined because they are imported locally or used as globals in method
    with patch('src.services.workflow_service.MomentumAgent') as MockMom, \
         patch('src.services.workflow_service.get_db_connection') as MockDB, \
         patch('src.notifier.EmailNotifier') as MockEmail:
        
        MockMom.return_value.run.return_value = "STRONG BUY"
        MockDB.return_value = MagicMock()
        
        workflow.run(dry_run=False)
        
        MockEmail.return_value.send_report.assert_called()
        MockDB.return_value.execute.assert_called()
