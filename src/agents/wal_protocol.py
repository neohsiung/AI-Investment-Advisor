"""
WAL (Write-Ahead Logging) Protocol — Agent Layer.
WAL 協議 — Agent 層。

Manages context window budgeting and checkpoint/flush logic:
  - Token estimation
  - Context window overflow detection
  - Silent flush: summarize → persist to STATE.md → truncate history

Extracted from BaseAgent._check_context_window / _perform_silent_flush (Phase 2).

遵循規範:
  - 規範一 (Clean Architecture): 單一職責，僅負責上下文視窗管理
  - 規範六 (Context Guard): 主動偵測上下文即將溢出
  - 規範四 (模組化設計): 獨立可單元測試
"""

import os
import re
import logging
from typing import List, Dict, Callable, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class WalProtocol:
    """
    Context window management with Write-Ahead Logging.
    具備預寫式日誌的上下文視窗管理。
    """

    def __init__(
        self,
        workspace_path: str = "",
        agent_name: str = "Agent",
        redact_fn: Optional[Callable[[str], str]] = None,
    ):
        """
        Args:
            workspace_path: Path to agent workspace for STATE.md persistence
            agent_name: Agent name for logging
            redact_fn: Optional function to redact secrets from WAL state
        """
        self._workspace_path = workspace_path
        self._agent_name = agent_name
        self._redact_fn = redact_fn or (lambda x: x)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count (approx. 4 chars per token).
        估算 Token 數量（約每 4 字元一個 Token）。
        """
        return len(text) // 4

    def check_context_window(
        self,
        messages: List[Dict[str, str]],
        reserve_floor: int = 4000,
        max_tokens: int = 32000,
    ) -> bool:
        """
        Check if the current context approaches the token limit.
        如果上下文超過安全線，回傳 True 觸發 Flush 訊號。

        Args:
            messages: Current message history
            reserve_floor: Reserved token budget for response
            max_tokens: Maximum context window size

        Returns:
            True if flush is needed
        """
        total_tokens = sum(
            self.estimate_tokens(msg.get("content", "")) for msg in messages
        )
        if total_tokens > (max_tokens - reserve_floor):
            logger.warning(
                f"Context Window approaching limit! Tokens: {total_tokens} "
                f"(Reserve: {reserve_floor})"
            )
            return True
        return False

    async def perform_silent_flush(
        self,
        messages: List[Dict[str, str]],
        call_llm_fn: Callable,
    ) -> None:
        """
        WAL Protocol: Write state context out and truncate history.
        將當前思考軌跡壓縮，寫入狀態日誌，避免斷片。

        Args:
            messages: Message list (mutated in-place for truncation)
            call_llm_fn: Callable to invoke LLM for summarization
        """
        logger.info(f"[{self._agent_name}] Initiating Silent Pre-Compaction Flush & WAL")

        # 1. Ask LLM to summarize and generate a WAL checkpoint
        flush_prompt = (
            "SYSTEM SILENT COMMAND: The context window is almost full. "
            "Please summarize your current reasoning state, memory trajectory, "
            "and any pending tool calls. "
            "Output MUST be in markdown format prefixed with 'WAL_CHECKPOINT:' "
            "so I can restore this session."
        )
        temp_messages = messages + [{"role": "user", "content": flush_prompt}]

        try:
            # Async call for the summary
            wal_state = await call_llm_fn(temp_messages, temperature=0.1)

            # 2. Write WAL to Workspace /STATE.md
            if self._workspace_path:
                state_path = os.path.join(self._workspace_path, "STATE.md")
                safe_wal_state = self._redact_fn(wal_state)
                os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
                with open(state_path, "w", encoding="utf-8") as f:
                    f.write(
                        f"# Session Checkpoint: {datetime.now().isoformat()}\n\n"
                        f"{safe_wal_state}"
                    )

            # 3. Truncate History: Keep System Prompt + WAL state
            if len(messages) > 3:
                system_msg = messages[0]
                messages.clear()
                messages.append(system_msg)
                messages.append({
                    "role": "user",
                    "content": (
                        f"Session Restored from Checkpoint:\n\n{wal_state}\n\n"
                        "Please continue where you left off."
                    ),
                })
                logger.info("Context truncated via WAL.")
        except Exception as e:
            logger.error(f"Silent flush failed: {e}")
