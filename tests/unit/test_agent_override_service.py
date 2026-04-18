"""
Unit tests for src/services/llm_agent_override_service.py (Phase C).

Tests:
  - resolve() with no override → falls back to build_config_chain
  - resolve() with disabled override → falls back to build_config_chain
  - resolve() with override_tier → uses tier chain
  - resolve() with primary_model_id → uses custom chain
  - resolve() with forbid_local=True → filters ollama candidates
  - resolve() with forbid_fallback=True → truncates to primary only
  - resolve() with forbid_local + forbid_fallback combined
  - resolve() with misconfigured override (no tier, no primary) → fallback
  - update_overrides() happy path
  - update_overrides() validation: missing tier AND primary_model_id
  - update_overrides() validation: invalid override_tier value
  - update_overrides() validation: duplicate model IDs in chain
  - update_overrides() validation: chain length > 5
  - list_overrides() returns all overrides for user

Design: docs/architecture/multi_provider_multi_model_design.md §8.4 C1
"""
from __future__ import annotations

from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.services.llm_agent_override_service import (
    AgentOverrideUpdate,
    LLMAgentOverrideService,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def make_service(override_row=None, model_row=None, provider_row=None) -> LLMAgentOverrideService:
    """
    Build a LLMAgentOverrideService with mocked repositories.
    """
    with patch.object(LLMAgentOverrideService, '__init__', lambda self, user_id, db_session=None: None):
        svc = LLMAgentOverrideService.__new__(LLMAgentOverrideService)

    svc.user_id = "user-test-1"
    svc._override_repo = MagicMock()
    svc._model_repo = MagicMock()
    svc._provider_repo = MagicMock()

    svc._override_repo.get_by_agent.return_value = override_row
    svc._override_repo.list_by_user.return_value = []
    svc._override_repo.upsert.return_value = MagicMock(
        id="ov-1",
        user_id="user-test-1",
        agent_name="cio",
        override_tier=None,
        primary_model_id=None,
        fallback_model_ids=[],
        forbid_local=False,
        forbid_fallback=False,
        enabled=True,
        notes=None,
    )

    if model_row:
        svc._model_repo.get.return_value = model_row
    else:
        svc._model_repo.get.return_value = MagicMock(
            id="model-1",
            model_code="claude-sonnet-4.5",
            display_name="Claude Sonnet 4.5",
            provider_id="prov-1",
            enabled=True,
            capability_tool_calling=True,
            capability_vision=True,
            capability_json_mode=True,
            capability_streaming=True,
            capability_embeddings=False,
            input_cost_per_1k=None,
            output_cost_per_1k=None,
        )

    if provider_row:
        svc._provider_repo.get.return_value = provider_row
    else:
        svc._provider_repo.get.return_value = MagicMock(
            id="prov-1",
            provider_code="anthropic",
            display_name="Anthropic",
            enabled=True,
            base_url=None,
            encrypted_api_key=None,
        )

    return svc


def make_override_row(
    enabled=True,
    override_tier=None,
    primary_model_id="model-1",
    fallback_model_ids=None,
    forbid_local=False,
    forbid_fallback=False,
):
    row = MagicMock()
    row.enabled = enabled
    row.override_tier = override_tier
    row.primary_model_id = primary_model_id
    row.fallback_model_ids = fallback_model_ids or []
    row.forbid_local = forbid_local
    row.forbid_fallback = forbid_fallback
    return row


def make_candidate(provider_code: str, model_code: str):
    c = MagicMock()
    c.provider_code = provider_code
    c.model_code = model_code
    return c


# ──────────────────────────────────────────────────────────────────────
# resolve() tests
# ──────────────────────────────────────────────────────────────────────

class TestResolveNoOverride:
    """resolve() when no override exists → falls back to build_config_chain."""

    def test_no_override_calls_build_config_chain(self):
        svc = make_service(override_row=None)
        fake_chain = [make_candidate("gemini", "gemini-2.5-pro")]

        # build_config_chain is lazy-imported inside resolve(); patch at its source
        with patch(
            "src.infrastructure.llm.llm_config_chain.build_config_chain",
            return_value=fake_chain,
        ) as mock_build:
            result = svc.resolve(agent_name="cio", default_tier="smart")

        mock_build.assert_called_once_with(
            user_id="user-test-1",
            tier="smart",
            db_session=None,
        )
        assert result == fake_chain

    def test_disabled_override_falls_back_to_build_config_chain(self):
        disabled_row = make_override_row(enabled=False)
        svc = make_service(override_row=disabled_row)
        fake_chain = [make_candidate("openai", "gpt-4.1-nano")]

        with patch(
            "src.infrastructure.llm.llm_config_chain.build_config_chain",
            return_value=fake_chain,
        ) as mock_build:
            result = svc.resolve(agent_name="cio", default_tier="nano")

        mock_build.assert_called_once()
        assert result == fake_chain


class TestResolveWithOverrideTier:
    """resolve() with override_tier set → uses that tier's chain."""

    def test_override_tier_uses_tier_chain(self):
        row = make_override_row(override_tier="advanced", primary_model_id=None)
        svc = make_service(override_row=row)
        advanced_chain = [make_candidate("anthropic", "claude-sonnet-4.5")]

        with patch(
            "src.infrastructure.llm.llm_config_chain.build_config_chain",
            return_value=advanced_chain,
        ) as mock_build:
            result = svc.resolve(agent_name="cio", default_tier="smart")

        mock_build.assert_called_once_with(
            user_id="user-test-1",
            tier="advanced",
            db_session=None,
        )
        assert result == advanced_chain


class TestResolveWithCustomChain:
    """resolve() with primary_model_id set → builds custom chain."""

    def test_primary_model_id_builds_custom_chain(self):
        row = make_override_row(
            override_tier=None,
            primary_model_id="model-cloud-1",
            fallback_model_ids=["model-cloud-2"],
        )
        svc = make_service(override_row=row)
        custom_chain = [
            make_candidate("anthropic", "claude-sonnet-4.5"),
            make_candidate("openai", "gpt-4.1-nano"),
        ]

        with patch.object(svc, "_build_custom_chain", return_value=custom_chain) as mock_build:
            result = svc.resolve(agent_name="cio", default_tier="smart")

        mock_build.assert_called_once_with(
            primary_model_id="model-cloud-1",
            fallback_model_ids=["model-cloud-2"],
        )
        assert result == custom_chain


class TestResolveForbidLocal:
    """resolve() with forbid_local=True → ollama candidates filtered out."""

    def test_forbid_local_removes_ollama_candidates(self):
        row = make_override_row(
            override_tier=None,
            primary_model_id="model-cloud",
            fallback_model_ids=["model-ollama"],
            forbid_local=True,
        )
        svc = make_service(override_row=row)

        cloud = make_candidate("anthropic", "claude-sonnet-4.5")
        ollama = make_candidate("ollama", "qwen2.5:7b")

        with patch.object(svc, "_build_custom_chain", return_value=[cloud, ollama]):
            result = svc.resolve(agent_name="cio", default_tier="advanced")

        assert len(result) == 1
        assert result[0].provider_code == "anthropic"

    def test_forbid_local_keeps_non_ollama_candidates(self):
        row = make_override_row(
            override_tier=None,
            primary_model_id="model-cloud",
            fallback_model_ids=["model-cloud-2"],
            forbid_local=True,
        )
        svc = make_service(override_row=row)

        cloud1 = make_candidate("anthropic", "claude-sonnet-4.5")
        cloud2 = make_candidate("openai", "gpt-4.1-nano")

        with patch.object(svc, "_build_custom_chain", return_value=[cloud1, cloud2]):
            result = svc.resolve(agent_name="cio", default_tier="advanced")

        assert len(result) == 2


class TestResolveForbidFallback:
    """resolve() with forbid_fallback=True → only primary kept."""

    def test_forbid_fallback_truncates_to_primary(self):
        row = make_override_row(
            override_tier=None,
            primary_model_id="model-primary",
            fallback_model_ids=["model-fallback-1", "model-fallback-2"],
            forbid_fallback=True,
        )
        svc = make_service(override_row=row)

        primary = make_candidate("anthropic", "claude-sonnet-4.5")
        fb1 = make_candidate("openai", "gpt-4.1-nano")
        fb2 = make_candidate("gemini", "gemini-2.5-flash")

        with patch.object(svc, "_build_custom_chain", return_value=[primary, fb1, fb2]):
            result = svc.resolve(agent_name="cio", default_tier="advanced")

        assert len(result) == 1
        assert result[0].model_code == "claude-sonnet-4.5"

    def test_forbid_local_and_forbid_fallback_combined(self):
        """forbid_local + forbid_fallback: filter local, then truncate to 1."""
        row = make_override_row(
            override_tier=None,
            primary_model_id="model-cloud",
            fallback_model_ids=["model-ollama"],
            forbid_local=True,
            forbid_fallback=True,
        )
        svc = make_service(override_row=row)

        cloud = make_candidate("anthropic", "claude-sonnet-4.5")
        ollama = make_candidate("ollama", "qwen2.5:7b")

        with patch.object(svc, "_build_custom_chain", return_value=[cloud, ollama]):
            result = svc.resolve(agent_name="cio", default_tier="advanced")

        # After forbid_local: [cloud]; after forbid_fallback: [cloud]
        assert len(result) == 1
        assert result[0].provider_code == "anthropic"


class TestResolveMisconfigured:
    """resolve() with override that has neither tier nor primary → fallback."""

    def test_misconfigured_override_falls_back_to_default_tier(self):
        row = make_override_row(override_tier=None, primary_model_id=None)
        svc = make_service(override_row=row)
        fallback_chain = [make_candidate("gemini", "gemini-2.5-pro")]

        with patch(
            "src.infrastructure.llm.llm_config_chain.build_config_chain",
            return_value=fallback_chain,
        ) as mock_build:
            result = svc.resolve(agent_name="cio", default_tier="smart")

        mock_build.assert_called_once_with(
            user_id="user-test-1",
            tier="smart",
            db_session=None,
        )
        assert result == fallback_chain


# ──────────────────────────────────────────────────────────────────────
# update_overrides() tests
# ──────────────────────────────────────────────────────────────────────

class TestUpdateOverrides:
    """update_overrides() validation and happy path."""

    def test_update_overrides_happy_path(self):
        svc = make_service()
        updates = [
            AgentOverrideUpdate(
                agent_name="cio",
                override_tier="advanced",
                enabled=True,
            )
        ]

        result = svc.update_overrides(updates)
        assert len(result) == 1
        svc._override_repo.upsert.assert_called_once()

    def test_validation_fails_when_no_tier_and_no_primary(self):
        svc = make_service()
        updates = [
            AgentOverrideUpdate(
                agent_name="cio",
                override_tier=None,
                primary_model_id=None,
            )
        ]

        with pytest.raises(ValueError) as exc_info:
            svc.update_overrides(updates)

        errors = exc_info.value.args[0]
        assert any("override_tier" in e.get("field", "") for e in errors)

    def test_validation_fails_with_invalid_tier(self):
        svc = make_service()
        updates = [
            AgentOverrideUpdate(
                agent_name="cio",
                override_tier="ultra",  # invalid
            )
        ]

        with pytest.raises(ValueError) as exc_info:
            svc.update_overrides(updates)

        errors = exc_info.value.args[0]
        assert any("override_tier" in e.get("field", "") for e in errors)

    def test_validation_fails_with_duplicate_model_ids(self):
        svc = make_service()
        updates = [
            AgentOverrideUpdate(
                agent_name="cio",
                primary_model_id="model-1",
                fallback_model_ids=["model-1"],  # duplicate!
            )
        ]

        with pytest.raises(ValueError) as exc_info:
            svc.update_overrides(updates)

        errors = exc_info.value.args[0]
        assert any("Duplicate" in e.get("message", "") for e in errors)

    def test_validation_fails_when_chain_too_long(self):
        svc = make_service()
        updates = [
            AgentOverrideUpdate(
                agent_name="cio",
                primary_model_id="model-1",
                fallback_model_ids=["m2", "m3", "m4", "m5", "m6"],  # 6 total > 5
            )
        ]

        with pytest.raises(ValueError) as exc_info:
            svc.update_overrides(updates)

        errors = exc_info.value.args[0]
        assert any("≤ 5" in e.get("message", "") for e in errors)


# ──────────────────────────────────────────────────────────────────────
# list_overrides() tests
# ──────────────────────────────────────────────────────────────────────

class TestListOverrides:
    """list_overrides() returns all overrides for the user."""

    def test_list_overrides_returns_empty_when_none(self):
        svc = make_service()
        svc._override_repo.list_by_user.return_value = []

        result = svc.list_overrides()
        assert result == []

    def test_list_overrides_returns_all_rows(self):
        svc = make_service()

        row1 = MagicMock()
        row1.id = "ov-1"
        row1.user_id = "user-test-1"
        row1.agent_name = "cio"
        row1.override_tier = "advanced"
        row1.primary_model_id = None
        row1.fallback_model_ids = []
        row1.forbid_local = True
        row1.forbid_fallback = False
        row1.enabled = True
        row1.notes = None

        row2 = MagicMock()
        row2.id = "ov-2"
        row2.user_id = "user-test-1"
        row2.agent_name = "skill_router"
        row2.override_tier = None
        row2.primary_model_id = "model-1"
        row2.fallback_model_ids = []
        row2.forbid_local = False
        row2.forbid_fallback = False
        row2.enabled = True
        row2.notes = "High frequency"

        svc._override_repo.list_by_user.return_value = [row1, row2]

        result = svc.list_overrides()
        assert len(result) == 2
        assert result[0].agent_name == "cio"
        assert result[1].agent_name == "skill_router"
