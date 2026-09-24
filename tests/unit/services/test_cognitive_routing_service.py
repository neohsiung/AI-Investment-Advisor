"""
Unit tests for CognitiveRoutingService and Issue-to-Tier matrix.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from src.domain.cognitive_issue_type import CognitiveIssueType, IssueRoutingSpec
from src.services.cognitive_routing_service import CognitiveRoutingService
from src.infrastructure.llm.arbiter_client import ArbiterDecision


@pytest.fixture
def mock_settings_repo():
    repo = MagicMock()
    repo.get.return_value = None
    return repo


@pytest.fixture
def mock_arbiter():
    arbiter = MagicMock()
    arbiter.decide = AsyncMock()
    return arbiter


@pytest.fixture
def routing_service(mock_settings_repo, mock_arbiter):
    # Ensure fresh cache
    CognitiveRoutingService._cached_defaults = None
    return CognitiveRoutingService(
        settings_repo=mock_settings_repo,
        arbiter_client=mock_arbiter
    )


def test_load_defaults(routing_service):
    """Verify loading from YAML config populated standard issue types."""
    specs = routing_service.list_all_routing_specs()
    assert len(specs) >= 10

    # Level 0 checks
    intent_spec = routing_service.get_routing_spec(CognitiveIssueType.INTENT_ROUTING)
    assert intent_spec.default_tier == "reflex"
    assert intent_spec.is_reflex_eligible is True
    assert intent_spec.confidence_threshold == 0.88

    # Level 1 checks
    news_spec = routing_service.get_routing_spec(CognitiveIssueType.NEWS_SUMMARIZATION)
    assert news_spec.default_tier == "fast"
    assert news_spec.is_reflex_eligible is False

    # Level 2 checks
    fund_spec = routing_service.get_routing_spec(CognitiveIssueType.FUNDAMENTAL_ANALYSIS)
    assert fund_spec.default_tier == "smart"

    # Level 3 checks
    cio_spec = routing_service.get_routing_spec(CognitiveIssueType.CIO_DECISION)
    assert cio_spec.default_tier == "advanced"


def test_should_use_reflex(routing_service):
    """Verify reflex tier detection for micro-decisions."""
    assert routing_service.should_use_reflex(CognitiveIssueType.INTENT_ROUTING) is True
    assert routing_service.should_use_reflex(CognitiveIssueType.SENTINEL_BREACH) is True
    assert routing_service.should_use_reflex(CognitiveIssueType.NEWS_RELEVANCE) is True
    assert routing_service.should_use_reflex(CognitiveIssueType.FUNDAMENTAL_ANALYSIS) is False
    assert routing_service.should_use_reflex(CognitiveIssueType.CIO_DECISION) is False


def test_user_override_support(routing_service, mock_settings_repo):
    """Verify tenant-specific overrides can alter default tier and confidence."""
    user_id = "tenant_123"
    mock_settings_repo.get.return_value = json.dumps({
        "intent_routing": {
            "default_tier": "fast",
            "confidence_threshold": 0.95
        }
    })

    spec = routing_service.get_routing_spec(CognitiveIssueType.INTENT_ROUTING, user_id=user_id)
    assert spec.default_tier == "fast"
    assert spec.confidence_threshold == 0.95

    # Should not affect another user
    mock_settings_repo.get.return_value = None
    other_spec = routing_service.get_routing_spec(CognitiveIssueType.INTENT_ROUTING, user_id="other_user")
    assert other_spec.default_tier == "reflex"


def test_unknown_issue_fallback(routing_service):
    """Verify unknown issue gracefully falls back to fast tier (Constraint #0 safe)."""
    spec = routing_service.get_routing_spec("unknown_nonexistent_task")
    assert spec.default_tier == "fast"
    assert spec.fallback_tier == "smart"


@pytest.mark.asyncio
async def test_evaluate_reflex_issue_dispatch(routing_service, mock_arbiter):
    """Verify evaluate_reflex_issue passes spec confidence threshold to Arbiter."""
    mock_arbiter.decide.return_value = ArbiterDecision(
        decision_id="dec_test123",
        choice="P1",
        confidence=0.95,
        is_escalated=False,
        tier="reflex",
        state_hash="abc",
        latency_ms=45.0
    )

    decision = await routing_service.evaluate_reflex_issue(
        issue_type=CognitiveIssueType.SENTINEL_BREACH,
        domain="sentinel",
        state={"vix": 25.0},
        question_key="priority",
        question_spec={"type": "choice"},
        system2_fallback_prompt="escalate prompt",
        deterministic_default="P2"
    )

    assert decision.choice == "P1"
    assert decision.confidence == 0.95
    assert decision.tier == "reflex"
    mock_arbiter.decide.assert_called_once()
    # Check that sentinel threshold (0.92) was passed
    args, kwargs = mock_arbiter.decide.call_args
    assert kwargs["confidence_threshold"] == 0.92
