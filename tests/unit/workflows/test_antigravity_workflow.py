import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import json

from src.services.task_planning_service import TaskPlanningService, ExecutionPlan, Task
from src.services.workflow_service import WeeklyWorkflow, DailyWorkflow
from src.services.memory_service import MemoryService
from src.repositories.memory_repository import AlchemyMemoryRepository
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
    agent_provider.summarize = AsyncMock(return_value="Mocked Summary")
    memory_service = MemoryService(repository=mem_repo, llm_provider=agent_provider)
    
    return planner, memory_service

@pytest.mark.asyncio
@patch('src.services.workflow_service.BaseWorkflow._call_agent_llm', new_callable=AsyncMock)
async def test_weekly_workflow_execution(mock_llm, mock_workflow_deps):
    """Test full Weekly Workflow execution with mocked agents."""
    planner, memory_service = mock_workflow_deps
    
    # Setup Mock Agent Responses
    def side_effect(agent_name, *args, **kwargs):
        if agent_name == "Macro": return "Macro: Growth"
        if agent_name == "CIO": return "CIO: Buy Tech"
        if agent_name == "Fundamental": return "Fund: Strong Cashflow"
        return "Mock Response"
    mock_llm.side_effect = side_effect
    
    workflow = WeeklyWorkflow(user_id="test_user")
    workflow.task_planner = planner
    workflow.memory_service = memory_service
    
    # Mock Context
    workflow.context = {"tickers": ["NVDA"], "market_data": {}}
    workflow.market_service = MagicMock() 
    workflow.transaction_service = MagicMock()
    workflow.transaction_service.get_holdings_map.return_value = {}
    workflow.performance_service = MagicMock()
    
    # Run
    report = await workflow.run_weekly_cycle(user_id="test_user")
    
    # Assertions
    assert "CIO: Buy Tech" in report or "Macro: Growth" in report or "Fund" in report
    # Check that agents were called
    assert mock_llm.called
    # Check that Memory Store was called
    memory_service.repo.save_report.assert_called()

# --- Memory Consistency Tests ---

@pytest.mark.asyncio
@patch('src.services.workflow_service.AgentLLMProvider')
@patch('src.services.workflow_service.AlchemyMemoryRepository')
@patch('src.services.workflow_service.AlchemyTransactionRepository')
@patch('src.services.workflow_service.TransactionService')
@patch('src.services.workflow_service.MarketDataService')
@patch('src.services.workflow_service.BaseWorkflow._call_agent_llm', new_callable=AsyncMock)
@patch('src.services.broker_factory.BrokerFactory')
@patch('src.infrastructure.risk_manager.RiskManager')
@patch('src.infrastructure.risk_manager.AlchemySettingsRepository')
@patch('src.services.workflow_service.PerformanceService')
async def test_daily_consistency_warning(MockPerformanceService, MockRiskSettings, MockRiskManager, MockBrokerFactory, mock_llm, MockMarket, MockTransService, MockTransRepo, MockMemRepo, MockLLMProvider):
    """Test that contradictory views trigger a warning."""
    mem_repo = MagicMock()
    agent_provider = MagicMock()
    agent_provider.summarize = AsyncMock(return_value="Mocked Summary")
    
    # Mock Repository to return prior reports
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
    
    # Mock Agent Provider
    agent_provider.check_contradictions = AsyncMock(return_value=["Contradiction: Bull vs Bear"])
    
    memory_service = MemoryService(mem_repo, agent_provider)
    
    # Validate Mocks Setup
    def side_effect(agent_name, *args, **kwargs):
        if agent_name == "Macro": return "Old Macro"
        if agent_name == "CIO": return "Final Report with Warning"
        return "Mock Response"
    mock_llm.side_effect = side_effect
    
    mock_broker = MagicMock()
    mock_broker.get_name.return_value = "MockBroker"
    mock_broker.get_account.return_value = MagicMock(total_equity=10000, available_cash=5000)
    MockBrokerFactory.get_broker.return_value = mock_broker
    
    mock_risk = MagicMock()
    mock_risk.check_constraints.return_value = True
    MockRiskManager.return_value = mock_risk

    # Instantiate Workflow (now under patch)
    workflow = DailyWorkflow(user_id="consistency_user")
    workflow.memory_service = memory_service
    
    # Mock Context
    workflow.context = {"tickers": ["S"]}
    workflow.context['ticker_reports'] = {"S": {"momentum": "UP"}}
    
    await workflow.synthesize_results()
    
    # Check that check_contradictions was called
    agent_provider.check_contradictions.assert_called()
    
    # Check that CIO agent received the warning in context
    # It should be the last call or one of the calls to mock_llm where agent_name="CIO"
    cio_call = [call for call in mock_llm.call_args_list if call.args[0] == "CIO"][-1]
    context_arg = cio_call.args[1]
    assert "consistency_constraints" in context_arg
    assert "Contradiction: Bull vs Bear" in context_arg["consistency_constraints"]
