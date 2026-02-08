import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import json

from src.services.task_planning_service import TaskPlanningService, ExecutionPlan, Task
from src.services.workflow_service import WeeklyWorkflow, DailyWorkflow
from src.services.memory_service import MemoryService
from src.data.memory_repository import SqliteMemoryRepository
from src.infrastructure.agent_llm_provider import AgentLLMProvider

# --- TaskPlanningService Tests ---

def test_standard_plan_structure():
    """Test that Standard Plan generates the correct 6-step Macro-to-Micro flow."""
    planner = TaskPlanningService(llm_client=None)
    context = {"tickers": ["AAPL"]}
    plan = planner.decompose_goal("Weekly Report", context, strategy="standard_weekly")
    
    assert isinstance(plan, ExecutionPlan)
    assert len(plan.tasks) == 6
    
    task_names = [t.name for t in plan.tasks]
    assert "Market Cycle Analysis" in task_names
    assert "Supply Chain & Industry Deep-Dive" in task_names
    assert "Report Synthesis" in task_names
    
    # Check Context Linking
    sector_task = next(t for t in plan.tasks if "Sector" in t.name)
    assert "Market_Phase" in sector_task.input_keys

# --- WorkflowService Integration Tests ---

@pytest.fixture
def mock_workflow_deps():
    """Fixture to mock Planner, Memory, and Agents for Workflow."""
    planner = TaskPlanningService(llm_client=None)
    
    # Mock Memory Service
    mem_repo = MagicMock()
    agent_provider = MagicMock()
    memory_service = MemoryService(mem_repo, agent_provider)
    
    return planner, memory_service

@patch('src.agents.factory.AgentFactory.create_macro_agent')
@patch('src.agents.factory.AgentFactory.create_cio_agent')
@patch('src.agents.factory.AgentFactory.create_fundamental_agent')
def test_weekly_workflow_execution(mock_fund, mock_cio, mock_macro, mock_workflow_deps):
    """Test full Weekly Workflow execution with mocked agents."""
    planner, memory_service = mock_workflow_deps
    
    # Setup Mock Agent Responses
    mock_macro.return_value.run.return_value = "Macro: Growth"
    mock_cio.return_value.run.return_value = "CIO: Buy Tech"
    # Mock polish_report
    mock_cio.return_value.polish_report.side_effect = lambda x: x
    
    mock_fund.return_value.run.return_value = "Fund: Strong Cashflow"
    
    workflow = WeeklyWorkflow(user_id="test_user")
    workflow.task_planner = planner
    workflow.memory_service = memory_service
    
    # Mock Context
    workflow.context = {"tickers": ["NVDA"], "market_data": {}}
    workflow.market_service = MagicMock() # Mock market service calls if any
    workflow.transaction_service = MagicMock()
    workflow.transaction_service.get_holdings_map.return_value = {}
    workflow.performance_service = MagicMock()
    
    # Run
    report = workflow.run_weekly_cycle(user_id="test_user")
    
    # Assertions
    assert "CIO: Buy Tech" in report or "Macro: Growth" in report or "Fund" in report
    # Check that agents were called
    assert mock_macro.called
    assert mock_cio.called
    # Check that Memory Store was called
    memory_service.repo.save_report.assert_called()

# --- Memory Consistency Tests ---

def test_daily_consistency_warning():
    """Test that contradictory views trigger a warning."""
    mem_repo = MagicMock()
    agent_provider = MagicMock()
    
    # Mock Repository to return prior reports (Essential for get_context to work)
    from src.services.memory_service import ReportMemoryItem
    mem_repo.get_recent_reports.return_value = [
        ReportMemoryItem(
            user_id="consistency_user",
            report_type="daily",
            report_date="2023-01-01",
            full_content="Old Bullish View",
            compressed_summary="Bullish"
        )
    ]
    
    # Mock Agent Provider to return a contradiction JSON
    agent_provider.check_contradictions.return_value = ["Contradiction: Bull vs Bear"]
    
    memory_service = MemoryService(mem_repo, agent_provider)
    
    # Mock Workflow
    workflow = DailyWorkflow(user_id="consistency_user")
    workflow.memory_service = memory_service
    workflow.context = {"tickers": ["S"]}
    
    # Mock Dependent Calls
    workflow.market_service = MagicMock()
    workflow.market_service.get_macro_data.return_value = {}
    workflow.transaction_service = MagicMock()
    workflow.transaction_service.get_holdings_map.return_value = {}
    workflow.performance_service = MagicMock()
    
    with patch('src.agents.factory.AgentFactory.create_macro_agent') as mock_macro, \
         patch('src.agents.factory.AgentFactory.create_cio_agent') as mock_cio:
        
        mock_macro.return_value.run.return_value = "Old Macro"
        mock_cio.return_value.run.return_value = "Final Report with Warning"
        
        # We need to ensure 'ticker_reports' is populated or logic inside synthesize works
        workflow.context['ticker_reports'] = {"S": {"momentum": "UP"}}
        
        workflow.synthesize_results()
        
        # Check that check_contradictions was called
        agent_provider.check_contradictions.assert_called()
        
        # Check that CIO agent received the warning in context
        call_args = mock_cio.return_value.run.call_args
        context_arg = call_args[0][0]
        assert "consistency_constraints" in context_arg
        assert "Contradiction: Bull vs Bear" in context_arg["consistency_constraints"]
