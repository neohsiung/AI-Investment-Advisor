"""
Aggregation Strategies for Swarm Result Synthesis.
群集結果合成的聚合策略。

Pluggable strategies for combining multiple agent outputs:
  - ConcatStrategy: Simple concatenation (legacy default)
  - MajorityVoteStrategy: Extract signals and return majority verdict
  - WeightedVoteStrategy: Weight-based scoring with agent performance

遵循規範:
  - 規範一 (Clean Architecture): Strategy Pattern，單一職責
  - 規範八 (動態指標原則): 權重皆為可調參數
  - 規範四 (模組化設計): 獨立可單元測試
"""

import re
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class Signal(str, Enum):
    """Agent output signal classification."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    ERROR = "error"


@dataclass
class VoteResult:
    """Result of a consensus vote."""
    verdict: Signal
    confidence: float  # 0.0 ~ 1.0
    vote_counts: Dict[str, int] = field(default_factory=dict)
    details: str = ""


class AggregationStrategy(ABC):
    """Base class for aggregation strategies."""

    @abstractmethod
    def aggregate(
        self, results: Dict[str, str], weights: Optional[Dict[str, float]] = None
    ) -> str:
        """
        Aggregate multiple agent results into a single output.

        Args:
            results: Dict of agent_name → response_text
            weights: Optional dict of agent_name → weight (0.0-1.0)
        """
        pass


class ConcatStrategy(AggregationStrategy):
    """Simple concatenation (legacy default)."""

    def aggregate(
        self, results: Dict[str, str], weights: Optional[Dict[str, float]] = None
    ) -> str:
        summary = "### Swarm Results\n"
        for name, res in results.items():
            summary += f"#### {name}\n{res}\n\n"
        return summary


class MajorityVoteStrategy(AggregationStrategy):
    """
    Extract signals (bullish/bearish/neutral) and return majority.
    提取訊號並回傳多數決結果。
    """

    # Signal detection patterns (case-insensitive)
    BULLISH_PATTERNS = [
        r"\b(bullish|buy|strong buy|overweight|accumulate|upgrade)\b",
        r"\b(positive outlook|upside potential|recommendation:\s*buy)\b",
    ]
    BEARISH_PATTERNS = [
        r"\b(bearish|sell|strong sell|underweight|reduce|downgrade)\b",
        r"\b(negative outlook|downside risk|recommendation:\s*sell)\b",
    ]

    def classify_signal(self, text: str) -> Signal:
        """Classify agent output into a signal."""
        text_lower = text.lower()

        bullish_score = sum(
            1 for p in self.BULLISH_PATTERNS if re.search(p, text_lower)
        )
        bearish_score = sum(
            1 for p in self.BEARISH_PATTERNS if re.search(p, text_lower)
        )

        if bullish_score > bearish_score:
            return Signal.BULLISH
        elif bearish_score > bullish_score:
            return Signal.BEARISH
        return Signal.NEUTRAL

    def vote(
        self, results: Dict[str, str], weights: Optional[Dict[str, float]] = None
    ) -> VoteResult:
        """
        Run majority vote and return structured result.
        執行多數決並回傳結構化結果。
        """
        votes: Dict[Signal, float] = {
            Signal.BULLISH: 0.0,
            Signal.BEARISH: 0.0,
            Signal.NEUTRAL: 0.0,
        }
        agent_signals: Dict[str, Signal] = {}

        for name, text in results.items():
            if text.startswith("Error:"):
                agent_signals[name] = Signal.ERROR
                continue

            signal = self.classify_signal(text)
            agent_signals[name] = signal
            w = (weights or {}).get(name, 1.0)
            votes[signal] += w

        total = sum(votes.values()) or 1.0
        verdict = max(votes, key=votes.get)
        confidence = votes[verdict] / total

        vote_counts = {s.value: int(v) for s, v in votes.items() if v > 0}

        details = "| Agent | Signal | Weight |\n|-------|--------|--------|\n"
        for name, sig in agent_signals.items():
            w = (weights or {}).get(name, 1.0)
            details += f"| {name} | {sig.value} | {w:.2f} |\n"

        return VoteResult(
            verdict=verdict,
            confidence=confidence,
            vote_counts=vote_counts,
            details=details,
        )

    def aggregate(
        self, results: Dict[str, str], weights: Optional[Dict[str, float]] = None
    ) -> str:
        result = self.vote(results, weights)
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(
            result.verdict.value, "⚪"
        )
        return (
            f"### Council Consensus: {emoji} {result.verdict.value.upper()}\n"
            f"**Confidence**: {result.confidence:.0%}\n"
            f"**Votes**: {result.vote_counts}\n\n"
            f"{result.details}"
        )


class WeightedVoteStrategy(MajorityVoteStrategy):
    """
    Weighted voting with dynamic agent performance weights.
    具動態 Agent 性能權重的加權投票。
    """

    def __init__(self, agent_repo=None):
        self._agent_repo = agent_repo

    def aggregate(
        self, results: Dict[str, str], weights: Optional[Dict[str, float]] = None
    ) -> str:
        # Auto-fetch weights from repo if not provided
        if not weights and self._agent_repo:
            weights = {}
            for name in results:
                weights[name] = self._agent_repo.get_agent_weight(
                    name, default=1.0
                )

        return super().aggregate(results, weights)


# ── Degradation Chain ────────────────────────────────────────

class DegradationChain:
    """
    Graceful degradation: detect emergency signals and short-circuit.
    優雅降級：偵測緊急訊號並短路。
    """

    EMERGENCY_KEYWORDS = [
        "CRITICAL DANGER",
        "EMERGENCY STOP",
        "SYSTEM PAUSE",
        "CIRCUIT BREAKER",
    ]

    @classmethod
    def check(cls, text: str) -> bool:
        """Check if text contains emergency signals."""
        upper = text.upper()
        return any(kw in upper for kw in cls.EMERGENCY_KEYWORDS)

    @classmethod
    def format_emergency(cls, tier_name: str, summary: str) -> str:
        """Format emergency stop response."""
        return (
            f"🚨 **EMERGENCY STOP TRIGGERED BY {tier_name.upper()} TIER**:\n\n"
            f"{summary}"
        )


# ── Strategy Registry ────────────────────────────────────────

STRATEGIES: Dict[str, type] = {
    "concat": ConcatStrategy,
    "majority_vote": MajorityVoteStrategy,
    "weighted_vote": WeightedVoteStrategy,
}


def get_strategy(name: str, **kwargs) -> AggregationStrategy:
    """
    Factory for aggregation strategies.
    聚合策略工廠。
    """
    cls = STRATEGIES.get(name)
    if not cls:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGIES.keys())}")
    return cls(**kwargs) if kwargs else cls()
