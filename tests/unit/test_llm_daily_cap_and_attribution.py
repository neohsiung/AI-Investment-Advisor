"""
DD-2026-1030 L2: LLM calls carry their own name, and a daily USD cap stops further calls visibly.
DD-2026-1030 L2：LLM 呼叫要有自己的名字；每日美元上限用完時要明確停止並留標記。

These tests are written first and fail until L2 is implemented.
本檔先寫、實作前會失敗。

Behaviour covered / 涵蓋行為:
  - every get_resilient_gateway(...) caller in src names itself (no anonymous "budget_aware_router" bucket)
  - the confidence compositor names its pipeline
  - cap exhausted -> the gateway is never called, a DailyBudgetExhaustedError is raised (never a fake answer)
  - under the cap, cap disabled (0 / None), and an unreadable spend figure -> the call goes through
  - essential calls (exit / safety paths) are never stopped by the cap
  - the compositor turns an exhausted cap into a marked fallback, not a plausible score
"""
import ast
import asyncio
import logging
import pathlib
from unittest.mock import MagicMock

import pytest

from src.domain.interfaces import ILLMGateway
from src.infrastructure.llm.resilient_pipeline import ModelCandidate, ResilientLLMPipeline

SRC = pathlib.Path(__file__).resolve().parents[2] / "src"


class _Gateway(ILLMGateway):
    calls = 0

    async def chat(self, messages, config):
        type(self).calls += 1
        return '{"score": 7}'

    async def stream_chat(self, messages, config):
        raise NotImplementedError

    async def embed(self, text, config):
        raise NotImplementedError


def _candidate():
    return ModelCandidate(model_id="m", provider_code="p", model_code="fast", gateway_class=_Gateway, max_retries=0)


def _pipeline(**kw):
    _Gateway.calls = 0
    return ResilientLLMPipeline(config_chain=[_candidate()], agent_name="t", tier="fast", **kw)


def _cap(cap_usd, spent):
    from src.infrastructure.llm.daily_spend_cap import DailySpendCap
    return DailySpendCap(cap_usd=cap_usd, spent_today_usd=spent)


def _run(pipeline):
    return asyncio.run(pipeline.execute([{"role": "user", "content": "hi"}]))


# ── attribution ──────────────────────────────────────────────────────────────

def test_every_gateway_caller_names_itself():
    """A call to get_resilient_gateway without agent_name lands in the anonymous bucket (the 10-15 step hid there)."""
    offenders = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get_resilient_gateway"
                    and "agent_name" not in {k.arg for k in node.keywords}):
                offenders.append(f"{path.relative_to(SRC.parent)}:{node.lineno}")
    assert offenders == []


def test_compositor_names_its_pipeline():
    from src.services.confidence_compositor_service import CompositorService
    router = MagicMock()
    svc = CompositorService.__new__(CompositorService)
    svc.user_id, svc._router, svc._pipelines = "u", router, {}
    asyncio.run(svc._get_pipeline("fast"))
    assert router.get_resilient_gateway.call_args.kwargs.get("agent_name") == "confidence_compositor"


# ── daily cap ────────────────────────────────────────────────────────────────

def test_exhausted_cap_stops_the_call_and_says_so(caplog):
    from src.infrastructure.llm.daily_spend_cap import DailyBudgetExhaustedError
    p = _pipeline(daily_cap=_cap(0.10, lambda: 0.10))
    with caplog.at_level(logging.WARNING), pytest.raises(DailyBudgetExhaustedError) as e:
        _run(p)
    assert _Gateway.calls == 0
    assert e.value.cap_usd == 0.10 and e.value.spent_usd == 0.10
    assert "llm_daily_cap_exhausted" in caplog.text


def test_under_the_cap_the_call_goes_through():
    _run(_pipeline(daily_cap=_cap(0.10, lambda: 0.05)))
    assert _Gateway.calls == 1


@pytest.mark.parametrize("cap", [0, None])
def test_cap_disabled_never_stops_calls(cap):
    _run(_pipeline(daily_cap=_cap(cap, lambda: 999.0)))
    assert _Gateway.calls == 1


def test_unreadable_spend_lets_the_call_through_but_warns(caplog):
    def boom():
        raise RuntimeError("db down")
    with caplog.at_level(logging.WARNING):
        _run(_pipeline(daily_cap=_cap(0.10, boom)))
    assert _Gateway.calls == 1
    assert "llm_daily_cap_unreadable" in caplog.text


def test_essential_calls_ignore_the_cap():
    """Exit / safety paths must still be able to think when the day's budget is gone."""
    _run(_pipeline(daily_cap=_cap(0.10, lambda: 5.0), essential=True))
    assert _Gateway.calls == 1


def test_compositor_marks_an_exhausted_cap_instead_of_inventing_a_score():
    from src.services.confidence_compositor_service import CompositorService
    svc = CompositorService.__new__(CompositorService)
    svc.user_id, svc._router = "u", MagicMock()
    svc._pipelines = {"fast": _pipeline(daily_cap=_cap(0.10, lambda: 0.10))}
    _score, factors = asyncio.run(svc._score_via_llm("AMZN", "fundamental", "score {ticker}", "fast"))
    assert _Gateway.calls == 0
    assert "daily" in str(factors.get("_fallback_reason", "")).lower()
