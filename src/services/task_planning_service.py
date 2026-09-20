import json
import uuid
import re
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
    # Which agent executes this task. Set explicitly by plan files; left None by
    # the LLM planner, which is why workflow_service still keeps a name-based
    # fallback for that path.
    # 由計畫檔明確指定；LLM 動態規劃不會設定，故仍保留以名稱推斷的後備路徑。
    agent: Optional[str] = None

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
        The engineered weekly research plan, loaded from
        config/workflows/weekly_plan.yaml.

        This was a literal list of six `Task(...)` dataclasses in this method.
        Reordering the research, moving a stage to a cheaper tier, or changing
        which agent writes a section all meant editing Python and redeploying —
        for values that are pure configuration.

        Falls back to the built-in plan if the file is missing or malformed: a
        broken edit must not take the weekly report offline entirely.

        原本是本方法中六個字面 Task 的清單；調整順序、tier 或執行代理都得改程式。
        檔案缺失或格式錯誤時退回內建計畫，避免一次錯誤編輯讓週報完全停擺。
        """
        tasks = self._load_weekly_tasks()
        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            goal=goal,
            context=context,
            tasks=tasks,
        )

    def _load_weekly_tasks(self) -> List[Task]:
        """Parse config/workflows/weekly_plan.yaml into Task objects."""
        try:
            import yaml

            from src.infrastructure.workflow.loader import workflows_dir

            # config/plans/, not config/workflows/. The two directories hold
            # different schemas: workflows/ are DAG graphs (`nodes:` with
            # input/output keys, executed by DAGExecutor), plans/ are sequential
            # Task lists (`tasks:` with model_tier and complexity, executed by the
            # Task/ExecutionPlan pipeline). Sharing one directory made the DAG
            # loader try to parse this file and fail.
            # 兩者 schema 不同：workflows/ 是 DAG 圖，plans/ 是循序任務清單。
            # 放在同一個目錄會讓 DAG loader 嘗試解析本檔而失敗。
            path = workflows_dir().parent / "plans" / "weekly_plan.yaml"
            raw = yaml.safe_load(path.read_text()) or {}
            entries = raw.get("tasks") or []
            if not entries:
                raise ValueError("`tasks:` is empty")

            tasks = []
            for e in entries:
                name = e.get("name")
                if not name:
                    raise ValueError("a task is missing `name:`")
                tasks.append(Task(
                    name=name,
                    description=e.get("description", ""),
                    complexity=int(e.get("complexity", 5)),
                    model_tier=e.get("model_tier", "smart"),
                    input_keys=list(e.get("inputs") or []),
                    output_keys=list(e.get("outputs") or []),
                    estimated_tokens=int(e.get("estimated_tokens", 1000)),
                    agent=e.get("agent"),
                ))
            logger.info("Loaded weekly plan from YAML: %d tasks", len(tasks))
            return tasks
        except Exception as exc:
            logger.error(
                "Could not load config/workflows/weekly_plan.yaml (%s) — "
                "falling back to the built-in plan.", exc,
            )
            return self._builtin_weekly_tasks()

    def _builtin_weekly_tasks(self) -> List[Task]:
        """
        Minimal in-code fallback. Deliberately short: it exists so a malformed
        YAML edit degrades to a working-but-basic weekly report rather than to
        nothing, not as a second copy of the full plan to keep in sync.
        刻意精簡的後備計畫：目的是讓錯誤編輯降級為「可用但簡化」的週報，
        而不是維護第二份完整計畫。
        """
        return [
            Task(
                name="Market Cycle Analysis",
                description="Analyze the current market cycle: liquidity, rates and growth.",
                complexity=8, model_tier="advanced", input_keys=[],
                output_keys=["Market_Phase", "Macro_Outlook"],
                estimated_tokens=6000, agent="Macro",
            ),
            Task(
                name="Report Synthesis",
                description="Synthesize the findings into a macro-to-micro investment report.",
                complexity=6, model_tier="smart", input_keys=["ALL"],
                output_keys=["Final_Report"], estimated_tokens=12000, agent="CIO",
            ),
        ]

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
