import pytest
from unittest.mock import MagicMock, patch
from src.services.workflow_service import DailyWorkflow, WeeklyWorkflow

@pytest.fixture
def mock_deps():
    repo = MagicMock()
    trans = MagicMock()
    market = MagicMock()
    # Setup market context mock
    market.get_market_context.return_value = {
        "AAPL": {
            "price_data": {"close": 150.0},
            "indicators": {}
        }
    }
    market.get_news.return_value = []
    market.get_financials.return_value = {}
    market.get_macro_data.return_value = {"^VIX": 15, "SPY": 400}
    return {"repo": repo, "trans": trans, "market": market}

def test_daily_workflow_execution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory, \
         patch('src.services.workflow_service.PerformanceService') as MockPerf:
        
        # Mock Agents
        mock_mom = MagicMock()
        mock_mom.run.return_value = "STRONG BUY"
        MockFactory.create_momentum_agent.return_value = mock_mom

        mock_sent = MagicMock()
        mock_sent.run.return_value = "Bullish"
        MockFactory.create_sentiment_agent.return_value = mock_sent

        mock_fund = MagicMock()
        mock_fund.run.return_value = "Solid"
        MockFactory.create_fundamental_agent.return_value = mock_fund
        
        mock_macro = MagicMock()
        mock_macro.run.return_value = "Macro Context"
        MockFactory.create_macro_agent.return_value = mock_macro

        mock_cio = MagicMock()
        mock_cio.run.return_value = "Daily Report with STRONG BUY"
        MockFactory.create_cio_agent.return_value = mock_cio
        
        # Instantiate inside structure where Factory is active
        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        
        result = workflow.run(dry_run=True)
        
        assert "STRONG BUY" in result
        mock_deps['trans'].get_user_tickers.assert_called_with(user_id, only_active=True)
        # Verify Factory called
        MockFactory.create_momentum_agent.assert_called()

def test_daily_workflow_skip_empty_portfolio(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = []
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory:
        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        result = workflow.run()
        assert result == "SKIPPED"

def test_weekly_workflow_execution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory, \
         patch('src.services.workflow_service.PerformanceService') as MockPerf:
         
        mock_macro = MagicMock()
        mock_macro.run.return_value = "Macro ok"
        MockFactory.create_macro_agent.return_value = mock_macro
        
        mock_fund = MagicMock()
        mock_fund.run.return_value = "Fund ok"
        MockFactory.create_fundamental_agent.return_value = mock_fund
        
        mock_mom = MagicMock()
        mock_mom.run.return_value = "Mom ok"
        MockFactory.create_momentum_agent.return_value = mock_mom

        mock_sent = MagicMock()
        mock_sent.run.return_value = "Sent ok"
        MockFactory.create_sentiment_agent.return_value = mock_sent
        
        mock_cio = MagicMock()
        mock_cio.run.return_value = "Final Report"
        MockFactory.create_cio_agent.return_value = mock_cio
        
        mock_engineer = MagicMock()
        mock_engineer.run.return_value = "Optimized"
        MockFactory.create_agent.return_value = mock_engineer # For 'Engineer' via create_agent
        
        workflow = WeeklyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])

        result = workflow.run(dry_run=True)
        
        assert result == "Final Report"
        mock_macro.run.assert_called()
        mock_cio.run.assert_called()

def test_report_distribution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory, \
         patch('src.services.workflow_service.get_db_connection') as MockDB, \
         patch('src.notifier.EmailNotifier') as MockEmail, \
         patch('src.services.workflow_service.PerformanceService') as MockPerf:
        
        mock_mom = MagicMock()
        mock_mom.run.return_value = "STRONG BUY"
        MockFactory.create_momentum_agent.return_value = mock_mom
        
        # Mock other agents
        MockFactory.create_sentiment_agent.return_value = MagicMock()
        MockFactory.create_fundamental_agent.return_value = MagicMock()
        MockFactory.create_macro_agent.return_value = MagicMock()
        
        mock_cio = MagicMock()
        mock_cio.run.return_value = "Report"
        MockFactory.create_cio_agent.return_value = mock_cio

        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        
        mock_conn = MagicMock()
        MockDB.return_value = mock_conn
        
        workflow.run(dry_run=False)
        
        MockEmail.return_value.send_report.assert_called()
        mock_conn.execute.assert_called()
