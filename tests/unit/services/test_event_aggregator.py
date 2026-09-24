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
