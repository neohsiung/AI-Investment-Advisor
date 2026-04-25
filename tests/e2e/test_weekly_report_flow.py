import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.workflow_service import WeeklyWorkflow
from src.services.task_planning_service import Task, ExecutionPlan

@pytest.fixture
def mock_transaction_service():
    service = MagicMock()
    service.get_user_tickers.return_value = ["AAPL", "NVDA"]
    return service

@pytest.fixture
def mock_market_service():
    service = MagicMock()
    service.get_market_context.return_value = {
        "AAPL": {"price_data": {"close": 150}},
        "NVDA": {"price_data": {"close": 400}}
    }
    return service

@pytest.fixture
def mock_planner():
    planner = MagicMock()
    task1 = Task(name="Market Cycle Analysis", description="Analyze Macro", complexity=1)
    task2 = Task(name="Report Synthesis", description="Synthesize", complexity=1)
    planner.decompose_goal.return_value = ExecutionPlan(plan_id="p1", goal="g", context={}, tasks=[task1, task2])
    return planner

@pytest.fixture
def workflow(mock_transaction_service, mock_market_service, mock_planner):
    wf = WeeklyWorkflow(
        user_id="test_user",
        transaction_service=mock_transaction_service,
        market_service=mock_market_service
    )
    # Inject Planner
    wf.task_planner = mock_planner
    # Inject No-op Memory Service to avoid Redis calls
    wf.memory_service = MagicMock()
    wf.memory_service.store_report = AsyncMock()
    return wf

@pytest.mark.asyncio
@patch('src.services.workflow_service.BaseWorkflow._call_agent_llm', new_callable=AsyncMock)
async def test_weekly_cycle_flow(mock_llm, workflow, mock_transaction_service, mock_market_service, mock_planner):
    """
    E2E-like test for the weekly report flow.
    Verifies that the workflow orchestrates the Planner and Agents correctly.
    """
    # Mock LLM Responses
    def side_effect(agent_name, *args, **kwargs):
        if agent_name == "Macro": return "Bullish Macro View"
        if agent_name == "CIO": return "Final Weekly Report Content"
        return "Mock Response"
    mock_llm.side_effect = side_effect
    
    # Run the workflow
    report = await workflow.run_weekly_cycle(user_id="test_user")
    
    # Assertions
    # 1. Data Collection
    mock_transaction_service.get_user_tickers.assert_called()
    mock_market_service.get_market_context.assert_called()
    
    # 2. Planning
    from unittest.mock import ANY
    mock_planner.decompose_goal.assert_called_with("Generate Weekly Report", ANY)
    
    # 3. Agent Execution
    assert mock_llm.called
    
    # 4. Final Report
    assert "Final Weekly Report Content" in report or "Bullish Macro View" in report
    
    # 5. Storage (Memory Service)
    workflow.memory_service.store_report.assert_called_with(
        user_id="test_user",
        report_type="weekly",
        date=ANY,
        content=str(report)
    )

@pytest.mark.asyncio
@patch('src.services.workflow_service.BaseWorkflow._call_agent_llm', new_callable=AsyncMock)
async def test_weekly_cycle_flow_legacy_fallback(mock_llm, workflow, mock_transaction_service):
    """Test fallback if Planner is missing."""
    workflow.task_planner = None
    
    # Mock LLM
    mock_llm.return_value = "Final Weekly Report Content"
    
    # It should now try to run the legacy flow. 
    report = await workflow.run_weekly_cycle(user_id="test_user")
    
    assert "Final Weekly Report Content" in report
