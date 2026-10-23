"""LLM credit-limit handling: classify, record, alert. / LLM 額度用盡：分類、記錄、告警。"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.domain.interfaces import ILLMGateway, Message
from src.infrastructure.llm import credit_signal
from src.infrastructure.llm.error_classifier import ErrorCategory, classify_error, should_fallback
from src.infrastructure.llm.resilient_pipeline import ModelCandidate, ResilientLLMPipeline
from src.services.self_ops_service import SelfOpsService, _NAMED_CHECKS

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


class _Err(Exception):
    def __init__(self, msg, status=None):
        self.status_code = status
        super().__init__(msg)


# ── classification ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("exc", [
    _Err("payment required", 402),
    _Err("anything", 402),
    _Err("Key limit exceeded (weekly limit)", 403),
    _Err("Key limit exceeded", 429),
    _Err("insufficient credits"),
    _Err("openrouter: out of credits"),
])
def test_credit_limit_wording_and_status_are_classified(exc):
    assert classify_error(exc) is ErrorCategory.CREDIT_LIMIT


@pytest.mark.parametrize("exc,expected", [
    (_Err("rate limit exceeded", 429), ErrorCategory.RATE_LIMIT),
    (_Err("quota exceeded"), ErrorCategory.RATE_LIMIT),               # unchanged: still a rate limit
    (_Err("invalid api key", 401), ErrorCategory.AUTH_FAILURE),
    (_Err("internal server error", 500), ErrorCategory.SERVER_ERROR),
])
def test_existing_categories_are_unchanged(exc, expected):
    assert classify_error(exc) is expected


def test_credit_limit_is_not_fallback_eligible():
    """Another candidate on the same key fails the same way, and a different provider would bypass the spend cap."""
    assert should_fallback(ErrorCategory.CREDIT_LIMIT) is False


# ── signal ────────────────────────────────────────────────────────────────────

class _Redis:
    def __init__(self):
        self.store = {}

    def set(self, k, v, ex=None):
        self.store[k] = v

    def get(self, k):
        return self.store.get(k)


@pytest.fixture()
def redis(monkeypatch):
    r = _Redis()
    monkeypatch.setattr(credit_signal, "get_redis_sync", lambda: r)
    return r


def test_nothing_recorded_is_ok(redis):
    assert credit_signal.probe(NOW)[0] is True


def test_recent_refusal_is_critical(redis):
    credit_signal.record(NOW - timedelta(minutes=10))
    ok, detail, sev = credit_signal.probe(NOW)
    assert ok is False and sev == "critical" and "10 min ago" in detail


def test_old_refusal_clears_itself(redis):
    credit_signal.record(NOW - timedelta(minutes=90))
    assert credit_signal.probe(NOW)[0] is True


def test_unreadable_redis_is_unknown_not_fine(monkeypatch):
    def boom():
        raise RuntimeError("redis down")
    monkeypatch.setattr(credit_signal, "get_redis_sync", boom)
    ok, _, sev = credit_signal.probe(NOW)
    assert ok is False and sev == "warning"


def test_record_never_raises_into_the_llm_path(monkeypatch):
    def boom():
        raise RuntimeError("redis down")
    monkeypatch.setattr(credit_signal, "get_redis_sync", boom)
    credit_signal.record(NOW)                                         # must not raise


# ── pipeline hook ─────────────────────────────────────────────────────────────

class _Gateway(ILLMGateway):
    def __init__(self, exc=None):
        self._exc, self.calls = exc, 0

    async def chat(self, messages, config):
        self.calls += 1
        if self._exc:
            raise self._exc
        return "ok"

    async def stream_chat(self, messages, config):
        raise NotImplementedError

    async def embed(self, text, config):
        raise NotImplementedError


def _candidate(gw, mid):
    return ModelCandidate(model_id=mid, provider_code="p", model_code="m", gateway_class=type(gw), base_url=None,
                          api_key=None, max_retries=0, timeout_seconds=5.0)


def test_pipeline_records_credit_limit_and_does_not_fall_back(redis):
    g1, g2 = _Gateway(_Err("Key limit exceeded", 403)), _Gateway()
    gws = iter([g1, g2])
    pipe = ResilientLLMPipeline(config_chain=[_candidate(g1, "a"), _candidate(g2, "b")],
                                gateway_factory=lambda c: next(gws))
    with pytest.raises(_Err):
        asyncio.get_event_loop().run_until_complete(pipe.execute([Message(role="user", content="hi")]))
    assert g2.calls == 0                                              # no fallback to a second candidate
    assert credit_signal.KEY in redis.store


def test_pipeline_does_not_record_for_other_errors(redis):
    g1 = _Gateway(_Err("invalid api key", 401))
    pipe = ResilientLLMPipeline(config_chain=[_candidate(g1, "a")], gateway_factory=lambda c: g1)
    with pytest.raises(_Err):
        asyncio.get_event_loop().run_until_complete(pipe.execute([Message(role="user", content="hi")]))
    assert redis.store == {}


# ── self-ops wiring ───────────────────────────────────────────────────────────

def test_self_ops_named_check_is_critical_when_refused(redis):
    credit_signal.record()
    assert "probe" in _NAMED_CHECKS["llm_credit_available"]
    br = SelfOpsService(user_id="u")._check_named(None, "check:llm_credit_available", "llm_credit_available")
    assert br["severity"] == "critical" and "credit" in br["detail"].lower()


def test_self_ops_named_check_none_when_fine(redis):
    assert SelfOpsService(user_id="u")._check_named(None, "check:llm_credit_available", "llm_credit_available") is None
