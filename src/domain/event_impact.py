"""
Domain models for Event Impact Bias Loop.
事件量化抽取與交易評分偏置閉環之領域模型。

Defines:
  - EventScope: MICRO (個經 / Idiosyncratic) vs MACRO (總經 / Systemic)
  - EventSentiment: BULLISH, BEARISH, NEUTRAL
  - EventImpact: Core entity representing a quantified event and its exponential time-decay
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid


class EventScope(str, Enum):
    """Scope of an event: Micro (ticker-specific) vs Macro (systemic)."""
    MICRO = "micro"  # 個經事件：影響特定標的 (如降評、財報、管理層異動)
    MACRO = "macro"  # 總經事件：影響市場整體防禦與流動性 (如 FOMC、通膨、地緣風險)


class EventSentiment(str, Enum):
    """Sentiment direction of an event."""
    BULLISH = "bullish"  # 正向利多
    BEARISH = "bearish"  # 負向利空
    NEUTRAL = "neutral"  # 中性或資訊追蹤


@dataclass
class EventImpact:
    """
    Quantified market event with mathematical exponential time-decay.
    具備指數時間衰減的量化市場事件。
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    scope: EventScope = EventScope.MICRO
    ticker: Optional[str] = None  # None for Macro, uppercase symbol for Micro
    category: str = "general"
    headline: str = ""
    summary: str = ""
    sentiment: EventSentiment = EventSentiment.NEUTRAL
    initial_impact: float = 0.0  # Micro: [-2.0, +2.0] score delta; Macro: [-1.0, +1.0] stress
    half_life_hours: float = 36.0  # Decay half-life in hours
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_dismissed: bool = False

    def compute_decayed_impact(self, at_time: Optional[datetime] = None) -> float:
        """
        Calculate time-decayed impact at a given timestamp:
        Impact(t) = I0 * 2^(-Δt / T_half)
        """
        if self.is_dismissed:
            return 0.0

        if at_time is None:
            at_time = datetime.now(timezone.utc)
        elif at_time.tzinfo is None:
            at_time = at_time.replace(tzinfo=timezone.utc)

        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        delta_seconds = (at_time - created).total_seconds()
        if delta_seconds < 0:
            delta_hours = 0.0
        else:
            delta_hours = delta_seconds / 3600.0

        if self.half_life_hours <= 0:
            return round(self.initial_impact, 2)

        # Decay: I(t) = I_0 * 2^(-Δt / T_half)
        decayed = self.initial_impact * (2.0 ** (-delta_hours / self.half_life_hours))

        # Negligible threshold cut-off: < 0.05 or >= 3.5 half-lives is considered fully decayed
        if delta_hours >= self.half_life_hours * 3.5 or abs(decayed) < 0.05:
            return 0.0

        return round(decayed, 2)

    def is_active(self, at_time: Optional[datetime] = None) -> bool:
        """Returns True if the event has not been dismissed and still carries non-zero impact."""
        if self.is_dismissed:
            return False
        return abs(self.compute_decayed_impact(at_time)) >= 0.03

    def remaining_hours(self, at_time: Optional[datetime] = None) -> float:
        """Estimated hours until impact decays to negligible (< 0.05). Effective lifespan ~ 3 half-lives."""
        if at_time is None:
            at_time = datetime.now(timezone.utc)
        elif at_time.tzinfo is None:
            at_time = at_time.replace(tzinfo=timezone.utc)

        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        elapsed = max(0.0, (at_time - created).total_seconds() / 3600.0)
        total_lifespan = self.half_life_hours * 3.5
        remaining = max(0.0, total_lifespan - elapsed)
        return round(remaining, 1)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        created_str = (
            self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else str(self.created_at)
        )
        return {
            "id": self.id,
            "user_id": self.user_id,
            "scope": self.scope.value if isinstance(self.scope, EventScope) else str(self.scope),
            "ticker": self.ticker.upper() if self.ticker else None,
            "category": self.category,
            "headline": self.headline,
            "summary": self.summary,
            "sentiment": self.sentiment.value if isinstance(self.sentiment, EventSentiment) else str(self.sentiment),
            "initial_impact": float(self.initial_impact),
            "current_impact": self.compute_decayed_impact(),
            "half_life_hours": float(self.half_life_hours),
            "remaining_hours": self.remaining_hours(),
            "created_at": created_str,
            "metadata": self.metadata,
            "is_dismissed": bool(self.is_dismissed),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventImpact":
        """Deserialize from dictionary."""
        created = data.get("created_at")
        if isinstance(created, str):
            try:
                created_dt = datetime.fromisoformat(created)
            except Exception:
                created_dt = datetime.now(timezone.utc)
        elif isinstance(created, datetime):
            created_dt = created
        else:
            created_dt = datetime.now(timezone.utc)

        scope_raw = data.get("scope", "micro")
        try:
            scope = EventScope(scope_raw)
        except ValueError:
            scope = EventScope.MICRO

        sent_raw = data.get("sentiment", "neutral")
        try:
            sentiment = EventSentiment(sent_raw)
        except ValueError:
            sentiment = EventSentiment.NEUTRAL

        return cls(
            id=str(data.get("id", uuid.uuid4())),
            user_id=str(data.get("user_id", "")),
            scope=scope,
            ticker=data.get("ticker").upper() if data.get("ticker") else None,
            category=str(data.get("category", "general")),
            headline=str(data.get("headline", "")),
            summary=str(data.get("summary", "")),
            sentiment=sentiment,
            initial_impact=float(data.get("initial_impact", 0.0)),
            half_life_hours=float(data.get("half_life_hours", 36.0)),
            created_at=created_dt,
            metadata=dict(data.get("metadata", {})),
            is_dismissed=bool(data.get("is_dismissed", False)),
        )
