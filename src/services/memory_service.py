import abc
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

# --- Domain Entities ---
@dataclass
class ReportMemoryItem:
    user_id: str
    report_type: str
    report_date: str
    full_content: str
    compressed_summary: Optional[str] = None
    key_findings: Optional[Dict] = None

@dataclass
class MemoryContext:
    user_id: str
    report_type: str
    lookback_window: int
    recent_items: List[ReportMemoryItem]

    def get_compressed_context(self) -> str:
        """Formatted context string for LLM injection"""
        parts = []
        for i, item in enumerate(self.recent_items):
             offset = f"T-{i+1}"
             content = item.compressed_summary if item.compressed_summary else item.full_content[:500] + "..."
             parts.append(f"[{offset} Date: {item.report_date}]\n{content}\n")
        return "\n---\n".join(parts)

# --- Ports / Interfaces ---
class IMemoryRepository(abc.ABC):
    @abc.abstractmethod
    def get_recent_reports(self, user_id: str, report_type: str, limit: int) -> List[ReportMemoryItem]:
        pass

    @abc.abstractmethod
    def save_report(self, item: ReportMemoryItem) -> None:
        pass

class ILLMProvider(abc.ABC):
    """Interface for LLM operations needed by MemoryService"""
    @abc.abstractmethod
    def summarize(self, text: str) -> str:
        pass
    
    @abc.abstractmethod
    def check_contradictions(self, new_text: str, context_text: str) -> List[str]:
        pass

# --- Use Case / Service ---
class MemoryService:
    """
    Core Domain Logic for Memory Management.
    Decoupled from specific DBs or LLM APIs.
    """
    def __init__(self, repository: IMemoryRepository, llm_provider: ILLMProvider):
        self.repo = repository
        self.llm = llm_provider
        self.lookback_window = 4

    def get_context(self, user_id: str, report_type: str, model_max_tokens: int = 8192) -> MemoryContext:
        """
        Retrieves context with strict size limits (20% of model tolerance).
        User Requirement: Total context < 20% of Model Capacity.
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

    def store_report(self, user_id: str, report_type: str, date: str, content: str):
        # 1. Generate Summary (Compressed) for long-term storage
        summary = self.llm.summarize(content)
        
        item = ReportMemoryItem(
            user_id=user_id,
            report_type=report_type, # Guidelines: Strict separation stored here
            report_date=date,
            full_content=content,
            compressed_summary=summary
        )
        self.repo.save_report(item)
        logger.info(f"Stored {report_type} memory for {user_id}")

    def detect_conflicts(self, current_analysis: str, context: MemoryContext) -> List[str]:
        if not context.recent_items:
            return []
        context_str = context.get_compressed_context()
        return self.llm.check_contradictions(current_analysis, context_str)
