import pytest
from unittest.mock import MagicMock, patch
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
def mock_agent_factory():
    with patch("src.services.workflow_service.AgentFactory") as factory:
        # Mock agents
        mock_macro = MagicMock()
        mock_macro.run.return_value = "Bullish Macro View"
        
        mock_cio = MagicMock()
        mock_cio.run.return_value = "Final Weekly Report Content"
        
        factory.create_macro_agent.return_value = mock_macro
        factory.create_cio_agent.return_value = mock_cio
        factory.create_fundamental_agent.return_value = MagicMock(run=lambda x: "Fundamental Data")
        
        yield factory

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
    return wf

def test_weekly_cycle_flow(workflow, mock_transaction_service, mock_market_service, mock_planner, mock_agent_factory):
    """
    E2E-like test for the weekly report flow.
    Verifies that the workflow orchestrates the Planner and Agents correctly.
    """
    
    # Run the workflow
    report = workflow.run_weekly_cycle(user_id="test_user")
    
    # Assertions
    # 1. Data Collection
    mock_transaction_service.get_user_tickers.assert_called()
    mock_market_service.get_market_context.assert_called()
    
    # 2. Planning
    from unittest.mock import ANY
    mock_planner.decompose_goal.assert_called_with("Generate Weekly Report", ANY)
    
    # 3. Agent Execution
    # Macro Agent (for "Market Cycle Analysis")
    mock_agent_factory.create_macro_agent.assert_called()
    
    # CIO Agent (for "Report Synthesis")
    # Note: run_weekly_cycle calls create_cio_agent with mode="synthesis" for the synthesis task if mapped
    # The logic in _select_agent_for_task maps "Report Synthesis" to CIO(synthesis)
    
    # 4. Final Report
    assert "Final Weekly Report Content" in report or "Bullish Macro View" in report
    
    # 5. Storage (Memory Service)
    workflow.memory_service.store_report.assert_called_with(
        user_id="test_user",
        report_type="weekly",
        date=ANY,
        content=str(report)
    )

def test_weekly_cycle_flow_legacy_fallback(workflow, mock_transaction_service):
    """Test fallback if Planner is missing."""
    workflow.task_planner = None
    
    # Since legacy calls _legacy_weekly_cycle which returns an error string in current stub
    # or warnings.
    # We just verify it handles strict gracefully.
    
    report = workflow.run_weekly_cycle(user_id="test_user")
    assert "Error: TaskPlanner not configured" in report
