"""
Context Assembly Engine — Agent Layer.
上下文組裝引擎 — Agent 層。

Responsible for constructing the final system prompt by injecting:
  - Current timestamp
  - Tool definitions (MCP JSON + Skills XML)
  - Dynamic memory (HybridMemory / contextual retrieval)
  - Jinja2 template rendering

Extracted from BaseAgent.render_system_prompt (Phase 2).

遵循規範:
  - 規範一 (Clean Architecture): 單一職責，僅負責上下文組裝
  - 規範五 (Context Assembly Engine): 精準上下文提取
  - 規範四 (模組化設計): 獨立可單元測試
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from jinja2 import Template

logger = logging.getLogger(__name__)


class ContextAssembler:
    """
    Assembles the final system prompt from template, tools, skills, and memory.
    從模板、工具、技能與記憶組裝最終系統提示詞。
    """

    def __init__(self, skill_loader=None, memory=None, toold=None):
        """
        Args:
            skill_loader: SkillLoader instance for skill XML generation
            memory: HybridMemory instance for contextual retrieval
            toold: McpServer instance for MCP tool definitions
        """
        self._skill_loader = skill_loader
        self._memory = memory
        self._toold = toold

    def render(self, system_prompt: str, context: Any) -> str:
        """
        Render the system prompt with injected context.
        使用注入的上下文渲染系統提示詞。

        Args:
            system_prompt: Raw Jinja2 template string
            context: User context (dict or str)

        Returns:
            Fully rendered system prompt with tools, skills, time, and memory
        """
        try:
            # 1. Inject Time Context
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 2. Inject Tool Definitions (MCP JSON + Skills XML)
            mcp_tools_json = json.dumps(
                self._toold.list_tools(), indent=2
            ) if self._toold else "[]"

            skills_xml = (
                self._skill_loader.get_skill_registry_xml()
                if self._skill_loader else ""
            )

            # 3. Inject Dynamic Memory
            memory_context_str = self._build_memory_context(context)

            # 4. Merge into template variables
            context_dict = context if isinstance(context, dict) else {}
            context_with_tools = context_dict.copy()
            context_with_tools["tools"] = mcp_tools_json
            context_with_tools["skills_xml"] = skills_xml
            context_with_tools["current_time"] = current_time
            context_with_tools["memory_context"] = memory_context_str

            template = Template(system_prompt)
            return template.render(**context_with_tools)
        except Exception as e:
            logger.error(f"Error rendering system prompt: {e}")
            return system_prompt

    def _build_memory_context(self, context: Any) -> str:
        """
        Build memory context string from explicit historical context or memory search.
        從明確歷史上下文或記憶搜索中構建記憶上下文字串。
        """
        memory_context_str = ""
        context_dict = context if isinstance(context, dict) else {}

        # Explicit Historical Context (from CouncilService)
        if "historical_context" in context_dict:
            memory_context_str += (
                f"\n[Historical Context]:\n{context_dict['historical_context']}\n"
            )

        # Topic-based memory retrieval
        topic = context_dict.get("topic")
        if topic and "historical_context" not in context_dict and self._memory:
            memories = self._memory.search(topic, query_vector=None, limit=3)
            if memories:
                memory_context_str += "\n".join(
                    [f"- {m['content']} (Score: {m['score']:.2f})" for m in memories]
                )

        return memory_context_str

    @staticmethod
    def render_user_context(context: Any) -> str:
        """
        Convert user context to a string suitable for LLM user message.
        將用戶上下文轉換為適合 LLM 用戶訊息的字串。
        """
        if isinstance(context, str):
            return context
        return json.dumps(context, indent=2, ensure_ascii=False)
