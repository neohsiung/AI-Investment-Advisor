import json
import logging
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.domain.interfaces import Message, LLMConfig
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
from src.utils.async_utils import to_thread

logger = logging.getLogger(__name__)

@dataclass
class SubTask:
    """
    Represents a single atomic task to be executed by a specific agent role.
    表示由特定 Agent 角色執行的單個原子任務。
    """
    id: str
    agent_role: str
    task_description: str
    depends_on: List[str] = field(default_factory=list)
    priority: int = 5
    result: Optional[str] = None

class ConversationTaskDecomposer:
    """
    Decomposes complex user messages into a set of SubTasks.
    將複雜的使用者訊息拆解為一組 SubTask。
    """

    DECOMPOSITION_PROMPT = """
You are the **Lead Orchestrator** of an AI Investment Committee.
Your job is to analyze a user's request and decompose it into atomic tasks for specialized agents.

### Specialized Agents Available:
1. **Momentum (momentum)**: Technical analysis, RSI, MACD, price action, trend following.
2. **Fundamental (fundamental)**: Valuation, earnings, balance sheet, growth potential.
3. **Sentiment (sentiment)**: Social media buzz, news sentiment, retail retail interest.
4. **Macro (macro)**: Interest rates, inflation, VIX, yield curves, global economic events.
5. **Risk (risk)**: Drawdown analysis, position sizing limits, stop-loss strategy.
6. **CIO (cio)**: Executive summary, final arbitration, and strategy synthesis.

### Rules for Decomposition:
- **Atomicity**: Each task should focus on one specific aspect.
- **Dependencies**: If Task B needs the result of Task A, add "Task A ID" to Task B's `depends_on`.
- **Simplification**: If the request is simple (e.g., "What is NVDA price?"), return a single task or an empty list if it can be handled by a basic router.
- **Output Format**: You MUST return a JSON list of objects matching the `SubTask` structure.

### SubTask Structure:
```json
[
  {{
    "id": "task_1",
    "agent_role": "momentum",
    "task_description": "Analyze NVDA relative strength and trend stability.",
    "depends_on": []
  }},
  {{
    "id": "task_2",
    "agent_role": "cio",
    "task_description": "Synthesize momentum findings into a buy/hold recommendation.",
    "depends_on": ["task_1"]
  }}
]
```

User Request: {user_message}
Context: {context_summary}

Return ONLY the JSON list.
"""

    def __init__(self, user_id: str, tier: str = "smart"):
        self.user_id = user_id
        self.tier = tier
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            provider = os.getenv("AI_PROVIDER", "Google Gemini")
            self._llm = LLMGatewayFactory.create(provider)
        return self._llm

    def _get_config(self) -> LLMConfig:
        model = os.getenv("AI_MODEL_SMART", "gemini-1.5-pro")
        return LLMConfig(
            provider=os.getenv("AI_PROVIDER", "Google Gemini"),
            model=model,
            api_key=os.getenv("API_KEY", ""),
            base_url=os.getenv("BASE_URL", ""),
            temperature=0.1,
        )

    async def decompose(self, user_message: str, history: str = "") -> List[SubTask]:
        """
        Analyze user message and return a list of SubTasks.
        """
        llm = self._get_llm()
        
        prompt = self.DECOMPOSITION_PROMPT.format(
            user_message=user_message,
            context_summary=f"History: {history}"
        )

        try:
            # chat() is synchronous, wrap it in to_thread
            content = await to_thread(
                llm.chat,
                messages=[Message(role="user", content=prompt)],
                config=self._get_config()
            )
            
            # Handle potential markdown blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            if isinstance(data, dict) and "tasks" in data:
                data = data["tasks"]
            
            if not isinstance(data, list):
                logger.warning(f"Unexpected decomposition format: {data}")
                return []

            sub_tasks = []
            for item in data:
                sub_tasks.append(SubTask(
                    id=item.get("id", f"task_{len(sub_tasks)}"),
                    agent_role=item.get("agent_role", "rio"),
                    task_description=item.get("task_description", ""),
                    depends_on=item.get("depends_on", []),
                    priority=item.get("priority", 5)
                ))
            
            logger.info(f"Decomposed request into {len(sub_tasks)} tasks")
            return sub_tasks

        except Exception as e:
            logger.error(f"Failed to decompose request: {e}")
            return []
