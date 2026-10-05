"""
Dynamic Debate Termination & Marginal Information Gain Service (A5 Engine)
跨專家交互辯論輪次動態終止與邊際資訊增益
=============================================================================
Provides algorithmic early convergence stopping and marginal information gain
tracking across multi-agent council debate rounds before redundant tokens and latency
are expended.

Key Capabilities:
1. Argument Semantic Similarity Tracking (Sim(r, r-1)):
   - Analyzes textual argument drift across successive rounds per agent.
   - Computes weighted token/n-gram semantic cosine & Jaccard overlap.
   - Detects repetitive echo arguments when similarity >= threshold (default 0.85).
2. Stance Stability & Drift Index (Delta Stance):
   - Measures stance changes (BUY/HOLD/SELL) and conviction swings across rounds.
   - Distinguishes between active debate persuasion vs. solidified consensus.
3. Marginal Information Gain (Delta I):
   - Formulates dynamic information gain:
     Delta I = 0.60 * (1 - Sim) + 0.40 * min(1.0, 2.0 * StanceDrift)
   - When Delta I < epsilon (default 0.12), flags diminishing returns.
4. Early Stopping Decision State Machine:
   - CONTINUE_DEBATE: Information gain remains high; further rounds warranted.
   - CONVERGED_TERMINATION: Opinions and rationale have converged; lock consensus early.
   - DEADLOCK_TERMINATION: Agents are entrenched in static disagreement; escalate to CIO.
   - MAX_ROUNDS_REACHED: Hard safety cap reached.
5. Efficiency & Savings Attribution:
   - Calculates estimated saved tokens (avg ~750 per agent-round) and latency (~4.5s/round).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("DynamicDebateTerminationService")


class TerminationStatus(str, Enum):
    """Classification of debate termination decision."""
    CONTINUE_DEBATE = "CONTINUE_DEBATE"
    CONVERGED_TERMINATION = "CONVERGED_TERMINATION"
    DEADLOCK_TERMINATION = "DEADLOCK_TERMINATION"
    MAX_ROUNDS_REACHED = "MAX_ROUNDS_REACHED"


@dataclass
class AgentDebateTurn:
    """Single agent's argument and vote within a debate round."""
    agent_name: str
    stance: str  # "BUY", "HOLD", "SELL"
    confidence: float
    arguments: str
    key_points: List[str] = field(default_factory=list)


@dataclass
class DebateRoundSnapshot:
    """Complete collection of all agent turns in a single round."""
    round_number: int
    turns: List[AgentDebateTurn]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TerminationEvaluation:
    """Comprehensive evaluation of whether debate should terminate."""
    round_number: int
    decision: TerminationStatus
    marginal_info_gain: float
    semantic_similarity: float
    stance_drift: float
    estimated_tokens_saved: int
    estimated_latency_saved_seconds: float
    rationale: str
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "decision": self.decision.value,
            "marginal_info_gain": round(self.marginal_info_gain, 4),
            "semantic_similarity": round(self.semantic_similarity, 4),
            "stance_drift": round(self.stance_drift, 4),
            "estimated_tokens_saved": self.estimated_tokens_saved,
            "estimated_latency_saved_seconds": round(self.estimated_latency_saved_seconds, 2),
            "rationale": self.rationale,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


class DynamicDebateTerminationService:
    """
    A5 Engine: Dynamically terminates multi-agent council debate rounds
    based on marginal information gain and semantic consensus convergence.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        default_min_rounds: int = 2,
        default_max_rounds: int = 5,
        default_marginal_info_gain_threshold: float = 0.12,
        default_argument_similarity_threshold: float = 0.85,
    ) -> None:
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self._min_rounds = default_min_rounds
        self._max_rounds = default_max_rounds
        self._marginal_info_gain_threshold = default_marginal_info_gain_threshold
        self._argument_similarity_threshold = default_argument_similarity_threshold

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service and hasattr(self.settings_service, "get"):
            try:
                val = self.settings_service.get(key)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to fetch setting '{key}': {e}. Using default {default}")
        return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("debate_termination_enabled", True))

    @property
    def min_rounds(self) -> int:
        return int(self._get_setting("debate_min_rounds", self._min_rounds))

    @property
    def max_rounds(self) -> int:
        return int(self._get_setting("debate_max_rounds", self._max_rounds))

    @property
    def marginal_info_gain_threshold(self) -> float:
        return float(self._get_setting("debate_marginal_info_gain_threshold", self._marginal_info_gain_threshold))

    @property
    def argument_similarity_threshold(self) -> float:
        return float(self._get_setting("debate_argument_similarity_threshold", self._argument_similarity_threshold))

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        """Extract character n-grams and word tokens supporting bilingual Chinese/English text."""
        tokens: Set[str] = set()
        # English and numeric tokens
        for w in re.findall(r"[a-zA-Z0-9_]+", text.lower()):
            if len(w) > 0:
                tokens.add(w)

        # CJK unigrams and bigrams
        cjk_chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
        for ch in cjk_chars:
            tokens.add(ch)
        for i in range(len(cjk_chars) - 1):
            tokens.add(cjk_chars[i] + cjk_chars[i + 1])

        return tokens

    @classmethod
    def compute_text_similarity(cls, text_a: str, text_b: str) -> float:
        """Computes Dice similarity coefficient between two debate turns."""
        tokens_a = cls._tokenize(text_a)
        tokens_b = cls._tokenize(text_b)

        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0

        intersection = len(tokens_a.intersection(tokens_b))
        total = len(tokens_a) + len(tokens_b)
        return (2.0 * intersection) / total if total > 0 else 1.0

    def compute_round_similarity(
        self,
        prev_round: DebateRoundSnapshot,
        curr_round: DebateRoundSnapshot,
    ) -> float:
        """
        Computes the average semantic similarity of arguments for agents
        participating across both rounds.
        """
        prev_map = {t.agent_name.upper(): t for t in prev_round.turns}
        curr_map = {t.agent_name.upper(): t for t in curr_round.turns}

        common_agents = set(prev_map.keys()).intersection(curr_map.keys())
        if not common_agents:
            return 0.0

        total_sim = 0.0
        for agent in common_agents:
            t_prev = prev_map[agent]
            t_curr = curr_map[agent]

            text_prev = f"{t_prev.arguments} {' '.join(t_prev.key_points)}"
            text_curr = f"{t_curr.arguments} {' '.join(t_curr.key_points)}"
            sim = self.compute_text_similarity(text_prev, text_curr)
            total_sim += sim

        return total_sim / len(common_agents)

    def compute_stance_drift(
        self,
        prev_round: DebateRoundSnapshot,
        curr_round: DebateRoundSnapshot,
    ) -> float:
        """
        Quantifies the drift in agent stances and confidence scores.
        Returns drift in [0.0, 1.0].
        """
        prev_map = {t.agent_name.upper(): t for t in prev_round.turns}
        curr_map = {t.agent_name.upper(): t for t in curr_round.turns}

        common_agents = set(prev_map.keys()).intersection(curr_map.keys())
        if not common_agents:
            return 1.0

        total_drift = 0.0
        for agent in common_agents:
            p = prev_map[agent]
            c = curr_map[agent]

            stance_changed = 1.0 if p.stance.upper() != c.stance.upper() else 0.0
            conf_diff = abs(p.confidence - c.confidence)
            agent_drift = 0.70 * stance_changed + 0.30 * min(1.0, conf_diff)
            total_drift += agent_drift

        return total_drift / len(common_agents)

    def evaluate_termination(
        self,
        history_rounds: List[DebateRoundSnapshot],
    ) -> TerminationEvaluation:
        """
        Assesses whether the ongoing council debate should be dynamically terminated.
        """
        now = datetime.now(timezone.utc)
        if not history_rounds:
            return TerminationEvaluation(
                round_number=0,
                decision=TerminationStatus.CONTINUE_DEBATE,
                marginal_info_gain=1.0,
                semantic_similarity=0.0,
                stance_drift=1.0,
                estimated_tokens_saved=0,
                estimated_latency_saved_seconds=0.0,
                rationale="Debate has not yet commenced.",
                evaluated_at=now,
            )

        curr_round = history_rounds[-1]
        round_num = curr_round.round_number
        agents_count = max(1, len(curr_round.turns))

        # Check hard cap first
        if round_num >= self.max_rounds:
            return TerminationEvaluation(
                round_number=round_num,
                decision=TerminationStatus.MAX_ROUNDS_REACHED,
                marginal_info_gain=0.0,
                semantic_similarity=1.0,
                stance_drift=0.0,
                estimated_tokens_saved=0,
                estimated_latency_saved_seconds=0.0,
                rationale=f"Hard upper round limit ({self.max_rounds}) reached.",
                evaluated_at=now,
            )

        # Check minimum rounds
        if round_num < self.min_rounds or len(history_rounds) < 2:
            return TerminationEvaluation(
                round_number=round_num,
                decision=TerminationStatus.CONTINUE_DEBATE,
                marginal_info_gain=1.0,
                semantic_similarity=0.0,
                stance_drift=1.0,
                estimated_tokens_saved=0,
                estimated_latency_saved_seconds=0.0,
                rationale=f"Minimum debate rounds ({self.min_rounds}) requirement not yet satisfied.",
                evaluated_at=now,
            )

        if not self.is_enabled:
            return TerminationEvaluation(
                round_number=round_num,
                decision=TerminationStatus.CONTINUE_DEBATE,
                marginal_info_gain=1.0,
                semantic_similarity=0.0,
                stance_drift=1.0,
                estimated_tokens_saved=0,
                estimated_latency_saved_seconds=0.0,
                rationale="Dynamic debate termination is disabled by configuration.",
                evaluated_at=now,
            )

        prev_round = history_rounds[-2]
        similarity = self.compute_round_similarity(prev_round, curr_round)
        drift = self.compute_stance_drift(prev_round, curr_round)

        # Formulate Marginal Information Gain Delta I
        novelty = max(0.0, 1.0 - similarity)
        info_gain = max(0.0, min(1.0, 0.60 * novelty + 0.40 * min(1.0, 2.0 * drift)))

        rounds_saved = max(0, self.max_rounds - round_num)
        tokens_saved = rounds_saved * agents_count * 750
        latency_saved = rounds_saved * 4.5

        # Early termination condition check
        if (
            info_gain < self.marginal_info_gain_threshold
            and similarity >= self.argument_similarity_threshold
        ):
            # Check whether agents have achieved consensus or deadlock
            stances = [t.stance.upper() for t in curr_round.turns]
            dominant_count = max(stances.count(s) for s in set(stances)) if stances else 0
            dominant_ratio = dominant_count / len(stances) if stances else 0.0

            # Consensus requires at least 65% alignment
            if len(set(stances)) == 1 or dominant_ratio >= 0.65:
                decision = TerminationStatus.CONVERGED_TERMINATION
                rationale = (
                    f"Arguments converged (Sim={similarity:.2f} >= {self.argument_similarity_threshold:.2f}, "
                    f"InfoGain={info_gain:.3f} < {self.marginal_info_gain_threshold:.3f}). "
                    f"Solidified consensus achieved early at round {round_num}."
                )
            else:
                decision = TerminationStatus.DEADLOCK_TERMINATION
                rationale = (
                    f"Entrenched debate deadlock detected (Sim={similarity:.2f}, InfoGain={info_gain:.3f}). "
                    f"Agents maintain static conflicting stances without new information; escalating to CIO."
                )

            return TerminationEvaluation(
                round_number=round_num,
                decision=decision,
                marginal_info_gain=info_gain,
                semantic_similarity=similarity,
                stance_drift=drift,
                estimated_tokens_saved=tokens_saved,
                estimated_latency_saved_seconds=latency_saved,
                rationale=rationale,
                evaluated_at=now,
            )

        return TerminationEvaluation(
            round_number=round_num,
            decision=TerminationStatus.CONTINUE_DEBATE,
            marginal_info_gain=info_gain,
            semantic_similarity=similarity,
            stance_drift=drift,
            estimated_tokens_saved=0,
            estimated_latency_saved_seconds=0.0,
            rationale=(
                f"Sufficient marginal information gain detected (InfoGain={info_gain:.3f} >= {self.marginal_info_gain_threshold:.3f}, "
                f"Sim={similarity:.2f}). Proceeding with next debate round."
            ),
            evaluated_at=now,
        )
