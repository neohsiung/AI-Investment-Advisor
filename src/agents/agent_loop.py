"""
Agent ReAct Loop — Agent Layer.
Agent ReAct 迴圈 — Agent 層。

Implements the standardized ReAct (Reason + Act) loop:
  - LLM call → Parse tool call → Execute tool → Inject observation → Loop

Extracted from BaseAgent.run_tool_loop / _parse_tool_call (Phase 2).

遵循規範:
  - 規範一 (Clean Architecture): 單一職責，僅負責 ReAct 執行迴圈
  - 規範十 (MCP 整合): 支援 MCP tool 與 Legacy SEARCH
  - 規範四 (模組化設計): 獨立可單元測試
"""

from typing import List, Dict, Any, Tuple, Optional, Callable
import json
import logging
from datetime import datetime
from dataclasses import replace
from src.domain.interfaces import Message
from src.prompts.reflection_prompt import ReflectionPrompt
from src.services.settings_service import SettingsService
from src.services.token_logger_service import TokenLoggerService
from src.services.evolution_metrics import EvolutionMetrics
from src.services.reflection_manager import ReflectionManager

logger = logging.getLogger(__name__)


class AgentLoop:
    """
    ReAct-style execution loop for agent tool use.
    Agent 工具使用的 ReAct 風格執行迴圈。
    """

    def __init__(
        self,
        agent_name: str = "Agent",
        toold=None,
        search_service=None,
        user_id: str = "system"
    ):
        """
        Args:
            agent_name: Agent name for logging
            toold: McpServer instance for registered tools
            search_service: InternetSearchService for legacy SEARCH handler
            user_id: For budget-aware reflection
        """
        self._agent_name = agent_name
        self._toold = toold
        self._search_service = search_service
        self._user_id = user_id

    def execute(
        self,
        messages: List[Dict[str, str]],
        call_llm_fn: Callable,
        check_context_fn: Callable = None,
        flush_fn: Callable = None,
        max_turns: int = 3,
    ) -> str:
        """
        Execute the ReAct loop.
        執行 ReAct 迴圈。

        Args:
            messages: Initial messages [system, user]
            call_llm_fn: Callable to invoke LLM
            check_context_fn: Optional context window check function
            flush_fn: Optional context flush function
            max_turns: Maximum tool-use turns

        Returns:
            Final LLM response text
        """
        response_text = ""

        for turn in range(max_turns):
            # [Context Guard]
            if check_context_fn and check_context_fn(messages):
                if flush_fn:
                    flush_fn(messages)

            response_text = call_llm_fn(messages)

            # Tool Parsing
            tool_call = self.parse_tool_call(response_text)

            if tool_call:
                name, args = tool_call
                logger.info(f"Agent requested tool: {name} with {args}")
                messages.append({"role": "assistant", "content": response_text})

                observation = self._execute_tool(name, args)
                messages.append({"role": "user", "content": observation})
                # Loop continues
            else:
                return response_text

        return response_text

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """
        Execute a single tool call and return the observation string.
        [Phase 6] Self-healing skill execution with reflection.
        """
        try:
            return self._run_tool_logic(name, args)
        except Exception as e:
            logger.warning(f"AgentLoop: Primary execution failed for tool '{name}': {e}. Starting Reflection.")
            
            # 1. Reflect on the failure
            reflection = self._reflect_on_error(name, args, str(e))
            
            # 2. Act based on reflection
            if reflection and reflection.get("recommended_action") == "retry":
                corrected_args = reflection.get("corrected_args", {})
                logger.info(f"AgentLoop: Reflection suggested RETRY for tool '{name}' with args: {corrected_args}")
                try:
                    return self._run_tool_logic(name, corrected_args)
                except Exception as retry_e:
                    logger.error(f"AgentLoop: Retry failed for tool '{name}': {retry_e}")
                    return f"System: [Tool '{name}' Reflection Retry Failed] {retry_e}\n"
            
            # Cannot self-heal or reflection suggests failing
            logger.error(f"AgentLoop: Tool '{name}' failed and reflection could not recover: {e}")
            return f"System: [Tool '{name}' Error] {e}\n"

    def _run_tool_logic(self, name: str, args: Dict[str, Any]) -> str:
        """Core tool invocation logic."""
        result = ""
        if name == "SEARCH":
            # Legacy Search Handler
            result = self._execute_search(args)
        elif self._toold and name in self._toold.tools:
            # MCP Tool Call
            raw_res = self._toold.call_tool(name, args)
            result = json.dumps(raw_res, ensure_ascii=False)
        else:
            result = f"Error: Tool '{name}' not found."

        return f"System: [Tool '{name}' Output]\n{result}\n"

    def _reflect_on_error(self, tool_name: str, args: Any, error: str) -> Optional[Dict[str, Any]]:
        """
        Synchronous reflection call with budget awareness and observability. [Phase 7]
        Delegates to ReflectionManager to avoid code duplication.
        """
        manager = ReflectionManager(user_id=self._user_id)
        return manager.reflect_on_error(
            tool_name=tool_name,
            args=args,
            error=str(error),
            agent_name=self._agent_name
        )

    def _execute_search(self, args: Dict[str, Any]) -> str:
        """
        Execute legacy SEARCH tool call.
        執行舊版 SEARCH 工具調用。
        """
        if not self._search_service:
            return "Error: Search service not available."

        q = args.get("query", str(args))
        res_list = self._search_service.search_financial_context(q, max_results=3)

        if res_list:
            result = ""
            for r in res_list:
                result += (
                    f"- {r.get('title')}: {r.get('snippet')} ({r.get('link')})\n"
                )
            return result
        return "No results found."

    @staticmethod
    def parse_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Heuristic parsing for tool calls.
        啟發式工具調用解析。

        Supported formats:
        1. SEARCH: "query"
        2. CALL: tool_name({"arg": "val"})

        Returns:
            Tuple of (tool_name, args_dict) or None
        """
        for line in text.splitlines():
            if "SEARCH:" in line:
                parts = line.split("SEARCH:", 1)
                if len(parts) > 1:
                    query = parts[1].strip().strip('"').strip("'")
                    return ("SEARCH", {"query": query})

            if line.strip().startswith("CALL:"):
                content = line.strip().replace("CALL:", "").strip()
                if "(" in content and content.endswith(")"):
                    name = content.split("(", 1)[0].strip()
                    args_str = content.split("(", 1)[1][:-1]
                    try:
                        args = json.loads(args_str)
                        return (name, args)
                    except json.JSONDecodeError:
                        return (name, {"arg": args_str})
        return None
