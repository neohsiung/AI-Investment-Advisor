import os
import sys
import asyncio
from unittest.mock import patch

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.workflow_service import WeeklyWorkflow
from src.services.task_planning_service import TaskPlanningService
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.services.transaction_service import TransactionService

class MockAgent:
    def __init__(self, name):
        self.name = name
    def run(self, context=None):
        if self.name == "CIO":
            return """# 🦁 週報：戰略復盤與記憶鞏固 (Weekly Strategy & Memory Consolidation)
日期: 2026-03-14

## 0. 產業大局觀 (Thematic & Big Picture)
> 系統追蹤的核心主題與供應鏈動態。
- **實體 AI (Physical AI)**: ["TSLA"]

## 1. 宏觀經濟與市場週期 (Macro & Market Cycle)
> 根據最新 CPI、殖利率與 VIX 數據判斷的總體經濟水位與板塊輪動策略。
【即時宏觀指標】
- VIX: 15.5
- SPY: 512.30
- 10Y-2Y Spread: -0.2

【週期分析】
MOCKED CYCLE ANALYSIS

## 2. 記憶鏈回顧 (Memory Chain Review)
> System 2 對本週 System 1 決策的審計，並糾正敘事偏離。
MOCKED DRIFT

## 3. 議會深度審議 (Council Deep Dive)
> 各代理人之間針對持倉的多層次辯論與收斂結果 (如 Fundamental vs Momentum，是否具備共識或分歧)。
### 關鍵持倉再評估 (Positions under Review)
#### AAPL
- **辯論摘要 (Debate Transcript)**: Fundamental says hold, momentum says buy.
- **Long-Term Thesis Check**:
  - 🟢 **Fundamental**: No change.
  - 🔴 **Risk & Momentum**: Low risk.
- **Verdict (共識決策)**: **Stay the Course**
"""
        return f"MOCKED RESPONSE FROM {self.name}"
    
    def polish_report(self, text):
        return text

async def main():
    user_id = "test_user_weekly"
    
    repo = AlchemyTransactionRepository()
    transaction_service = TransactionService(repository=repo)
    
    workflow = WeeklyWorkflow(user_id=user_id, transaction_service=transaction_service)
    workflow.task_planner = TaskPlanningService()
    
    with patch("src.services.workflow_service.AgentFactory") as factory:
        factory.create_macro_agent.return_value = MockAgent("Macro")
        factory.create_cio_agent.return_value = MockAgent("CIO")
        factory.create_fundamental_agent.return_value = MockAgent("Fundamental")
        factory.create_agent.return_value = MockAgent("Generic")
        
        # Patch the base workflow's pre-created CIO agent
        workflow.cio_agent = MockAgent("CIO")
        
        # In workflow service it uses self._select_agent_for_task which routes to factory
        # We also need to patch CouncilAgentAdapter for portfolio analysis
        with patch("src.services.workflow_service.CouncilAgentAdapter") as adapter:
            adapter.return_value = MockAgent("Council")
            
            print("\nRunning Weekly Cycle (MOCKED AGENTS)...")
            report = workflow.run_weekly_cycle(user_id=user_id)
            
            print("\n\n" + "="*80)
            print("====== GENERATED WEEKLY REPORT ======")
            print("="*80 + "\n")
            print(report)
            print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(main())
