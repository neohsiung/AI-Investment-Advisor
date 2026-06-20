"""
EventAggregator — Service for tiered event aggregation & batch dispatching.

Core design:
- Events are ingested w/ tier classification, written to event_queue (silent)
- Agents pull pending events via pull_batch() — never pushed
- Only P0+Actionable events bypass queue for immediate notification

Tier definitions:
  P0 (Critical)   : market crash, liquidity crisis, hack → immediate processing
  P1 (Important)  : price drift >2%, earnings, major news → batch every 5-15min
  P2 (Routine)    : price micro-adjustments, minor signals → batch every 1-4h
  P3 (Reference)  : fundamentals update, research papers → batch daily/weekly
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.data.models import EventQueue
from src.repositories.event_queue_repository import EventQueueRepository

logger = logging.getLogger(__name__)

# Default aggregation windows (in minutes)
TIER_WINDOWS: Dict[str, int] = {
    EventQueue.TIER_P0: 0,    # Immediate
    EventQueue.TIER_P1: 15,   # Every 15 minutes
    EventQueue.TIER_P2: 240,  # Every 4 hours
    EventQueue.TIER_P3: 1440, # Every 24 hours
}

# Keywords that trigger P0 classification
P0_KEYWORDS = [
    "crash", "collapse", "hack", "fraud", "liquidity crisis",
    "bankrun", "black swan", "flash crash", "circuit breaker",
]

# Keywords that trigger P1 classification
P1_KEYWORDS = [
    "sell", "reduce", "trim", "buy", "exit", "hedge",
    "earnings", "dividend", "split", "upgrade", "downgrade",
    "drift", "overweight", "underweight",
]


class EventAggregator:
    """Service for managing the event aggregation lifecycle."""

    def __init__(self, repository: Optional[EventQueueRepository] = None):
        self.repo = repository or EventQueueRepository()

    # ──────────────────────────────────────────────
    # Classification
    # ──────────────────────────────────────────────

    @staticmethod
    def classify_tier(event_type: str, content: dict, existing_decision: str = "") -> Tuple[str, int]:
        """
        Classify an event into P0-P3 based on content signals.
        Returns (tier, priority).

        Priority 100+ = actionable (immediate attention)
        Priority 50-99 = important
        Priority 0-49 = background
        """
        # Build a string from content for keyword matching
        content_text = json_content_str(content) + " " + existing_decision.lower()
        content_lower = content_text.lower()

        # P0: Critical keywords
        if any(kw in content_lower for kw in P0_KEYWORDS):
            return EventQueue.TIER_P0, 100

        # P1: Actionable keywords
        if any(kw in content_lower for kw in P1_KEYWORDS):
            return EventQueue.TIER_P1, 80

        # P1: Any event with concrete numerical data (price changes, %, $ amounts)
        if any(c in content_text for c in ["%", "$", "+", "-", ">", "<"]):
            if event_type in ("sentinel_alert", "sentinel_threshold_breach"):
                return EventQueue.TIER_P1, 60
            return EventQueue.TIER_P2, 40

        # P2: Routine system events
        if event_type in ("report", "daily_snapshot", "rebalance_check"):
            return EventQueue.TIER_P2, 30

        # P3: Everything else (reference, research, noise)
        return EventQueue.TIER_P3, 10

    @staticmethod
    def is_actionable(tier: str, content: dict, decision: str = "") -> bool:
        """Check if an event is truly actionable (should trigger immediate notification)."""
        if tier != EventQueue.TIER_P0:
            return False
        # P0 is always actionable by definition
        return True

    # ──────────────────────────────────────────────
    # Ingestion
    # ──────────────────────────────────────────────

    def ingest_event(
        self,
        user_id: str,
        event_type: str,
        content: dict,
        tier: Optional[str] = None,
        priority: Optional[int] = None,
        decision: str = "",
    ) -> str:
        """
        Classify, write to queue, and return event_id.
        Never sends notifications — that's the Agent's job on pull.
        """
        if tier is None or priority is None:
            classified_tier, classified_priority = self.classify_tier(event_type, content, decision)
            tier = tier or classified_tier
            priority = priority if priority is not None else classified_priority

        event_id = self.repo.insert_event(
            user_id=user_id,
            event_type=event_type,
            content=content,
            tier=tier,
            priority=priority,
        )

        logger.info(
            f"EventAggregator: ingested {event_id} [{tier}/p{priority}] "
            f"type={event_type} user={user_id[:8]}..."
        )
        return event_id

    # ──────────────────────────────────────────────
    # Batch Pull (for agents)
    # ──────────────────────────────────────────────

    def pull_batch(
        self,
        user_id: str,
        tier: str = EventQueue.TIER_P0,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Pull and lock pending events for agent processing."""
        return self.repo.pull_batch(user_id=user_id, tier=tier, limit=limit, batch_mode=True)

    def pull_multi_tier(
        self,
        user_id: str,
        tiers: Optional[List[str]] = None,
        max_total: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Pull events from multiple tiers, starting from P0 (highest priority).
        Returns a merged, deduplicated list ordered by priority desc.
        """
        tiers = tiers or [EventQueue.TIER_P0, EventQueue.TIER_P1, EventQueue.TIER_P2]
        all_events = []
        for tier in tiers:
            remaining = max_total - len(all_events)
            if remaining <= 0:
                break
            batch = self.repo.pull_batch(
                user_id=user_id, tier=tier,
                limit=remaining,
                batch_mode=True,
            )
            all_events.extend(batch)

        # Sort by priority descending
        all_events.sort(key=lambda e: e.get("priority", 0), reverse=True)
        return all_events

    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    def mark_processed(self, event_ids: List[str], batch_id: Optional[str] = None):
        """Mark events as analyzed after agent processing."""
        self.repo.mark_processed(event_ids, batch_id)

    def get_pending_summary(self, user_id: str) -> Dict[str, Any]:
        """Get a summary of pending events for decision-making."""
        counts = self.repo.get_pending_counts(user_id)
        total = sum(counts.values())

        summary = {
            "total_pending": total,
            "counts": counts,
            "has_critical": counts.get(EventQueue.TIER_P0, 0) > 0,
            "needs_attention": counts.get(EventQueue.TIER_P0, 0) > 0 or counts.get(EventQueue.TIER_P1, 0) > 5,
            "recommended_action": "immediate" if counts.get(EventQueue.TIER_P0, 0) > 0
            else "batch" if counts.get(EventQueue.TIER_P1, 0) > 0
            else "skip",
        }
        return summary


def json_content_str(content: dict) -> str:
    """Flatten a dict into a searchable string for keyword matching."""
    parts = []
    for v in content.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (int, float)):
            parts.append(str(v))
        elif isinstance(v, dict):
            parts.append(json_content_str(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    parts.append(item)
    return " ".join(parts)