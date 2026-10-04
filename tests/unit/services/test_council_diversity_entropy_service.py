"""
Unit tests for CouncilDiversityEntropyService (A4 Engine).
"""
import pytest
import math

from src.services.council_diversity_entropy_service import (
    AgentVote,
    CouncilDiversityEntropyService,
    DiversityLevel,
    VoteStance,
)
from src.api.v1.schemas.council_diversity_schemas import (
    AgentVoteSchema,
    DiversityEvaluationRequest,
)


class MockSettingsRepo:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, user_id: str, key: str, default=None):
        return self.data.get(key, default)


def test_perfectly_balanced_diversity():
    """Test Shannon entropy calculation under perfectly balanced votes (1/3, 1/3, 1/3)."""
    service = CouncilDiversityEntropyService()

    votes = [
        AgentVote(agent_name="Technical", stance=VoteStance.BUY, weight=1.0),
        AgentVote(agent_name="Fundamental", stance=VoteStance.HOLD, weight=1.0),
        AgentVote(agent_name="Risk", stance=VoteStance.SELL, weight=1.0),
    ]

    assessment = service.evaluate_diversity(votes, symbol="AAPL")

    assert pytest.approx(assessment.distribution["BUY"], 0.01) == 1.0 / 3.0
    assert pytest.approx(assessment.distribution["HOLD"], 0.01) == 1.0 / 3.0
    assert pytest.approx(assessment.distribution["SELL"], 0.01) == 1.0 / 3.0
    assert pytest.approx(assessment.shannon_entropy, 0.01) == math.log(3.0)
    assert pytest.approx(assessment.normalized_entropy, 0.01) == 1.0
    assert assessment.diversity_level == DiversityLevel.DIVERSE
    assert assessment.groupthink_detected is False
    assert assessment.recommended_haircut_pct == 0.0
    assert assessment.devils_advocate_challenge is None


def test_extreme_bullish_groupthink_warning():
    """Test groupthink detection when council unanimously votes BUY."""
    service = CouncilDiversityEntropyService()

    votes = [
        AgentVote(agent_name="Technical", stance=VoteStance.BUY, weight=1.0, confidence=1.0),
        AgentVote(agent_name="Fundamental", stance=VoteStance.BUY, weight=1.0, confidence=1.0),
        AgentVote(agent_name="Sentiment", stance=VoteStance.BUY, weight=1.0, confidence=0.9),
        AgentVote(agent_name="Valuation", stance=VoteStance.BUY, weight=1.0, confidence=1.0),
        AgentVote(agent_name="Risk", stance=VoteStance.BUY, weight=1.0, confidence=0.8),
    ]

    assessment = service.evaluate_diversity(votes, symbol="NVDA")

    assert assessment.distribution["BUY"] == 1.0
    assert assessment.normalized_entropy == 0.0
    assert assessment.diversity_level == DiversityLevel.GROUPTHINK_WARNING
    assert assessment.groupthink_detected is True
    assert assessment.dominant_stance == "BUY"
    assert pytest.approx(assessment.recommended_haircut_pct, 0.01) == 0.25

    # Verify Devil's Advocate packet
    challenge = assessment.devils_advocate_challenge
    assert challenge is not None
    assert challenge.dominant_stance == "BUY"
    assert "NVDA" in challenge.challenge_headline
    assert len(challenge.counter_arguments) >= 3
    assert len(challenge.required_checkpoints) >= 2


def test_extreme_bearish_groupthink_warning():
    """Test groupthink detection when council unanimously panics and votes SELL."""
    service = CouncilDiversityEntropyService()

    votes = [
        AgentVote(agent_name="Technical", stance=VoteStance.SELL, weight=1.0),
        AgentVote(agent_name="Risk", stance=VoteStance.SELL, weight=1.0),
        AgentVote(agent_name="Macro", stance=VoteStance.SELL, weight=1.0),
    ]

    assessment = service.evaluate_diversity(votes, symbol="TSLA")

    assert assessment.groupthink_detected is True
    assert assessment.dominant_stance == "SELL"
    challenge = assessment.devils_advocate_challenge
    assert challenge is not None
    assert "Short Squeeze" in "".join(challenge.counter_arguments) or "軋空" in "".join(challenge.counter_arguments)


def test_moderate_consensus():
    """Test moderate consensus where opinions lean but maintain diversity."""
    service = CouncilDiversityEntropyService()

    # 60% BUY, 40% HOLD
    votes = [
        AgentVote(agent_name="Technical", stance=VoteStance.BUY, weight=1.5),
        AgentVote(agent_name="Fundamental", stance=VoteStance.HOLD, weight=1.0),
    ]

    assessment = service.evaluate_diversity(votes, symbol="MSFT")

    assert assessment.diversity_level == DiversityLevel.MODERATE_CONSENSUS
    assert assessment.groupthink_detected is False
    assert assessment.recommended_haircut_pct == 0.0


def test_devils_advocate_prompt_injection():
    """Test injection of Devil's Advocate packet into CIO prompt."""
    service = CouncilDiversityEntropyService()

    votes = [
        AgentVote(agent_name="Agent1", stance=VoteStance.BUY, weight=1.0),
        AgentVote(agent_name="Agent2", stance=VoteStance.BUY, weight=1.0),
    ]
    assessment = service.evaluate_diversity(votes, symbol="GOOGL")
    base_prompt = "You are the Chief Investment Officer. Deliberate and render your final verdict."

    injected_prompt = service.inject_devils_advocate_into_prompt(assessment, base_prompt)

    assert "COUNCIL GROUPTHINK SHIELDER" in injected_prompt
    assert "GOOGL" in injected_prompt
    assert "魔鬼代言人強制反面論證" in injected_prompt
    assert "CIO 終審必須回應之檢查點" in injected_prompt


def test_conviction_haircut():
    """Test application of protective conviction haircut."""
    service = CouncilDiversityEntropyService()

    votes = [
        AgentVote(agent_name="Agent1", stance=VoteStance.BUY, weight=1.0),
        AgentVote(agent_name="Agent2", stance=VoteStance.BUY, weight=1.0),
    ]
    assessment = service.evaluate_diversity(votes, symbol="AMZN")

    haircut_conv = service.apply_conviction_haircut(0.80, assessment)
    # 0.80 * (1 - 0.25) = 0.60
    assert pytest.approx(haircut_conv, 0.01) == 0.60

    # Normal diverse state should not haircut
    diverse_votes = [
        AgentVote(agent_name="Agent1", stance=VoteStance.BUY, weight=1.0),
        AgentVote(agent_name="Agent2", stance=VoteStance.SELL, weight=1.0),
    ]
    diverse_assessment = service.evaluate_diversity(diverse_votes, symbol="AMZN")
    assert service.apply_conviction_haircut(0.80, diverse_assessment) == 0.80


def test_api_endpoint_flow():
    """Test evaluate_council_diversity endpoint function."""
    from src.api.v1.endpoints.council import evaluate_council_diversity

    service = CouncilDiversityEntropyService()
    req = DiversityEvaluationRequest(
        symbol="META",
        votes=[
            AgentVoteSchema(agent_name="Technical", stance="BUY", weight=1.0, confidence=0.9),
            AgentVoteSchema(agent_name="Fundamental", stance="BUY", weight=1.0, confidence=0.8),
            AgentVoteSchema(agent_name="Valuation", stance="BUY", weight=1.0, confidence=0.85),
            AgentVoteSchema(agent_name="Sentiment", stance="BUY", weight=1.0, confidence=0.95),
        ],
    )

    res = evaluate_council_diversity(payload=req, service=service)
    assert res.symbol == "META"
    assert res.dominant_stance == "BUY"
    assert res.groupthink_detected is True
    assert res.diversity_level == "GROUPTHINK_WARNING"
    assert res.devils_advocate_challenge is not None
    assert len(res.devils_advocate_challenge.counter_arguments) > 0
