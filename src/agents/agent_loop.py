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
import asyncio
import re
from typing import List, Dict, Any, Tuple, Optional, Callable
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

    async def execute(
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
        
        # v20.3: Start initial thinking status [Phase 20]
        await self._broadcast_status(f"🤖 {self._agent_name} 正在思考策略...")

        for turn in range(max_turns):
            # [Context Guard]
            if check_context_fn and check_context_fn(messages):
                if flush_fn:
                    flush_fn(messages)

            response_text = call_llm_fn(messages)

            # Tool Parsing - Now supports multiple [Phase 12]
            tool_calls = self.parse_tool_call(response_text)

            if tool_calls:
                logger.info(f"Agent requested {len(tool_calls)} tools in parallel: {[t[0] for t in tool_calls]}")
                messages.append({"role": "assistant", "content": response_text})

                # Parallel Execution [Phase 12]
                tasks = [self._execute_tool_async(name, args) for name, args in tool_calls]
                results = await asyncio.gather(*tasks)
                
                # Format feedback for LLM
                observation = "\n".join([f"Observation {i+1} ({t[0]}): {r}" for i, (t, r) in enumerate(zip(tool_calls, results))])
                messages.append({"role": "user", "content": observation})
            else:
                # No more tool calls, exit loop
                break

        return response_text

    async def _execute_tool_async(self, name: str, args: Dict[str, Any]) -> str:
        """Async execution of a tool with reflection/self-healing logic."""
        from opentelemetry import trace
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span(f"Agent.{self._agent_name}.Tool.{name}") as span:
            span.set_attribute("tool.name", name)
            span.set_attribute("tool.args", json.dumps(args, ensure_ascii=False))
            
            # v20.3: Broadcast tool start status [Phase 20]
            status_msg = self._get_tool_status_msg(name, args)
            await self._broadcast_status(status_msg)

            try:
                result = await self._run_tool_logic_async(name, args)
                span.set_attribute("tool.status", "success")
                return result
            except Exception as e:
                span.set_attribute("tool.status", "failure")
                span.record_exception(e)
                logger.warning(f"AgentLoop: Primary execution failed for tool '{name}': {e}. Starting Reflection.")
                
                # 1. Reflect on the failure (kept sync for now as it's pure logic)
                reflection = self._reflect_on_error(name, args, str(e))
                
                # 2. Act based on reflection
                if reflection and reflection.get("recommended_action") == "retry":
                    corrected_args = reflection.get("corrected_args", {})
                    logger.info(f"AgentLoop: Reflection suggested RETRY for tool '{name}' with args: {corrected_args}")
                    span.add_event("Tool_Retry", attributes={"corrected_args": json.dumps(corrected_args)})
                    try:
                        return await self._run_tool_logic_async(name, corrected_args)
                    except Exception as retry_e:
                        logger.error(f"AgentLoop: Retry failed for tool '{name}': {retry_e}")
                        return f"System: [Tool '{name}' Reflection Retry Failed] {retry_e}\n"
                
                # Cannot self-heal or reflection suggests failing
                logger.error(f"AgentLoop: Tool '{name}' failed and reflection could not recover: {e}")
                return f"System: [Tool '{name}' Error] {e}\n"

    async def _run_tool_logic_async(self, name: str, args: Dict[str, Any]) -> str:
        """Core async tool invocation logic."""
        
        # [Phase 9] Log Tool Execution to Pulse
        try:
            from src.repositories.pulse_repository import AsyncPulseRepository
            pulse_repo = AsyncPulseRepository()
            await pulse_repo.log_pulse(self._user_id, self._agent_name, name, args)
        except Exception as e:
            logger.warning(f"AgentLoop: Failed to log pulse: {e}")

        # T10.2: Handle Legacy SEARCH
        if name == "SEARCH":
            if self._search_service:
                query = args.get("query", "")
                return await self._execute_search_async(query)
            return "Error: Search service not initialized."

        # T10.1: MCP Integration
        if self._toold:
            try:
                return await self._toold.call_tool(name, args)
            except Exception as e:
                raise e # Throw for reflection handler
        
        return f"Error: Tool '{name}' not found."

    def _reflect_on_error(self, tool_name: str, args: Dict[str, Any], error: str) -> Dict[str, Any]:
        """Synchronous reflection logic (Task 12.2)."""
        manager = ReflectionManager()
        return manager.reflect(self._agent_name, tool_name, args, error)

    async def _execute_search_async(self, query: str) -> str:
        """Helper to run search asynchronously."""
        res_list = await self._search_service.search_financial_context(query)
        if res_list:
            result = ""
            for r in res_list:
                result += (
                    f"- {r.get('title')}: {r.get('snippet')} ({r.get('link')})\n"
                )
            return result
        return "No results found."

    @staticmethod
    def parse_tool_call(text: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Heuristic parsing for multiple tool calls in a single turn. [Phase 12]
        Supporting both SEARCH: and CALL: formats.
        """
        tool_calls = []
        
        # 1. Extract SEARCH: calls
        search_matches = re.finditer(r"SEARCH:\s*(.+)", text)
        for match in search_matches:
            query = match.group(1).strip().strip('"').strip("'")
            tool_calls.append(("SEARCH", {"query": query}))
            
        # 2. Extract CALL: calls
        call_matches = re.finditer(r"CALL:\s*(\w+)\s*\((.*?)\)", text, re.DOTALL)
        for match in call_matches:
            name = match.group(1).strip()
            args_str = match.group(2).strip()
            
            # Simple heuristic to find the first balanced JSON block if it exists
            # v12.1: Robust extraction for complex multi-tool scenarios
            try:
                # If there's a JSON block, extract it
                if "{" in args_str:
                    # Find balanced braces
                    start = args_str.find("{")
                    # We assume the last brace in this segment is the end
                    end = args_str.rfind("}")
                    if end > start:
                        args = json.loads(args_str[start:end+1])
                        tool_calls.append((name, args))
                else:
                    # Not a JSON block, skip or handle as simple string if needed
                    pass
            except Exception as e:
                logger.warning(f"AgentLoop: Failed to parse tool args for '{name}': {e}")
        
        return tool_calls

    # --- v20.3: PWA UX Helper Methods ---
    async def _broadcast_status(self, message: str):
        """Broadcasts a status update to the user via WebSocket."""
        try:
            from src.services.socket_manager import socket_manager
            await socket_manager.broadcast_to_user(self._user_id, {
                "type": "AGENT_STATUS",
                "payload": {
                    "agent": self._agent_name,
                    "message": message,
                    "timestamp": datetime.now().isoformat()
                }
            })
        except Exception as e:
            logger.debug(f"AgentLoop: Failed to broadcast status (likely no WS connection): {e}")

    def _get_tool_status_msg(self, name: str, args: Dict[str, Any]) -> str:
        """Generates a human-friendly status message based on the tool being used."""
        msg_map = {
            "SEARCH": f"🔍 正在搜尋市場新聞 ({args.get('query', '一般資訊')})...",
            "get_history": f"📈 正在調取歷史行情數據 ({args.get('ticker', 'N/A')})...",
            "get_current_price": f"💰 正在獲取即時報價 ({args.get('ticker', 'N/A')})...",
            "get_company_news": f"📰 正在整理公司最新動態 ({args.get('ticker', 'N/A')})...",
            "evaluate_and_execute_trade": f"💸 正在準備下單執行指令 ({args.get('ticker', 'N/A')})...",
            "get_watchlist": "📋 正在獲取您的關注清單...",
            "calculate_risk": f"⚖️ 正在對 {args.get('ticker', 'N/A')} 進行風險權重評估..."
        }
        return msg_map.get(name, f"🛠️ {self._agent_name} 正在執行工具 '{name}'...")
