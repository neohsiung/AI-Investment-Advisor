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


# ── default cap + essential marks (DD-2026-1030 L2, wiring to every pipeline) ─

def _patch_default_cap(monkeypatch, cap):
    monkeypatch.setattr("src.infrastructure.llm.resilient_pipeline.default_cap", lambda user_id: cap)


def test_pipeline_without_daily_cap_resolves_it_from_settings(monkeypatch):
    """The ~25 call sites that build a pipeline directly must be covered without being edited one by one."""
    from src.infrastructure.llm.daily_spend_cap import DailyBudgetExhaustedError
    _patch_default_cap(monkeypatch, _cap(0.10, lambda: 0.10))
    with pytest.raises(DailyBudgetExhaustedError):
        _run(_pipeline())
    assert _Gateway.calls == 0


def test_explicit_none_cap_means_disabled_not_default(monkeypatch):
    _patch_default_cap(monkeypatch, _cap(0.10, lambda: 0.10))
    _run(_pipeline(daily_cap=None))
    assert _Gateway.calls == 1


def test_default_cap_unset_in_settings_lets_calls_through(monkeypatch):
    _patch_default_cap(monkeypatch, None)
    _run(_pipeline())
    assert _Gateway.calls == 1


def _sentinel_pipeline_kwargs(monkeypatch, agent_name):
    """Run SentinelService._call_agent_llm with a fake pipeline class; return the kwargs it was built with."""
    from unittest.mock import AsyncMock
    from src.services.sentinel_service import SentinelService
    built = {}

    class _FakePipeline:
        def __init__(self, **kw):
            built.update(kw)
        execute = AsyncMock(return_value=("{}", []))

    monkeypatch.setattr("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline", _FakePipeline)
    monkeypatch.setattr("src.infrastructure.llm.llm_config_chain.build_config_chain", lambda uid, tier: [_candidate()])
    monkeypatch.setattr("src.infrastructure.llm.auto_tier.resolve_effective_tier", lambda tier, *a, **k: tier)
    monkeypatch.setattr("src.services.hard_token_budget_guard_service.HardTokenBudgetGuardService",
                        lambda user_id: MagicMock(should_allow_llm=lambda task_type: (True, "")))
    svc = SentinelService.__new__(SentinelService)
    svc.user_id, svc.model_router = "u", MagicMock()
    asyncio.run(svc._call_agent_llm(agent_name, {}, tier="fast"))
    return built


@pytest.mark.parametrize("agent", ["Sentinel", "Risk"])
def test_sentinel_risk_calls_are_essential(monkeypatch, agent):
    assert _sentinel_pipeline_kwargs(monkeypatch, agent).get("essential") is True


@pytest.mark.parametrize("agent", ["Thematic", "Momentum", "Macro"])
def test_other_sentinel_agents_stay_under_the_cap(monkeypatch, agent):
    assert _sentinel_pipeline_kwargs(monkeypatch, agent).get("essential", False) is False


def test_exit_compositor_llm_is_essential():
    from src.services.exit_compositor_service import ExitCompositorService
    assert ExitCompositorService(user_id="u")._llm.essential is True


def test_compositor_passes_essential_to_its_router():
    from src.services.confidence_compositor_service import CompositorService
    router = MagicMock()
    svc = CompositorService.__new__(CompositorService)
    svc.user_id, svc._router, svc._pipelines, svc.essential = "u", router, {}, True
    asyncio.run(svc._get_pipeline("fast"))
    assert router.get_resilient_gateway.call_args.kwargs.get("essential") is True


# ── review follow-ups: council / action extractor exemption, cap cache ────────

def _calls_in(path, func_name, attr):
    tree = ast.parse((SRC.parent / path).read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)) and fn.name == func_name:
            return [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == attr]
    raise AssertionError(f"{func_name} not found in {path}")


def test_sentinel_mode_council_calls_say_whether_they_are_essential():
    """A stop-loss council must still run its Risk veto and CIO when the day's budget is gone."""
    calls = _calls_in("src/services/council_service.py", "_run_debate_logic", "_call_agent_llm")
    assert calls and all("essential" in {k.arg for k in c.keywords} for c in calls)


@pytest.mark.parametrize("essential", [True, False])
def test_council_agent_call_passes_essential_to_pipeline(monkeypatch, essential):
    from unittest.mock import AsyncMock
    from src.services.council_service import CouncilService
    built = {}

    class _Fake:
        def __init__(self, **kw):
            built.update(kw)
        execute = AsyncMock(return_value=("ok", []))

    monkeypatch.setattr("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline", _Fake)
    monkeypatch.setattr("src.infrastructure.llm.llm_config_chain.build_config_chain", lambda uid, tier: [_candidate()])
    svc = CouncilService.__new__(CouncilService)
    svc.user_id = "u"
    asyncio.run(svc._call_agent_llm("Risk", {}, tier="fast", essential=essential))
    assert built.get("essential") is essential


def test_action_extractor_is_essential():
    """It turns an already-paid council decision (possibly an exit) into orders; dropping it loses the decision."""
    path = SRC.parent / "src/agents/action_extractor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pipes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", getattr(n.func, "attr", "")) == "ResilientLLMPipeline"]
    assert pipes and all(
        any(k.arg == "essential" and getattr(k.value, "value", None) is True for k in c.keywords) for c in pipes)


class _FakeRepo:
    reads = 0

    def get(self, user_id, key, default=None):
        type(self).reads += 1
        return 0.25


def test_default_cap_is_cached_for_a_short_ttl_not_read_per_call(monkeypatch):
    from src.infrastructure.llm import daily_spend_cap as m
    _FakeRepo.reads = 0
    clock = [1000.0]
    monkeypatch.setattr(m, "AlchemySettingsRepository", _FakeRepo)
    monkeypatch.setattr(m, "_now", lambda: clock[0])
    m.clear_default_cap_cache()
    first = m.default_cap("u")
    assert first is not None and first.cap_usd == 0.25
    m.default_cap("u")
    assert _FakeRepo.reads == 1
    clock[0] += m.CAP_CACHE_TTL_SECONDS + 1
    m.default_cap("u")
    assert _FakeRepo.reads == 2


def test_unreadable_setting_is_not_cached(monkeypatch, caplog):
    from src.infrastructure.llm import daily_spend_cap as m

    class _Boom:
        reads = 0

        def get(self, *a, **k):
            type(self).reads += 1
            raise RuntimeError("db down")

    monkeypatch.setattr(m, "AlchemySettingsRepository", _Boom)
    m.clear_default_cap_cache()
    with caplog.at_level(logging.WARNING):
        assert m.default_cap("u") is None
        assert m.default_cap("u") is None
    assert _Boom.reads == 2
    assert "llm_daily_cap_unreadable" in caplog.text


def test_spend_reading_is_cached_between_calls(monkeypatch):
    from src.infrastructure.llm import daily_spend_cap as m
    reads = []
    clock = [1000.0]
    monkeypatch.setattr(m, "AlchemySettingsRepository", _FakeRepo)
    monkeypatch.setattr(m, "_now", lambda: clock[0])
    monkeypatch.setattr(m, "_read_spent_today", lambda engine: reads.append(1) or 0.01)
    m.clear_default_cap_cache()
    cap = m.default_cap("u", engine=object())
    cap.check()
    cap.check()
    assert len(reads) == 1
