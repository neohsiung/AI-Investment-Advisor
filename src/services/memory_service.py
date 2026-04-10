import abc
from dataclasses import dataclass
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import json
from src.utils.logger import setup_logger
logger = setup_logger("MemoryService")

# --- Domain Entities & Interfaces (Canonical Source: src.domain) ---
# Re-exported here for backward compatibility.
# 領域實體與介面（規範來源：src.domain），此處為向後相容重新匯出。
from src.domain.entities import ReportMemoryItem, MemoryContext  # noqa: F401
from src.domain.interfaces import IMemoryRepository, ILLMProvider  # noqa: F401

# --- Use Case / Service ---
class MemoryService:
    """
    Core Domain Logic for context-aware Memory Management (Memory-Protocol-HR).
    記憶管理核心領域邏輯（HR 記憶協議）。
    
    Decoupled from specific DBs or LLM APIs through interfaces.
    透過介面與特定資料庫或 LLM API 解耦。
    """
    def __init__(self, repository: IMemoryRepository, llm_provider: ILLMProvider) -> None:
        """
        Initialize the memory service.
        初始化記憶服務。
        """
        self.repo = repository
        self.llm = llm_provider
        self.lookback_window = 4

    def get_context(self, user_id: str, report_type: str, model_max_tokens: int = 8192) -> MemoryContext:
        """
        Retrieve memory context with strict size limits (20% of model tolerance).
        檢索具有嚴格大小限制的記憶內容（模型容差的 20%）。
        """
        # 1. Fetch Candidates (fetch more than needed to allow filtering)
        items = self.repo.get_recent_reports(user_id, report_type, limit=10)
        
        # 2. Adaptive Compression Logic
        target_token_limit = int(model_max_tokens * 0.20)
        
        # Helper for rough token count (4 chars ~= 1 token)
        def estimate_tokens(text: str) -> int:
            return len(text) // 4

        final_items = []
        current_usage = 0
        
        # Strategy: 
        # T-1: Try to keep detailed
        # T-2+: Keep minimal (compressed_summary or key_findings)
        
        for i, item in enumerate(items):
            # Decide representation based on recency
            content_to_use = ""
            label = ""
            
            if i == 0: # Most recent (T-1)
                # Prefer full content if it fits, else compressed
                if estimate_tokens(item.full_content) < (target_token_limit * 0.6): # Allow T-1 to take up to 60% of the budget
                     content_to_use = item.full_content
                     label = "(Full)"
                else:
                     content_to_use = item.compressed_summary or item.full_content[:2000]
                     label = "(Summary)"
            else: # Older (T-2+)
                 # Always use compressed
                 content_to_use = item.compressed_summary or ""
                 if not content_to_use and item.full_content:
                     content_to_use = item.full_content[:500] + "..." # Fallback truncation
                 label = "(Compressed)"
            
            # Check budget
            # We construct the potential string entry
            entry = f"[{item.report_date}] {label}\n{content_to_use}\n"
            cost = estimate_tokens(entry)
            
            if current_usage + cost <= target_token_limit:
                final_items.append(item)
                current_usage += cost
            else:
                # Budget exceeded, stop adding older memories
                logger.info(f"Memory Context Limit Reached: Used {current_usage}/{target_token_limit} tokens. Dropping older items.")
                break
        
        return MemoryContext(
            user_id=user_id, 
            report_type=report_type, 
            lookback_window=len(final_items), 
            recent_items=final_items
        )

    async def store_report(self, user_id: str, report_type: str, date: str, content: str) -> None:
        """
        Compress and store a report in the memory repository.
        壓縮並將報告儲存在記憶儲存庫中。
        """
        # 1. Generate Summary (Compressed) for long-term storage
        summary = await self.llm.summarize(content)
        
        item = ReportMemoryItem(
            user_id=user_id,
            report_type=report_type, # Guidelines: Strict separation stored here
            report_date=date,
            full_content=content,
            compressed_summary=summary
        )
        self.repo.save_report(item)
        logger.info(f"Stored {report_type} memory for {user_id}")

    async def detect_conflicts(self, current_analysis: str, context: MemoryContext) -> List[str]:
        """
        Detect contradictions between current analysis and historical memory context.
        檢測目前分析與歷史記憶內容之間的矛盾。
        """
        if not context.recent_items:
            return []
        context_str = context.get_compressed_context()
        return await self.llm.check_contradictions(current_analysis, context_str)
