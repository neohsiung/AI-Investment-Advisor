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
    
    with patch('src.services.workflow_service.PerformanceService') as MockPerf, \
         patch('src.services.broker_factory.BrokerFactory') as MockBrokerFactory:
        
        # Mock Broker
        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "MockBroker"
        mock_broker.get_account.return_value = MagicMock(total_equity=10000, available_cash=5000)
        MockBrokerFactory.get_broker.return_value = mock_broker

        report_content = "### NVDA (0.5)\n- **Action**: **SELL**\n\n### TSM (0.5)\n- **Action**: **HOLD**"
        
        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        
        # Mock Memory Service to avoid AttributeErrors or logic errors
        workflow.memory_service = MagicMock()
        workflow.memory_service.detect_conflicts = AsyncMock(return_value=[])
        workflow.memory_service.get_context.return_value.recent_items = []
        workflow.memory_service.store_report = AsyncMock()
        
        # v11.1: Mock _call_agent_llm instead of AgentFactory
        workflow._call_agent_llm = AsyncMock()
        workflow._call_agent_llm.side_effect = lambda name, ctx, **kwargs: {
            "Momentum": "STRONG BUY",
            "Sentiment": {"sentiment": "Bullish", "score": 0.8, "narrative": "Good news found."},
            "Fundamental": "Solid",
            "Macro": "Macro Context",
            "CIO": report_content
        }.get(name, "Default Response")
        
        # Mock context setup usually done in collect_data
        workflow.context['tickers'] = ["NVDA", "TSM"]
        workflow.context['market_data'] = {"NVDA": {"price_data": {"close": 100}, "indicators": {}}, "TSM": {"price_data": {"close": 200}, "indicators": {}}}
        
        result = await workflow.run(dry_run=True)
        
        # Verify CIO signal recorded
        calls = workflow.performance_service.record_recommendation.call_args_list
        cio_calls = [c for c in calls if c.kwargs.get('agent_name') == 'CIO']
        assert len(cio_calls) >= 1
        
        # Verify content presence
        assert "Action" in result or "Simulation Mode" in result

@pytest.mark.anyio
async def test_daily_workflow_skip_empty_portfolio(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = []
    
    with patch('src.services.workflow_service.PerformanceService') as MockPerf:
        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        workflow.memory_service = MagicMock() # FIX
        workflow.memory_service.detect_conflicts = AsyncMock(return_value=[])
        result = await workflow.run()
        assert result == "SKIPPED"

@pytest.mark.anyio
async def test_report_distribution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.repositories.report_repository.AlchemyReportRepository') as MockRepo, \
         patch('src.services.broker_factory.BrokerFactory') as MockBrokerFactory, \
         patch('src.services.workflow_service.PerformanceService') as MockPerf, \
         patch('src.services.event_aggregator.EventAggregator.ingest_event') as mock_ingest:
        
        # Mock Broker
        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "MockBroker"
        mock_broker.get_account.return_value = MagicMock(total_equity=10000, available_cash=5000)
        MockBrokerFactory.get_broker.return_value = mock_broker

        workflow = DailyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        workflow.memory_service = MagicMock() # FIX: Ensure memory service is mocked
        workflow.memory_service.detect_conflicts = AsyncMock(return_value=[])
        workflow.memory_service.get_context.return_value.recent_items = []
        workflow.memory_service.store_report = AsyncMock()
        
        # Mock Agents
        workflow._call_agent_llm = AsyncMock()
        workflow._call_agent_llm.side_effect = lambda name, ctx, **kwargs: {
            "Momentum": "STRONG BUY",
            "Sentiment": {"score": 0.5},
            "Fundamental": "Cached Fundamental",
            "Macro": "Macro Context",
            "CIO": "Report"
        }.get(name, "Default Response")

        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance
        
        await workflow.run(dry_run=False)
        
        # Verify that ingest_event was called
        assert mock_ingest.called
        
        # Verify DB storage
        assert mock_repo_instance.save.called
