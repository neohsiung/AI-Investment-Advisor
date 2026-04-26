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

    cio_report = "## 1. Summary\n## 2. Debate\n## 3. Debate\n## 4. Orders"

    with patch('src.services.workflow_service.PerformanceService'), \
         patch('src.services.workflow_service.MemoryService'), \
         patch('src.services.workflow_service.TaskPlanningService'), \
         patch('src.services.workflow_service.AlchemyMemoryRepository'), \
         patch('src.services.workflow_service.AgentLLMProvider'):

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
            "CIO": cio_report
        }.get(name, "Default Response")

        result = await workflow.run(dry_run=True)

    assert isinstance(result, str)
    assert len(result) > 0
    workflow._call_agent_llm.assert_called()

@pytest.mark.anyio
async def test_weekly_workflow_synthesize_results(mock_deps):
    with patch('src.services.workflow_service.PerformanceService'), \
         patch('src.services.workflow_service.TaskPlanningService'), \
         patch('src.services.workflow_service.MemoryService'), \
         patch('src.services.workflow_service.AlchemyMemoryRepository'), \
         patch('src.services.workflow_service.AgentLLMProvider'):

        workflow = WeeklyWorkflow("test_user", transaction_repo=mock_deps['repo'], transaction_service=mock_deps['trans'], market_service=mock_deps['market'])
        workflow.context['tickers'] = ["AAPL"]
        workflow.context['macro_report'] = "Stable macro"

        workflow.memory_service = MagicMock()
        workflow.memory_service.get_context.return_value.recent_items = []

        cio_output = "## CIO Weekly Report\nBuy AAPL"
        workflow._call_agent_llm = AsyncMock(return_value=cio_output)

        result = await workflow.synthesize_results()
        assert cio_output in result
