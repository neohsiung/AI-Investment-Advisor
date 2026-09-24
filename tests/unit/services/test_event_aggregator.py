"""Tests for EventAggregator, tier classification, and ReDoS-safe thinking trace sanitization."""

import pytest
import time
from src.services.event_aggregator import EventAggregator, _strip_thinking_traces, EventQueue


def test_strip_thinking_traces_basic():
    """Verify normal texts remain intact and think tags are removed."""
    raw = "Normal text without thinking traces."
    assert _strip_thinking_traces(raw) == raw

    with_think = "<think>some hidden reasoning</think>Market alert: TSLA down 5%"
    assert _strip_thinking_traces(with_think) == "Market alert: TSLA down 5%"

    multiple_think = "<think>t1</think>part 1<think>t2</think>part 2"
    assert _strip_thinking_traces(multiple_think) == "part 1part 2"


def test_strip_thinking_traces_heres_a_thinking_process():
    """Verify 'here's a thinking process:' blocks are properly removed."""
    text = "here's a thinking process:\n1. analyze stock\n2. calculate risk\n\nFinal Recommendation: BUY"
    assert _strip_thinking_traces(text) == "Final Recommendation: BUY"


def test_strip_thinking_traces_unclosed():
    """Verify unclosed think blocks don't cause infinite loop or crash."""
    text = "<think>unclosed trailing text"
    assert _strip_thinking_traces(text) == ""

    text2 = "prefix <think>unclosed trailing text"
    assert _strip_thinking_traces(text2) == "prefix "


def test_strip_thinking_traces_redos_resistance():
    """Verify linear execution time even with adversarial repetitive inputs."""
    # Attack payload with repeated tokens that would trigger polynomial regex backtracking
    evil_input = "<think>" * 5000 + "unclosed"
    start = time.perf_counter()
    res = _strip_thinking_traces(evil_input)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1  # Must finish within 100ms
    assert res == ""

    evil_marker = "here's a thinking process: " * 5000 + "tail"
    start = time.perf_counter()
    res2 = _strip_thinking_traces(evil_marker)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1
    assert res2 == ""


def test_classify_tier_with_thinking_traces():
    """Verify classify_tier correctly sanitizes thinking traces without false P0 classification."""
    # If thinking trace contains 'fraud', but clean content doesn't, it shouldn't trigger P0
    content = {
        "text": "<think>Thinking about fraud scenarios that don't apply.</think>Routine portfolio update."
    }
    tier, priority = EventAggregator.classify_tier("report", content)
    assert tier != EventQueue.TIER_P0


@pytest.mark.asyncio
async def test_classify_tier_with_arbiter():
    """Verify classify_tier_with_arbiter routes to Jev and maps priority."""
    from unittest.mock import AsyncMock, MagicMock
    from src.infrastructure.llm.arbiter_client import ArbiterDecision

    mock_svc = MagicMock()
    mock_svc.should_use_reflex.return_value = True
    mock_svc.evaluate_reflex_issue = AsyncMock(return_value=ArbiterDecision(
        decision_id="dec_456",
        choice="P1",
        confidence=0.96,
        is_escalated=False,
        tier="reflex",
        state_hash="def",
        latency_ms=35.0
    ))

    content = {"headline": "Surprise rate cut announced"}
    tier, priority = await EventAggregator.classify_tier_with_arbiter(
        event_type="market_news",
        content=content,
        cognitive_routing_service=mock_svc
    )

    assert tier == EventQueue.TIER_P1
    assert priority == 80
    mock_svc.evaluate_reflex_issue.assert_called_once()
