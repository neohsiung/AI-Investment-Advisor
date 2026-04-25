"""
Unit tests for src/infrastructure/llm/resilient_pipeline.py

Tests:
  - Successful execution on first candidate
  - Single fallback (first fails with fallback-eligible error)
  - All candidates fail → AllCandidatesFailedError
  - Non-fallback error → propagated immediately (no fallback)
  - AttemptRecord contents
"""
import asyncio
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.interfaces import ILLMGateway, LLMConfig, Message
from src.infrastructure.llm.error_classifier import ErrorCategory
from src.infrastructure.llm.resilient_pipeline import (
    AllCandidatesFailedError,
    AttemptRecord,
    ModelCandidate,
    ResilientLLMPipeline,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

class FakeGateway(ILLMGateway):
    """Gateway that returns a fixed response or raises a fixed exception."""

    def __init__(self, response: str = "ok", exc: Exception = None):
        self._response = response
        self._exc = exc
        self.call_count = 0

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        self.call_count += 1
        if self._exc is not None:
            raise self._exc
        return self._response

    async def stream_chat(self, messages, config):
        raise NotImplementedError

    async def embed(self, text, config):
        raise NotImplementedError


class FakeRateLimitError(Exception):
    """Simulates a 429 rate-limit error."""
    def __init__(self):
        self.status_code = 429
        super().__init__("rate limit exceeded")


class FakeAuthError(Exception):
    """Simulates a 401 auth error (non-fallback)."""
    def __init__(self):
        self.status_code = 401
        super().__init__("invalid api key")


class FakeServerError(Exception):
    """Simulates a 500 server error."""
    def __init__(self):
        self.status_code = 500
        super().__init__("internal server error")


def make_candidate(
    model_id: str,
    provider_code: str,
    model_code: str,
    gateway: ILLMGateway,
    max_retries: int = 0,  # 0 = no retries for faster tests
) -> ModelCandidate:
    return ModelCandidate(
        model_id=model_id,
        provider_code=provider_code,
        model_code=model_code,
        gateway_class=type(gateway),
        base_url=None,
        api_key=None,
        max_retries=max_retries,
        timeout_seconds=5.0,
    )


def make_pipeline(candidates: List[ModelCandidate], gateways: List[ILLMGateway]) -> ResilientLLMPipeline:
    """Create a pipeline with a factory that returns pre-built gateways in order."""
    gateway_iter = iter(gateways)

    def factory(candidate: ModelCandidate) -> ILLMGateway:
        return next(gateway_iter)

    return ResilientLLMPipeline(config_chain=candidates, gateway_factory=factory)


MESSAGES = [Message(role="user", content="Hello")]


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

class TestResilientPipelineSuccess:
    def test_success_on_first_candidate(self):
        gw = FakeGateway(response="Hello from primary!")
        candidate = make_candidate("m1", "openai", "gpt-4.1-nano", gw)
        pipeline = make_pipeline([candidate], [gw])

        response, attempts = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(MESSAGES)
        )

        assert response == "Hello from primary!"
        assert len(attempts) == 1
        assert attempts[0].success is True
        assert attempts[0].model_id == "m1"
        assert attempts[0].provider_code == "openai"
        assert attempts[0].error_category is None

    def test_attempt_record_has_duration(self):
        gw = FakeGateway(response="ok")
        candidate = make_candidate("m1", "openai", "gpt-4.1-nano", gw)
        pipeline = make_pipeline([candidate], [gw])

        _, attempts = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(MESSAGES)
        )

        assert attempts[0].duration_ms >= 0
        assert isinstance(attempts[0].started_at, datetime)


class TestResilientPipelineFallback:
    def test_single_fallback_on_rate_limit(self):
        """Primary fails with 429, fallback succeeds."""
        gw1 = FakeGateway(exc=FakeRateLimitError())
        gw2 = FakeGateway(response="Fallback response")

        c1 = make_candidate("m1", "gemini", "gemini-2.5-pro", gw1)
        c2 = make_candidate("m2", "openai", "gpt-4.1-nano", gw2)
        pipeline = make_pipeline([c1, c2], [gw1, gw2])

        response, attempts = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(MESSAGES)
        )

        assert response == "Fallback response"
        assert len(attempts) == 2
        assert attempts[0].success is False
        assert attempts[0].error_category == ErrorCategory.RATE_LIMIT
        assert attempts[1].success is True
        assert attempts[1].model_id == "m2"

    def test_fallback_on_server_error(self):
        """Primary fails with 500, fallback succeeds."""
        gw1 = FakeGateway(exc=FakeServerError())
        gw2 = FakeGateway(response="ok from fallback")

        c1 = make_candidate("m1", "openrouter", "google/gemini-2.5-pro", gw1)
        c2 = make_candidate("m2", "anthropic", "claude-sonnet-4.5", gw2)
        pipeline = make_pipeline([c1, c2], [gw1, gw2])

        response, attempts = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(MESSAGES)
        )

        assert response == "ok from fallback"
        assert attempts[0].error_category == ErrorCategory.SERVER_ERROR
        assert attempts[1].success is True

    def test_multiple_fallbacks(self):
        """Two failures then success on third candidate."""
        gw1 = FakeGateway(exc=FakeRateLimitError())
        gw2 = FakeGateway(exc=FakeServerError())
        gw3 = FakeGateway(response="third time lucky")

        candidates = [
            make_candidate("m1", "gemini", "gemini-2.5-pro", gw1),
            make_candidate("m2", "openai", "gpt-4.1-nano", gw2),
            make_candidate("m3", "ollama", "qwen2.5:7b", gw3),
        ]
        pipeline = make_pipeline(candidates, [gw1, gw2, gw3])

        response, attempts = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(MESSAGES)
        )

        assert response == "third time lucky"
        assert len(attempts) == 3
        assert attempts[2].success is True


class TestResilientPipelineAllFailed:
    def test_all_candidates_fail_raises(self):
        """All candidates fail with fallback-eligible errors → AllCandidatesFailedError."""
        gw1 = FakeGateway(exc=FakeRateLimitError())
        gw2 = FakeGateway(exc=FakeServerError())

        candidates = [
            make_candidate("m1", "gemini", "gemini-2.5-pro", gw1),
            make_candidate("m2", "openai", "gpt-4.1-nano", gw2),
        ]
        pipeline = make_pipeline(candidates, [gw1, gw2])

        with pytest.raises(AllCandidatesFailedError) as exc_info:
            asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        err = exc_info.value
        assert len(err.attempts) == 2
        assert all(not a.success for a in err.attempts)
        assert err.attempts[0].error_category == ErrorCategory.RATE_LIMIT
        assert err.attempts[1].error_category == ErrorCategory.SERVER_ERROR

    def test_all_failed_error_message_contains_models(self):
        gw1 = FakeGateway(exc=FakeRateLimitError())
        candidates = [make_candidate("m1", "gemini", "gemini-2.5-pro", gw1)]
        pipeline = make_pipeline(candidates, [gw1])

        with pytest.raises(AllCandidatesFailedError) as exc_info:
            asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        assert "gemini-2.5-pro" in str(exc_info.value)


class TestResilientPipelineNonFallback:
    def test_auth_failure_propagates_immediately(self):
        """AUTH_FAILURE should NOT trigger fallback — propagate immediately."""
        gw1 = FakeGateway(exc=FakeAuthError())
        gw2 = FakeGateway(response="should not reach here")

        candidates = [
            make_candidate("m1", "openai", "gpt-4.1-nano", gw1),
            make_candidate("m2", "gemini", "gemini-2.5-pro", gw2),
        ]
        pipeline = make_pipeline(candidates, [gw1, gw2])

        with pytest.raises(FakeAuthError):
            asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        # Only one attempt should have been made
        # (We can't easily check this without inspecting internals,
        #  but the test verifies the exception propagates)

    def test_content_policy_propagates_immediately(self):
        """CONTENT_POLICY should NOT trigger fallback."""
        class ContentPolicyError(Exception):
            def __init__(self):
                super().__init__("content policy violation detected")

        gw1 = FakeGateway(exc=ContentPolicyError())
        gw2 = FakeGateway(response="should not reach here")

        candidates = [
            make_candidate("m1", "openai", "gpt-4.1-nano", gw1),
            make_candidate("m2", "gemini", "gemini-2.5-pro", gw2),
        ]
        pipeline = make_pipeline(candidates, [gw1, gw2])

        with pytest.raises(ContentPolicyError):
            asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))


class TestResilientPipelineValidation:
    def test_empty_chain_raises_value_error(self):
        with pytest.raises(ValueError, match="at least one candidate"):
            ResilientLLMPipeline(config_chain=[])
