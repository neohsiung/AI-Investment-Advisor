"""
Tests for Phase 4: Swarm Orchestration Upgrade.
Phase 4 測試：群集編排升級 — 策略、共識與降級。
"""

import pytest
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock

from src.agents.swarm.strategies import (
    Signal, VoteResult,
    ConcatStrategy, MajorityVoteStrategy, WeightedVoteStrategy,
    DegradationChain, get_strategy,
)
from src.agents.swarm.swarm_orchestrator import SwarmOrchestrator


# ──────────────────────────────────────────────────────
# Signal Classification Tests
# ──────────────────────────────────────────────────────

class TestSignalClassification:

    @pytest.fixture
    def strategy(self):
        return MajorityVoteStrategy()

    def test_bullish_signal(self, strategy):
        text = "AAPL shows strong momentum, Recommendation: BUY. Bullish outlook."
        assert strategy.classify_signal(text) == Signal.BULLISH

    def test_bearish_signal(self, strategy):
        text = "Revenue declining. Bearish pattern. Recommendation: SELL."
        assert strategy.classify_signal(text) == Signal.BEARISH

    def test_neutral_signal(self, strategy):
        text = "Mixed signals. Hold for now, awaiting earnings."
        assert strategy.classify_signal(text) == Signal.NEUTRAL

    def test_case_insensitive(self, strategy):
        assert strategy.classify_signal("STRONG BUY RECOMMENDATION") == Signal.BULLISH
        assert strategy.classify_signal("strong sell signal") == Signal.BEARISH


# ──────────────────────────────────────────────────────
# Aggregation Strategy Tests
# ──────────────────────────────────────────────────────

class TestConcatStrategy:

    def test_basic_concat(self):
        s = ConcatStrategy()
        results = {"AgentA": "Result A", "AgentB": "Result B"}
        output = s.aggregate(results)
        assert "AgentA" in output
        assert "Result A" in output
        assert "AgentB" in output

    def test_empty_results(self):
        s = ConcatStrategy()
        assert "Swarm Results" in s.aggregate({})


class TestMajorityVoteStrategy:

    def test_majority_bullish(self):
        s = MajorityVoteStrategy()
        results = {
            "Momentum": "Bullish breakout confirmed",
            "Fundamental": "Strong buy signal",
            "Sentiment": "Market is bearish",
        }
        vote = s.vote(results)
        assert vote.verdict == Signal.BULLISH
        assert vote.confidence > 0.5

    def test_majority_bearish(self):
        s = MajorityVoteStrategy()
        results = {
            "Momentum": "Sell signal, downgrade",
            "Fundamental": "Bearish outlook, underweight",
            "Sentiment": "Bullish sentiment",
        }
        vote = s.vote(results)
        assert vote.verdict == Signal.BEARISH

    def test_unanimous(self):
        s = MajorityVoteStrategy()
        results = {
            "A": "Strong buy", "B": "Bullish", "C": "Accumulate"
        }
        vote = s.vote(results)
        assert vote.verdict == Signal.BULLISH
        assert vote.confidence == 1.0

    def test_error_agents_excluded(self):
        s = MajorityVoteStrategy()
        results = {
            "A": "Bullish signal",
            "B": "Error: Timeout",
            "C": "Buy recommendation",
        }
        vote = s.vote(results)
        assert vote.verdict == Signal.BULLISH

    def test_aggregate_text(self):
        s = MajorityVoteStrategy()
        results = {"A": "Bullish", "B": "Bearish", "C": "Buy signal"}
        text = s.aggregate(results)
        assert "Council Consensus" in text
        assert "Confidence" in text

    def test_weighted_vote(self):
        s = MajorityVoteStrategy()
        results = {
            "Senior": "Buy recommendation",
            "Junior": "Sell signal, bearish",
        }
        # Senior has higher weight
        vote = s.vote(results, weights={"Senior": 3.0, "Junior": 1.0})
        assert vote.verdict == Signal.BULLISH


class TestWeightedVoteStrategy:

    def test_auto_fetch_weights(self):
        repo = MagicMock()
        repo.get_agent_weight.return_value = 1.0
        s = WeightedVoteStrategy(agent_repo=repo)
        results = {"A": "Bullish", "B": "Bearish"}
        s.aggregate(results)
        assert repo.get_agent_weight.call_count == 2

    def test_without_repo(self):
        s = WeightedVoteStrategy()
        results = {"A": "Buy signal"}
        output = s.aggregate(results)
        assert "Council Consensus" in output


# ──────────────────────────────────────────────────────
# DegradationChain Tests
# ──────────────────────────────────────────────────────

class TestDegradationChain:

    def test_detects_critical_danger(self):
        assert DegradationChain.check("CRITICAL DANGER: Market crash")

    def test_detects_emergency_stop(self):
        assert DegradationChain.check("Some analysis... EMERGENCY STOP needed")

    def test_detects_circuit_breaker(self):
        assert DegradationChain.check("CIRCUIT BREAKER triggered")

    def test_no_emergency(self):
        assert not DegradationChain.check("Everything looks fine. Bullish outlook.")

    def test_case_insensitive(self):
        assert DegradationChain.check("critical danger detected")

    def test_format_emergency(self):
        result = DegradationChain.format_emergency("Fast", "Details...")
        assert "EMERGENCY STOP" in result
        assert "FAST" in result


# ──────────────────────────────────────────────────────
# Strategy Factory Tests
# ──────────────────────────────────────────────────────

class TestStrategyFactory:

    def test_get_concat(self):
        s = get_strategy("concat")
        assert isinstance(s, ConcatStrategy)

    def test_get_majority_vote(self):
        s = get_strategy("majority_vote")
        assert isinstance(s, MajorityVoteStrategy)

    def test_get_weighted_vote(self):
        s = get_strategy("weighted_vote")
        assert isinstance(s, WeightedVoteStrategy)

    def test_unknown_strategy(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("nonexistent")


# ──────────────────────────────────────────────────────
# SwarmOrchestrator Integration Tests
# ──────────────────────────────────────────────────────

class TestSwarmOrchestratorStrategies:

    @patch('src.agents.swarm.swarm_orchestrator.AlchemyAgentRepository')
    def test_aggregate_concat(self, mock_repo_cls):
        orch = SwarmOrchestrator()
        result = orch.aggregate_results({"A": "X", "B": "Y"}, strategy="concat")
        assert "Swarm Results" in result

    @patch('src.agents.swarm.swarm_orchestrator.AlchemyAgentRepository')
    def test_aggregate_majority_vote(self, mock_repo_cls):
        orch = SwarmOrchestrator()
        result = orch.aggregate_results(
            {"A": "Bullish outlook", "B": "Buy signal"},
            strategy="majority_vote"
        )
        assert "Council Consensus" in result

    @patch('src.agents.swarm.swarm_orchestrator.AlchemyAgentRepository')
    def test_run_consensus(self, mock_repo_cls):
        orch = SwarmOrchestrator()
        vote = orch.run_consensus({"A": "Buy", "B": "Sell", "C": "Buy signal"})
        assert isinstance(vote, VoteResult)
        assert vote.verdict in [Signal.BULLISH, Signal.BEARISH, Signal.NEUTRAL]

    @patch('src.agents.swarm.swarm_orchestrator.AlchemyAgentRepository')
    def test_configurable_deltas(self, mock_repo_cls):
        orch = SwarmOrchestrator(reward_delta=0.05, penalty_delta=-0.2)
        assert orch.reward_delta == 0.05
        assert orch.penalty_delta == -0.2


class TestVoteResult:

    def test_dataclass(self):
        vr = VoteResult(
            verdict=Signal.BULLISH,
            confidence=0.8,
            vote_counts={"bullish": 3, "bearish": 1},
        )
        assert vr.verdict == Signal.BULLISH
        assert vr.confidence == 0.8
