import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.workflow_service import DailyWorkflow, WeeklyWorkflow

@pytest.fixture
def anyio_backend():
    return 'asyncio'

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
    market.get_macro_data.return_value = {"market_indicators": {"^VIX": 15, "SPY": 400}, "economics": {}}
    return {"repo": repo, "trans": trans, "market": market}


@pytest.mark.anyio
async def test_daily_workflow_execution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory, \
         patch('src.services.workflow_service.PerformanceService') as MockPerf, \
         patch('src.services.broker_factory.BrokerFactory') as MockBrokerFactory:
        
        # Mock Broker
        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "MockBroker"
        mock_broker.get_account.return_value = MagicMock(total_equity=10000, available_cash=5000)
        MockBrokerFactory.get_broker.return_value = mock_broker

        # Mock Agents
        mock_mom = MagicMock()
        mock_mom.run.return_value = "STRONG BUY"
        MockFactory.create_momentum_agent.return_value = mock_mom

        mock_sent = MagicMock()
        mock_sent.run.return_value = {"sentiment": "Bullish", "score": 0.8, "narrative": "Good news found."}
        MockFactory.create_sentiment_agent.return_value = mock_sent

        mock_fund = MagicMock()
        mock_fund.run.return_value = "Solid"
        MockFactory.create_fundamental_agent.return_value = mock_fund
        
        mock_macro = MagicMock()
        mock_macro.run.return_value = "Macro Context"
        MockFactory.create_macro_agent.return_value = mock_macro

        mock_cio = MagicMock()
        report_content = """
### NVDA (0.5)
- **Action**: **SELL**

### TSM (0.5)
- **Action**: **HOLD**
"""
        mock_cio.run.return_value = report_content
        mock_cio.polish_report.side_effect = lambda x: x # Identity function
        MockFactory.create_cio_agent.return_value = mock_cio
        
        # Instantiate inside structure where Factory is active
        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        
        # Mock Memory Service to avoid AttributeErrors or logic errors
        workflow.memory_service = MagicMock()
        workflow.memory_service.detect_conflicts.return_value = []
        workflow.memory_service.get_context.return_value.recent_items = []
        
        # Mock context setup usually done in collect_data
        workflow.context['tickers'] = ["NVDA", "TSM"]
        workflow.context['market_data'] = {"NVDA": {"price_data": {"close": 100}, "indicators": {}}, "TSM": {"price_data": {"close": 200}, "indicators": {}}}
        
        result = await workflow.run(dry_run=True)
        
        # Verify CIO signal recorded
        calls = workflow.performance_service.record_recommendation.call_args_list
        cio_calls = [c for c in calls if c.kwargs.get('agent_name') == 'CIO']
        assert len(cio_calls) >= 1
        
        # Verify content presence
        assert "Action" in result
        assert "SELL" in result

@pytest.mark.anyio
async def test_daily_workflow_skip_empty_portfolio(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = []
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory:
        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        workflow.memory_service = MagicMock() # FIX
        result = await workflow.run()
        assert result == "SKIPPED"

@pytest.mark.anyio
async def test_report_distribution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.services.workflow_service.AgentFactory') as MockFactory, \
         patch('src.services.workflow_service.get_db_connection') as MockDB, \
         patch('src.services.broker_factory.BrokerFactory') as MockBrokerFactory, \
         patch('src.services.notification_service.NotificationService.create_with_settings') as MockNotiFactory, \
         patch('src.services.workflow_service.PerformanceService') as MockPerf:
        
        # Mock Broker
        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "MockBroker"
        mock_broker.get_account.return_value = MagicMock(total_equity=10000, available_cash=5000)
        MockBrokerFactory.get_broker.return_value = mock_broker

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

        # Mock Notifier
        mock_notifier = MagicMock()
        mock_notifier.send_report = AsyncMock(return_value={"Email": True})
        MockNotiFactory.return_value = mock_notifier

        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        workflow.memory_service = MagicMock() # FIX: Ensure memory service is mocked
        workflow.memory_service.get_context.return_value.recent_items = []

        mock_conn = MagicMock()
        MockDB.return_value = mock_conn
        
        await workflow.run(dry_run=False)
        
        mock_notifier.send_report.assert_called()
        mock_conn.execute.assert_called()
