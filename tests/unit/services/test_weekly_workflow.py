import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.workflow_service import WeeklyWorkflow

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
async def test_weekly_workflow_execution(mock_deps):
    user_id = "test_user"
    mock_deps['trans'].get_user_tickers.return_value = ["AAPL"]
    
    with patch('src.services.workflow_service.PerformanceService') as MockPerf, \
         patch('src.services.broker_factory.BrokerFactory') as MockBrokerFactory, \
         patch('src.services.council_service.CouncilService') as MockCouncil:
        
        # Mock Broker
        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "MockBroker"
        mock_broker.get_account.return_value = MagicMock(total_equity=10000, available_cash=5000)
        MockBrokerFactory.get_broker.return_value = mock_broker

        # Mock Council
        mock_council = MockCouncil.return_value
        mock_council.start_session = AsyncMock(return_value="Council Summary")
        mock_council.get_full_transcript = MagicMock(return_value="Detailed Transcript")

        workflow = WeeklyWorkflow(user_id, transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        
        # Mock Memory Service
        workflow.memory_service = MagicMock()
        workflow.memory_service.detect_conflicts = AsyncMock(return_value=[])
        workflow.memory_service.get_context.return_value.recent_items = []
        
        # Mock LLM Calls
        workflow._call_agent_llm = AsyncMock()
        workflow._call_agent_llm.side_effect = lambda name, ctx, **kwargs: {
            "Momentum": "STRONG BUY",
            "Sentiment": {"sentiment": "Bullish", "score": 0.8},
            "Fundamental": "Solid",
            "Macro": "Macro Context",
            "CIO": "## 1. Summary\n## 2. Debate\n## 3. Debate\n## 4. Orders"
        }.get(name, "Default Response")
        
        # Mock polish
        mock_polisher = MagicMock()
        mock_polisher.polish_report = AsyncMock(return_value="Polished Report")
        
        with patch('src.agents.factory.AgentFactory.create_polisher_agent', return_value=mock_polisher):
            result = await workflow.run(dry_run=True)
            
        assert result == "Polished Report"
        assert mock_council.start_session.called
        assert mock_council.get_full_transcript.called

@pytest.mark.anyio
async def test_weekly_workflow_consensus_transcript(mock_deps):
    workflow = WeeklyWorkflow("test_user", transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
    
    with patch('src.services.council_service.CouncilService') as MockCouncil:
        mock_council = MockCouncil.return_value
        mock_council.get_full_transcript.return_value = "Detailed Debate"
        
        transcript = await workflow._get_consensus_transcript()
        assert "Detailed Debate" in transcript
