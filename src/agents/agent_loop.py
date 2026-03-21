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

import json
import logging
from typing import List, Dict, Any, Tuple, Optional, Callable

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
    ):
        """
        Args:
            agent_name: Agent name for logging
            toold: McpServer instance for registered tools
            search_service: InternetSearchService for legacy SEARCH handler
        """
        self._agent_name = agent_name
        self._toold = toold
        self._search_service = search_service

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
        執行單一工具調用並回傳觀察字串。
        """
        try:
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
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return f"System: [Tool Error] {e}\n"

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
