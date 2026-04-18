"""
Integration tests for multi-provider fallback pipeline (Phase C).

Tests the full chain: ModelCandidate list → ResilientLLMPipeline → fallback logic.

Scenarios:
  1. Gemini 429 → fallback to Claude (mock gateway)
  2. Ollama connection refused → fallback to OpenAI
  3. CIO Agent forbid_local=True → Ollama candidate filtered
  4. forbid_fallback=True → primary fails, raises immediately (no fallback)
  5. All candidates fail → AllCandidatesFailedError
  6. Provider/Model CRUD + 409 conflict (Model referenced by Tier cannot be deleted)

Design: docs/architecture/multi_provider_multi_model_design.md §8.4 C3
"""
from __future__ import annotations

import asyncio
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
# Shared helpers
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
    """Simulates a 429 rate-limit error (should trigger fallback)."""
    def __init__(self):
        self.status_code = 429
        super().__init__("rate limit exceeded")


class FakeConnectionError(Exception):
    """Simulates a connection refused error (should trigger fallback)."""
    def __init__(self):
        self.status_code = 503
        super().__init__("connection refused")


class FakeAuthError(Exception):
    """Simulates a 401 auth error (should NOT trigger fallback)."""
    def __init__(self):
        self.status_code = 401
        super().__init__("invalid api key")


def make_candidate(
    model_id: str,
    provider_code: str,
    model_code: str,
    gateway: ILLMGateway,
    max_retries: int = 0,
) -> ModelCandidate:
    """Helper to build a ModelCandidate with a pre-built gateway."""
    cand = ModelCandidate(
        model_id=model_id,
        provider_code=provider_code,
        model_code=model_code,
        gateway_class=type(gateway),
        base_url=None,
        api_key=None,
        max_retries=max_retries,
        timeout_seconds=5.0,
    )
    return cand


def make_pipeline(
    candidates_and_gateways: List[tuple],
) -> tuple:
    """
    Build a ResilientLLMPipeline where each candidate uses a pre-built gateway.

    candidates_and_gateways: list of (ModelCandidate, FakeGateway)
    Returns (pipeline, [gateways])
    """
    candidates = [c for c, _ in candidates_and_gateways]
    gateways = [g for _, g in candidates_and_gateways]

    # Use a gateway_factory that returns gateways in order
    call_idx = [0]
    def fake_factory(candidate):
        idx = call_idx[0]
        call_idx[0] += 1
        return gateways[idx]

    pipeline = ResilientLLMPipeline(
        config_chain=candidates,
        gateway_factory=fake_factory,
    )
    return pipeline, gateways


MESSAGES = [{"role": "user", "content": "test"}]


# ──────────────────────────────────────────────────────────────────────
# Scenario 1: Gemini 429 → fallback to Claude
# ──────────────────────────────────────────────────────────────────────

class TestScenario1GeminiFallbackToClaude:
    """Gemini returns 429 → pipeline falls back to Claude."""

    def test_gemini_429_falls_back_to_claude(self):
        gemini_gw = FakeGateway(exc=FakeRateLimitError())
        claude_gw = FakeGateway(response="claude response")

        gemini = make_candidate("m1", "gemini", "gemini-2.5-pro", gemini_gw)
        claude = make_candidate("m2", "anthropic", "claude-sonnet-4.5", claude_gw)

        pipeline, gateways = make_pipeline([(gemini, gemini_gw), (claude, claude_gw)])

        response, attempts = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(MESSAGES)
        )

        assert response == "claude response"
        assert gemini_gw.call_count == 1
        assert claude_gw.call_count == 1

    def test_attempt_records_show_gemini_error_and_claude_success(self):
        gemini_gw = FakeGateway(exc=FakeRateLimitError())
        claude_gw = FakeGateway(response="ok")

        gemini = make_candidate("m1", "gemini", "gemini-2.5-pro", gemini_gw)
        claude = make_candidate("m2", "anthropic", "claude-sonnet-4.5", claude_gw)

        pipeline, _ = make_pipeline([(gemini, gemini_gw), (claude, claude_gw)])

        _, attempts = asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        assert len(attempts) == 2
        assert attempts[0].success is False
        assert attempts[0].model_code == "gemini-2.5-pro"
        assert attempts[1].success is True
        assert attempts[1].model_code == "claude-sonnet-4.5"


# ──────────────────────────────────────────────────────────────────────
# Scenario 2: Ollama connection refused → fallback to OpenAI
# ──────────────────────────────────────────────────────────────────────

class TestScenario2OllamaFallbackToOpenAI:
    """Ollama connection refused → pipeline falls back to OpenAI."""

    def test_ollama_connection_refused_falls_back_to_openai(self):
        ollama_gw = FakeGateway(exc=FakeConnectionError())
        openai_gw = FakeGateway(response="openai response")

        ollama = make_candidate("m1", "ollama", "qwen2.5:7b", ollama_gw)
        openai = make_candidate("m2", "openai", "gpt-4.1-nano", openai_gw)

        pipeline, _ = make_pipeline([(ollama, ollama_gw), (openai, openai_gw)])

        response, attempts = asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        assert response == "openai response"
        assert ollama_gw.call_count == 1
        assert openai_gw.call_count == 1

    def test_attempt_records_show_ollama_error(self):
        ollama_gw = FakeGateway(exc=FakeConnectionError())
        openai_gw = FakeGateway(response="ok")

        ollama = make_candidate("m1", "ollama", "qwen2.5:7b", ollama_gw)
        openai = make_candidate("m2", "openai", "gpt-4.1-nano", openai_gw)

        pipeline, _ = make_pipeline([(ollama, ollama_gw), (openai, openai_gw)])
        _, attempts = asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        assert attempts[0].model_code == "qwen2.5:7b"
        assert attempts[0].success is False


# ──────────────────────────────────────────────────────────────────────
# Scenario 3: CIO Agent forbid_local=True → Ollama filtered
# ──────────────────────────────────────────────────────────────────────

class TestScenario3ForbidLocal:
    """
    CIO Agent has forbid_local=True.
    When AgentOverrideService.resolve() is called, Ollama candidates are removed.
    We test the filtering logic directly on the service.
    """

    def test_forbid_local_filters_ollama_from_chain(self):
        from src.services.llm_agent_override_service import LLMAgentOverrideService
        from src.data.models import LLMAgentOverride

        # Build a mock override with forbid_local=True
        mock_override = MagicMock(spec=LLMAgentOverride)
        mock_override.enabled = True
        mock_override.override_tier = None
        mock_override.primary_model_id = "model-cloud-id"
        mock_override.fallback_model_ids = ["model-ollama-id"]
        mock_override.forbid_local = True
        mock_override.forbid_fallback = False

        # Mock the repositories
        with patch.object(LLMAgentOverrideService, '__init__', lambda self, user_id, db_session=None: None):
            svc = LLMAgentOverrideService.__new__(LLMAgentOverrideService)
            svc.user_id = "user1"
            svc._override_repo = MagicMock()
            svc._model_repo = MagicMock()
            svc._provider_repo = MagicMock()

            svc._override_repo.get_by_agent.return_value = mock_override

            # Build fake candidates: one cloud, one ollama
            cloud_candidate = MagicMock()
            cloud_candidate.provider_code = "anthropic"
            cloud_candidate.model_code = "claude-sonnet-4.5"

            ollama_candidate = MagicMock()
            ollama_candidate.provider_code = "ollama"
            ollama_candidate.model_code = "qwen2.5:7b"

            with patch.object(svc, '_build_custom_chain', return_value=[cloud_candidate, ollama_candidate]):
                result = svc.resolve(
                    agent_name="cio",
                    default_tier="advanced",
                )

        # Ollama should be filtered out
        assert len(result) == 1
        assert result[0].provider_code == "anthropic"

    def test_forbid_local_with_only_ollama_returns_empty(self):
        from src.services.llm_agent_override_service import LLMAgentOverrideService
        from src.data.models import LLMAgentOverride

        mock_override = MagicMock(spec=LLMAgentOverride)
        mock_override.enabled = True
        mock_override.override_tier = None
        mock_override.primary_model_id = "model-ollama-id"
        mock_override.fallback_model_ids = []
        mock_override.forbid_local = True
        mock_override.forbid_fallback = False

        with patch.object(LLMAgentOverrideService, '__init__', lambda self, user_id, db_session=None: None):
            svc = LLMAgentOverrideService.__new__(LLMAgentOverrideService)
            svc.user_id = "user1"
            svc._override_repo = MagicMock()
            svc._model_repo = MagicMock()
            svc._provider_repo = MagicMock()
            svc._override_repo.get_by_agent.return_value = mock_override

            ollama_candidate = MagicMock()
            ollama_candidate.provider_code = "ollama"

            with patch.object(svc, '_build_custom_chain', return_value=[ollama_candidate]):
                result = svc.resolve(agent_name="cio", default_tier="advanced")

        assert result == []


# ──────────────────────────────────────────────────────────────────────
# Scenario 4: forbid_fallback=True → primary fails, raises immediately
# ──────────────────────────────────────────────────────────────────────

class TestScenario4ForbidFallback:
    """forbid_fallback=True: only primary is kept; if it fails, raises immediately."""

    def test_forbid_fallback_truncates_chain_to_primary(self):
        from src.services.llm_agent_override_service import LLMAgentOverrideService
        from src.data.models import LLMAgentOverride

        mock_override = MagicMock(spec=LLMAgentOverride)
        mock_override.enabled = True
        mock_override.override_tier = None
        mock_override.primary_model_id = "model-primary-id"
        mock_override.fallback_model_ids = ["model-fallback-id"]
        mock_override.forbid_local = False
        mock_override.forbid_fallback = True

        with patch.object(LLMAgentOverrideService, '__init__', lambda self, user_id, db_session=None: None):
            svc = LLMAgentOverrideService.__new__(LLMAgentOverrideService)
            svc.user_id = "user1"
            svc._override_repo = MagicMock()
            svc._model_repo = MagicMock()
            svc._provider_repo = MagicMock()
            svc._override_repo.get_by_agent.return_value = mock_override

            primary = MagicMock()
            primary.provider_code = "anthropic"
            primary.model_code = "claude-sonnet-4.5"

            fallback = MagicMock()
            fallback.provider_code = "openai"
            fallback.model_code = "gpt-4.1-nano"

            with patch.object(svc, '_build_custom_chain', return_value=[primary, fallback]):
                result = svc.resolve(agent_name="cio", default_tier="advanced")

        # Only primary should remain
        assert len(result) == 1
        assert result[0].model_code == "claude-sonnet-4.5"

    def test_forbid_fallback_pipeline_raises_on_primary_failure(self):
        """When chain has only 1 candidate and it fails → AllCandidatesFailedError."""
        primary_gw = FakeGateway(exc=FakeRateLimitError())
        primary = make_candidate("m1", "anthropic", "claude-sonnet-4.5", primary_gw)

        pipeline, _ = make_pipeline([(primary, primary_gw)])

        with pytest.raises(AllCandidatesFailedError) as exc_info:
            asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        assert len(exc_info.value.attempts) == 1
        assert exc_info.value.attempts[0].model_code == "claude-sonnet-4.5"


# ──────────────────────────────────────────────────────────────────────
# Scenario 5: All candidates fail → AllCandidatesFailedError
# ──────────────────────────────────────────────────────────────────────

class TestScenario5AllCandidatesFail:
    """All candidates in the chain fail → AllCandidatesFailedError."""

    def test_all_candidates_fail_raises_error(self):
        gw1 = FakeGateway(exc=FakeRateLimitError())
        gw2 = FakeGateway(exc=FakeConnectionError())
        gw3 = FakeGateway(exc=FakeRateLimitError())

        c1 = make_candidate("m1", "gemini", "gemini-2.5-pro", gw1)
        c2 = make_candidate("m2", "anthropic", "claude-sonnet-4.5", gw2)
        c3 = make_candidate("m3", "openai", "gpt-4.1-nano", gw3)

        pipeline, _ = make_pipeline([(c1, gw1), (c2, gw2), (c3, gw3)])

        with pytest.raises(AllCandidatesFailedError) as exc_info:
            asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        assert len(exc_info.value.attempts) == 3
        assert all(not a.success for a in exc_info.value.attempts)

    def test_all_candidates_fail_error_message_contains_models(self):
        gw1 = FakeGateway(exc=FakeRateLimitError())
        gw2 = FakeGateway(exc=FakeConnectionError())

        c1 = make_candidate("m1", "gemini", "gemini-2.5-pro", gw1)
        c2 = make_candidate("m2", "ollama", "qwen2.5:7b", gw2)

        pipeline, _ = make_pipeline([(c1, gw1), (c2, gw2)])

        with pytest.raises(AllCandidatesFailedError) as exc_info:
            asyncio.get_event_loop().run_until_complete(pipeline.execute(MESSAGES))

        error_msg = str(exc_info.value)
        assert "gemini-2.5-pro" in error_msg
        assert "qwen2.5:7b" in error_msg


# ──────────────────────────────────────────────────────────────────────
# Scenario 6: Provider/Model CRUD + 409 conflict
# ──────────────────────────────────────────────────────────────────────

class TestScenario6CRUDConflicts:
    """
    Provider/Model CRUD + 409 conflict:
    - Model referenced by Tier cannot be deleted (ModelInUseError)
    - Provider with models cannot be deleted (ProviderHasModelsError)
    """

    def test_delete_model_in_use_raises_model_in_use_error(self):
        from src.services.llm_model_service import LLMModelService
        from src.services.llm_settings_errors import ModelInUseError

        with patch.object(LLMModelService, '__init__', lambda self, user_id: None):
            svc = LLMModelService.__new__(LLMModelService)
            svc.user_id = "user1"
            svc.model_repo = MagicMock()
            svc.provider_repo = MagicMock()

            # model.get() returns a model owned by user1
            mock_model = MagicMock()
            mock_model.id = "model-uuid-123"
            mock_model.provider_id = "prov-1"
            svc.model_repo.get.return_value = mock_model

            # provider.get() returns provider owned by user1
            mock_provider = MagicMock()
            mock_provider.user_id = "user1"
            svc.provider_repo.get.return_value = mock_provider

            # get_references returns a dict with non-empty values → in use
            svc.model_repo.get_references.return_value = {
                "tier_bindings": [{"tier": "fast", "role": "primary"}],
                "agent_overrides": [],
            }

            with pytest.raises(ModelInUseError):
                svc.delete("model-uuid-123")

    def test_delete_provider_with_models_raises_provider_has_models_error(self):
        from src.services.llm_provider_service import LLMProviderService
        from src.services.llm_settings_errors import ProviderHasModelsError

        with patch.object(LLMProviderService, '__init__', lambda self, user_id: None):
            svc = LLMProviderService.__new__(LLMProviderService)
            svc.user_id = "user1"
            svc.provider_repo = MagicMock()
            svc.model_repo = MagicMock()

            # provider_repo.get_for_user returns a provider row
            mock_provider = MagicMock()
            mock_provider.id = "provider-uuid-123"
            svc.provider_repo.get_for_user.return_value = mock_provider

            # count_models returns 3 (int, not MagicMock)
            svc.provider_repo.count_models.return_value = 3

            with pytest.raises(ProviderHasModelsError):
                svc.delete("provider-uuid-123")

    def test_delete_model_not_in_use_succeeds(self):
        from src.services.llm_model_service import LLMModelService
        from src.services.llm_settings_errors import ModelInUseError

        with patch.object(LLMModelService, '__init__', lambda self, user_id: None):
            svc = LLMModelService.__new__(LLMModelService)
            svc.user_id = "user1"
            svc.model_repo = MagicMock()
            svc.provider_repo = MagicMock()

            mock_model = MagicMock()
            mock_model.id = "model-uuid-123"
            mock_model.provider_id = "prov-1"
            svc.model_repo.get.return_value = mock_model

            mock_provider = MagicMock()
            mock_provider.user_id = "user1"
            svc.provider_repo.get.return_value = mock_provider

            # No references → can delete (empty dict values)
            svc.model_repo.get_references.return_value = {
                "tier_bindings": [],
                "agent_overrides": [],
            }

            # Should not raise
            try:
                svc.delete("model-uuid-123")
            except ModelInUseError:
                pytest.fail("delete() raised ModelInUseError unexpectedly")
