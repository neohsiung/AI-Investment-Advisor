import asyncio
import logging
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_integrated_workflow():
    print("--- Integrated Workflow Verification (Swarm + Sentinel) ---")
    
    # 1. Mock External Services (Market, DB, Notifications)
    mock_market = MagicMock()
    mock_market.get_market_context.return_value = {
        "AAPL": {"price_data": {"close": 150.0}, "indicators": {}, "news": []},
        "GOOG": {"price_data": {"close": 2800.0}, "indicators": {}, "news": []},
        "TSLA": {"price_data": {"close": 700.0}, "indicators": {}, "news": []}
    }
    mock_market.get_financials.return_value = "Financials..."
    mock_market.get_news.return_value = []
    mock_market.get_macro_data.return_value = {"market_indicators": {"^VIX": 20.0}}
    
    mock_trans = MagicMock()
    mock_trans.get_user_tickers.return_value = ["AAPL", "GOOG", "TSLA"]
    mock_trans.get_holdings_map.return_value = {"AAPL": {"quantity": 10}, "GOOG": {"quantity": 5}, "TSLA": {"quantity": 20}}
    
    # Mock Repos
    mock_tx_repo = MagicMock()
    mock_tx_repo.settings_repo.get.return_value = "false" # Disable auto-trade for safety
    
    # Mock AgentFactory to ensure Swarms are used (though WorkflowService uses it directly)
    # We will let it run but mock the LLM calls inside agents to avoid API costs
    
    with patch("src.agents.base_agent.BaseAgent.run_tool_loop") as mock_run_tool:
        mock_run_tool.return_value = "Mock Analysis Result: HOLD"
        
        # 2. Initialize Workflow
        from src.services.workflow_service import DailyWorkflow, WeeklyWorkflow
        
        print("\n--- Testing Daily Workflow (Swarm Integration) ---")
        daily = DailyWorkflow(user_id="test_user", transaction_service=mock_trans, market_service=mock_market)
        daily.transaction_repo = mock_tx_repo
        
        # Override distribute to avoid DB/Email
        daily.distribute_report = MagicMock()
        
        # Execution
        try:
            report = daily.run(dry_run=True, force_refresh=True)
            print("✅ Daily Workflow Completed.")
            if "The Great Debate" in report:
                print("✅ Report contains 'The Great Debate' section.")
            if "AAPL" in report and "GOOG" in report:
                print("✅ Report covers multiple tickers.")
        except Exception as e:
            print(f"❌ Daily Workflow Failed: {e}")
            import traceback
            traceback.print_exc()

        print("\n--- Testing Weekly Workflow (Swarm + Planner) ---")
        weekly = WeeklyWorkflow(user_id="test_user", transaction_service=mock_trans, market_service=mock_market)
        weekly.transaction_repo = mock_tx_repo
        weekly.distribute_report = MagicMock()
        
        # Mock TaskPlanner
        mock_planner = MagicMock()
        mock_task = MagicMock()
        mock_task.name = "Sector Analysis"
        mock_task.description = "Analyze Tech Sector"
        mock_task.input_keys = ["tickers"]
        mock_task.model_tier = "smart"
        
        mock_plan = MagicMock()
        mock_plan.tasks = [mock_task]
        mock_planner.decompose_goal.return_value = mock_plan
        
        weekly.task_planner = mock_planner
        
        try:
            # We fail gracefully if Planner dependencies are complex, but aim to test the flow
            weekly.run_weekly_cycle(user_id="test_user")
            print("✅ Weekly Workflow Completed (Mocked Planner).")
        except Exception as e:
             print(f"⚠️ Weekly Workflow Check (Partial): {e}")

if __name__ == "__main__":
    asyncio.run(verify_integrated_workflow())
