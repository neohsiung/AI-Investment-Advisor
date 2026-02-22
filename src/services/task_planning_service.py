import json
import uuid
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from src.utils.logger import setup_logger
logger = setup_logger("TaskPlanningService")

@dataclass
class Task:
    """
    Represents a unit of work within an execution plan.
    表示執行計畫中的一個工作單元。
    """
    name: str
    description: str
    complexity: int
    model_tier: str = "smart"
    input_keys: List[str] = field(default_factory=list)
    output_keys: List[str] = field(default_factory=list)
    estimated_tokens: int = 1000

@dataclass
class ExecutionPlan:
    """
    A structured plan consisting of multiple tasks to achieve a goal.
    由多個任務組成以達成目標的結構化計畫。
    """
    plan_id: str
    goal: str
    context: Dict[str, Any]
    tasks: List[Task]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"

class TaskPlanningService:
    """
    Service responsible for decomposing high-level goals into executable tasks.
    任務規劃服務：負責將高階目標分解為可執行的任務。
    
    Acts as the 'Brain' in the 'Plan -> Execute' pattern.
    在「計畫 -> 執行」模式中充當「大腦」。
    """
    
    def __init__(self, llm_client: Any = None) -> None:
        """
        Initialize the task planning service.
        初始化任務規劃服務。
        """
        # llm_client is optional/unused for standard plan
        self.llm = llm_client
        # Use an advanced model for "Thinking" / Dynamic Planning if needed
        self.planner_model_tier = "advanced" 

    def decompose_goal(self, goal: str, context: Dict[str, Any], strategy: str = "standard_weekly") -> ExecutionPlan:
        """
        Decomposes a user goal into a structured execution plan.
        
        Args:
            strategy: 'standard_weekly' (Hardcoded Client Logic) or 'dynamic' (LLM Thought)
        """
        logger.info(f"Decomposing goal: {goal} with strategy: {strategy}")
        
        if strategy == "standard_weekly":
            return self._create_standard_weekly_plan(goal, context)
        else:
            return self._create_dynamic_plan(goal, context)

    def _create_standard_weekly_plan(self, goal: str, context: Dict[str, Any]) -> ExecutionPlan:
        """
        Client-Code defined best practice workflow. 
        This is the 'Antigravity' way: Reliable, Engineered Patterns.
        """
        tasks = [
            Task(
                name="Market Cycle Analysis",
                description="Analyze current Market Cycle (Early/Mid/Late/Recession). Focus on Liquidity (Fed), Rates (Yield Curve), and Growth (GDP). Output current 'Market_Phase' and 'Macro_Outlook'.",
                complexity=8,
                model_tier="advanced",
                input_keys=[], 
                output_keys=["Market_Phase", "Macro_Outlook"],
                estimated_tokens=6000
            ),
            Task(
                name="Sector Rotation & Swarm Insight",
                description="Identify Outperforming Sectors based on 'Market_Phase'. Aggregate 'Swarm Signals' (Momentum/Sentiment/Fundamental) to find sector-level divergences. Output 'Target_Sectors' and 'Sector_Themes'.",
                complexity=8,
                model_tier="smart",
                input_keys=["Market_Phase", "Macro_Outlook"],
                output_keys=["Target_Sectors", "Sector_Themes"],
                estimated_tokens=5000
            ),
            Task(
                name="Supply Chain & Industry Deep-Dive",
                description="For 'Target_Sectors': Analyze Upstream (Suppliers) and Downstream (Customers) logic. Review recent Vendor financial guidance to confirm trends. Output 'Supply_Chain_Trends'.",
                complexity=9,
                model_tier="advanced",
                input_keys=["Target_Sectors", "Sector_Themes"],
                output_keys=["Supply_Chain_Trends", "Industry_Outlook"],
                estimated_tokens=10000
            ),
            Task(
                name="Portfolio Deep-Dive & Health Check",
                description="Audit current holdings against 'Independent_Analysis'. Check '10-16 Stock Constraint'. Diagnose 'Swarm Signals' for each holding: Fundamental Quality vs Momentum Price Action. Recommend trim/hold.",
                complexity=9,
                model_tier="advanced",
                input_keys=["Market_Phase", "Supply_Chain_Trends", "Industry_Outlook"],
                output_keys=["Holdings_Analysis", "Gap_Analysis"],
                estimated_tokens=8000
            ),
            Task(
                name="Alpha Candidate Selection & Recommendations",
                description="Check if 'Current_Holdings_Count' < 15. IF YES: Execute 'Gap Filling Strategy'. Recommend new tickers following strict flow: 1. Macro (Cycle) -> 2. Sector (Themes) -> 3. Fundamental (Quality) -> 4. Technical (Entry). Target total 15 holdings.",
                complexity=9,
                model_tier="advanced",
                input_keys=["Holdings_Analysis", "Gap_Analysis", "Supply_Chain_Trends", "Target_Sectors"],
                output_keys=["Action_Plan", "Final_Target_Portfolio", "Buy_List"],
                estimated_tokens=8000
            ),
            Task(
                name="Report Synthesis",
                description="Synthesize all findings into a professional 'Macro-to-Micro' Investment Report (>10 mins read). explicit sections for 'Swarm Multi-Dim Insights' and 'Deep Portfolio Diagnosis'.",
                complexity=6,
                model_tier="smart",
                input_keys=["ALL"], 
                output_keys=["Final_Report"],
                estimated_tokens=12000
            )
        ]
        
        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            goal=goal,
            context=context,
            tasks=tasks
        )

    def _create_dynamic_plan(self, goal: str, context: Dict[str, Any]) -> ExecutionPlan:
        """
        Uses LLM Reasoning to generate a custom plan.
        """
        # ... (Existing LLM logic logic moved here if needed) ...
        # For now, we focus on the standard plan as the primary engine.
        pass # Placeholder for dynamic expansion


    def _parse_llm_json(self, content: str) -> Dict[str, Any]:
        """Helper to extract JSON from LLM response"""
        try:
            # Try direct parse
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON block
            import re
            match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            
            # Fallback: remove first/last lines if they are markdown code fences
            lines = content.strip().split('\n')
            if lines[0].strip().startswith("```") and lines[-1].strip().startswith("```"):
                return json.loads("\n".join(lines[1:-1]))
                
            raise ValueError(f"Could not parse JSON content: {content[:100]}...")
