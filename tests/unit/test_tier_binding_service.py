"""
Unit tests for src/services/llm_tier_binding_service.py

Tests:
  - validate_chain: normal (valid chain)
  - validate_chain: duplicate model_id
  - validate_chain: chain too long (> 5)
  - validate_chain: disabled model
  - validate_chain: disabled provider
  - validate_chain: model not found
  - validate_chain: invalid tier
  - get_tier_bindings: returns all 4 tiers
  - update_tier_bindings: calls upsert_all on success
  - update_tier_bindings: raises ValueError on validation failure
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.services.llm_tier_binding_service import (
    LLMTierBindingService,
    TierBindingUpdate,
    ValidationResult,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers — fake ORM objects
# ──────────────────────────────────────────────────────────────────────

def make_model(
    model_id: str,
    model_code: str = "gpt-4.1-nano",
    provider_id: str = "prov-1",
    enabled: bool = True,
) -> MagicMock:
    m = MagicMock()
    m.id = model_id
    m.model_code = model_code
    m.display_name = model_code
    m.provider_id = provider_id
    m.enabled = enabled
    m.input_cost_per_1k = Decimal("0.0001")
    m.output_cost_per_1k = Decimal("0.0004")
    m.capability_tool_calling = True
    m.capability_vision = False
    m.capability_json_mode = True
    m.capability_streaming = True
    m.capability_embeddings = False
    return m


def make_provider(
    provider_id: str = "prov-1",
    provider_code: str = "openai",
    enabled: bool = True,
) -> MagicMock:
    p = MagicMock()
    p.id = provider_id
    p.provider_code = provider_code
    p.display_name = f"{provider_code} (test)"
    p.enabled = enabled
    return p


def make_binding(
    tier: str,
    primary_model_id: str,
    fallback_model_ids: List[str] = None,
) -> MagicMock:
    b = MagicMock()
    b.id = f"binding-{tier}"
    b.tier = tier
    b.primary_model_id = primary_model_id
    b.fallback_model_ids = fallback_model_ids or []
    b.per_candidate_config = {}
    b.budget_aware = True
    return b


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def service_with_mocks():
    """
    Returns (service, mock_tier_repo, mock_model_repo, mock_provider_repo).
    All repos are mocked so no DB is needed.
    """
    with (
        patch("src.services.llm_tier_binding_service.LLMTierBindingRepository") as MockTierRepo,
        patch("src.services.llm_tier_binding_service.LLMModelRepository") as MockModelRepo,
        patch("src.services.llm_tier_binding_service.LLMProviderRepository") as MockProviderRepo,
    ):
        mock_tier_repo = MagicMock()
        mock_model_repo = MagicMock()
        mock_provider_repo = MagicMock()

        MockTierRepo.return_value = mock_tier_repo
        MockModelRepo.return_value = mock_model_repo
        MockProviderRepo.return_value = mock_provider_repo

        svc = LLMTierBindingService(user_id="user-test")
        yield svc, mock_tier_repo, mock_model_repo, mock_provider_repo


# ──────────────────────────────────────────────────────────────────────
# validate_chain tests
# ──────────────────────────────────────────────────────────────────────

class TestValidateChain:
    def test_valid_chain(self, service_with_mocks):
        svc, _, mock_model_repo, mock_provider_repo = service_with_mocks

        model = make_model("m1")
        provider = make_provider("prov-1")
        mock_model_repo.get.return_value = model
        mock_provider_repo.get.return_value = provider

        result = svc.validate_chain(
            tier="nano",
            primary_model_id="m1",
            fallback_model_ids=[],
        )

        assert result.valid is True
        assert result.errors == []

    def test_valid_chain_with_fallbacks(self, service_with_mocks):
        svc, _, mock_model_repo, mock_provider_repo = service_with_mocks

        model1 = make_model("m1", provider_id="prov-1")
        model2 = make_model("m2", provider_id="prov-2")
        provider1 = make_provider("prov-1")
        provider2 = make_provider("prov-2", provider_code="gemini")

        def get_model(mid):
            return {"m1": model1, "m2": model2}.get(mid)

        def get_provider(pid):
            return {"prov-1": provider1, "prov-2": provider2}.get(pid)

        mock_model_repo.get.side_effect = get_model
        mock_provider_repo.get.side_effect = get_provider

        result = svc.validate_chain(
            tier="fast",
            primary_model_id="m1",
            fallback_model_ids=["m2"],
        )

        assert result.valid is True

    def test_invalid_tier(self, service_with_mocks):
        svc, _, _, _ = service_with_mocks

        result = svc.validate_chain(
            tier="ultra",
            primary_model_id="m1",
            fallback_model_ids=[],
        )

        assert result.valid is False
        assert any("tier" in e.field for e in result.errors)

    def test_model_not_found(self, service_with_mocks):
        svc, _, mock_model_repo, _ = service_with_mocks
        mock_model_repo.get.return_value = None

        result = svc.validate_chain(
            tier="nano",
            primary_model_id="nonexistent-model",
            fallback_model_ids=[],
        )

        assert result.valid is False
        assert any("not found" in e.message for e in result.errors)

    def test_disabled_primary_model(self, service_with_mocks):
        svc, _, mock_model_repo, mock_provider_repo = service_with_mocks

        model = make_model("m1", enabled=False)
        mock_model_repo.get.return_value = model

        result = svc.validate_chain(
            tier="nano",
            primary_model_id="m1",
            fallback_model_ids=[],
        )

        assert result.valid is False
        assert any("disabled" in e.message for e in result.errors)

    def test_disabled_provider(self, service_with_mocks):
        svc, _, mock_model_repo, mock_provider_repo = service_with_mocks

        model = make_model("m1", enabled=True)
        provider = make_provider("prov-1", enabled=False)
        mock_model_repo.get.return_value = model
        mock_provider_repo.get.return_value = provider

        result = svc.validate_chain(
            tier="nano",
            primary_model_id="m1",
            fallback_model_ids=[],
        )

        assert result.valid is False
        assert any("disabled" in e.message for e in result.errors)

    def test_duplicate_model_id(self, service_with_mocks):
        svc, _, mock_model_repo, mock_provider_repo = service_with_mocks

        model = make_model("m1")
        provider = make_provider("prov-1")
        mock_model_repo.get.return_value = model
        mock_provider_repo.get.return_value = provider

        result = svc.validate_chain(
            tier="nano",
            primary_model_id="m1",
            fallback_model_ids=["m1"],  # duplicate!
        )

        assert result.valid is False
        assert any("Duplicate" in e.message for e in result.errors)

    def test_chain_too_long(self, service_with_mocks):
        svc, _, mock_model_repo, mock_provider_repo = service_with_mocks

        # Create 5 distinct models
        models = {f"m{i}": make_model(f"m{i}", provider_id="prov-1") for i in range(6)}
        provider = make_provider("prov-1")
        mock_model_repo.get.side_effect = lambda mid: models.get(mid)
        mock_provider_repo.get.return_value = provider

        result = svc.validate_chain(
            tier="nano",
            primary_model_id="m0",
            fallback_model_ids=["m1", "m2", "m3", "m4"],  # 5 total = max
        )
        assert result.valid is True  # exactly 5 is OK

        result2 = svc.validate_chain(
            tier="nano",
            primary_model_id="m0",
            fallback_model_ids=["m1", "m2", "m3", "m4", "m5"],  # 6 total = too long
        )
        assert result2.valid is False
        assert any("exceeds maximum" in e.message for e in result2.errors)

    def test_disabled_fallback_model(self, service_with_mocks):
        svc, _, mock_model_repo, mock_provider_repo = service_with_mocks

        primary = make_model("m1", enabled=True)
        fallback = make_model("m2", enabled=False)
        provider = make_provider("prov-1")

        def get_model(mid):
            return {"m1": primary, "m2": fallback}.get(mid)

        mock_model_repo.get.side_effect = get_model
        mock_provider_repo.get.return_value = provider

        result = svc.validate_chain(
            tier="fast",
            primary_model_id="m1",
            fallback_model_ids=["m2"],
        )

        assert result.valid is False
        assert any("fallback_model_ids" in e.field for e in result.errors)


# ──────────────────────────────────────────────────────────────────────
# get_tier_bindings tests
# ──────────────────────────────────────────────────────────────────────

class TestGetTierBindings:
    def test_returns_all_4_tiers(self, service_with_mocks):
        svc, mock_tier_repo, mock_model_repo, mock_provider_repo = service_with_mocks

        # No bindings in DB
        mock_tier_repo.list_by_user.return_value = []
        mock_model_repo.get.return_value = None

        result = svc.get_tier_bindings()

        assert set(result.keys()) == {"nano", "fast", "smart", "advanced"}

    def test_returns_binding_with_model_details(self, service_with_mocks):
        svc, mock_tier_repo, mock_model_repo, mock_provider_repo = service_with_mocks

        binding = make_binding("nano", "m1")
        model = make_model("m1")
        provider = make_provider("prov-1")

        mock_tier_repo.list_by_user.return_value = [binding]
        mock_model_repo.get.return_value = model
        mock_provider_repo.get.return_value = provider

        result = svc.get_tier_bindings()

        nano = result["nano"]
        assert nano.primary_model_id == "m1"
        assert nano.primary_model is not None
        assert nano.primary_model.model_code == "gpt-4.1-nano"

    def test_missing_tiers_have_empty_primary(self, service_with_mocks):
        svc, mock_tier_repo, mock_model_repo, mock_provider_repo = service_with_mocks

        # Only nano is configured
        binding = make_binding("nano", "m1")
        model = make_model("m1")
        provider = make_provider("prov-1")

        mock_tier_repo.list_by_user.return_value = [binding]
        mock_model_repo.get.return_value = model
        mock_provider_repo.get.return_value = provider

        result = svc.get_tier_bindings()

        assert result["fast"].primary_model_id == ""
        assert result["fast"].primary_model is None


# ──────────────────────────────────────────────────────────────────────
# update_tier_bindings tests
# ──────────────────────────────────────────────────────────────────────

class TestUpdateTierBindings:
    def test_valid_update_calls_upsert_all(self, service_with_mocks):
        svc, mock_tier_repo, mock_model_repo, mock_provider_repo = service_with_mocks

        model = make_model("m1")
        provider = make_provider("prov-1")
        mock_model_repo.get.return_value = model
        mock_provider_repo.get.return_value = provider

        # After upsert, list_by_user returns the binding
        binding = make_binding("nano", "m1")
        mock_tier_repo.list_by_user.return_value = [binding]

        updates = [
            TierBindingUpdate(
                tier="nano",
                primary_model_id="m1",
                fallback_model_ids=[],
            )
        ]

        result = svc.update_tier_bindings(updates)

        mock_tier_repo.upsert_all.assert_called_once()
        assert len(result) == 1

    def test_validation_failure_raises_value_error(self, service_with_mocks):
        svc, mock_tier_repo, mock_model_repo, mock_provider_repo = service_with_mocks

        # Model not found → validation fails
        mock_model_repo.get.return_value = None

        updates = [
            TierBindingUpdate(
                tier="nano",
                primary_model_id="nonexistent",
                fallback_model_ids=[],
            )
        ]

        with pytest.raises(ValueError) as exc_info:
            svc.update_tier_bindings(updates)

        errors = exc_info.value.args[0]
        assert isinstance(errors, list)
        assert len(errors) > 0
        assert errors[0]["tier"] == "nano"

    def test_upsert_not_called_on_validation_failure(self, service_with_mocks):
        svc, mock_tier_repo, mock_model_repo, mock_provider_repo = service_with_mocks

        mock_model_repo.get.return_value = None

        updates = [
            TierBindingUpdate(
                tier="nano",
                primary_model_id="nonexistent",
                fallback_model_ids=[],
            )
        ]

        with pytest.raises(ValueError):
            svc.update_tier_bindings(updates)

        mock_tier_repo.upsert_all.assert_not_called()
