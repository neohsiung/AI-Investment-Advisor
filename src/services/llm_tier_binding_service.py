"""
LLMTierBindingService — Phase B orchestrator for Tier Binding CRUD.

Responsibilities:
  - get_tier_bindings(user_id) -> dict[str, TierBindingOut]
      Returns all 4 tiers (nano/fast/smart/advanced) with full model details.
  - update_tier_bindings(user_id, bindings) -> list[TierBindingOut]
      Validates then bulk-upserts.
  - validate_chain(user_id, tier, primary_model_id, fallback_model_ids) -> ValidationResult
      Checks FK existence, enabled status, no duplicates, chain length ≤ 5.

Design: docs/architecture/multi_provider_multi_model_design.md §4.3 / §8.3 B1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.data.models import LLMModel, LLMProvider, LLMTierBinding
from src.repositories.llm_model_repository import LLMModelRepository
from src.repositories.llm_provider_repository import LLMProviderRepository
from src.repositories.llm_tier_binding_repository import LLMTierBindingRepository
from src.services.llm_settings_errors import ModelNotFound, ProviderNotFound

logger = logging.getLogger(__name__)

VALID_TIERS = ["nano", "fast", "smart", "advanced"]
MAX_CHAIN_LENGTH = 5  # 1 primary + 4 fallbacks


# ──────────────────────────────────────────────────────────────────────
# Value objects
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ModelOut:
    """Minimal model info embedded in TierBindingOut."""
    id: str
    model_code: str
    display_name: str
    provider_id: str
    provider_code: str
    provider_display_name: str
    enabled: bool
    input_cost_per_1k: Optional[Decimal] = None
    output_cost_per_1k: Optional[Decimal] = None
    capabilities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerCandidateConfig:
    max_retries: int = 2
    timeout_seconds: float = 30.0
    conditions: Optional[Dict[str, Any]] = None


@dataclass
class TierBindingOut:
    tier: str
    primary_model_id: str
    primary_model: Optional[ModelOut]
    fallback_model_ids: List[str]
    fallback_models: List[ModelOut]
    per_candidate_config: Dict[str, Any]
    budget_aware: bool
    estimated_daily_cost: Optional[float] = None


@dataclass
class ValidationError:
    field: str
    message: str


@dataclass
class ValidationResult:
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)


@dataclass
class TierBindingUpdate:
    tier: str
    primary_model_id: str
    fallback_model_ids: List[str] = field(default_factory=list)
    per_candidate_config: Dict[str, Any] = field(default_factory=dict)
    budget_aware: bool = True


# ──────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────

class LLMTierBindingService:
    """
    Orchestrates Tier Binding CRUD with full validation.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._tier_repo = LLMTierBindingRepository()
        self._model_repo = LLMModelRepository()
        self._provider_repo = LLMProviderRepository()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_tier_bindings(self) -> Dict[str, TierBindingOut]:
        """
        Return all 4 tier bindings for the user.
        Missing tiers are returned with None primary_model.
        """
        rows = self._tier_repo.list_by_user(self.user_id)
        bindings_by_tier: Dict[str, LLMTierBinding] = {r.tier: r for r in rows}

        result: Dict[str, TierBindingOut] = {}
        for tier in VALID_TIERS:
            row = bindings_by_tier.get(tier)
            if row is None:
                result[tier] = TierBindingOut(
                    tier=tier,
                    primary_model_id="",
                    primary_model=None,
                    fallback_model_ids=[],
                    fallback_models=[],
                    per_candidate_config={},
                    budget_aware=True,
                    estimated_daily_cost=None,
                )
            else:
                primary_model = self._fetch_model_out(row.primary_model_id)
                fallback_ids = row.fallback_model_ids or []
                fallback_models = [
                    m for m in (self._fetch_model_out(fid) for fid in fallback_ids)
                    if m is not None
                ]
                estimated_cost = self._estimate_daily_cost(primary_model, fallback_models)
                result[tier] = TierBindingOut(
                    tier=tier,
                    primary_model_id=row.primary_model_id,
                    primary_model=primary_model,
                    fallback_model_ids=fallback_ids,
                    fallback_models=fallback_models,
                    per_candidate_config=row.per_candidate_config or {},
                    budget_aware=row.budget_aware,
                    estimated_daily_cost=estimated_cost,
                )
        return result

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def update_tier_bindings(
        self, bindings: List[TierBindingUpdate]
    ) -> List[TierBindingOut]:
        """
        Validate then bulk-upsert tier bindings.
        Raises ValueError with detail on validation failure.
        """
        all_errors: List[Dict[str, Any]] = []

        for b in bindings:
            result = self.validate_chain(
                tier=b.tier,
                primary_model_id=b.primary_model_id,
                fallback_model_ids=b.fallback_model_ids,
            )
            if not result.valid:
                for err in result.errors:
                    all_errors.append({
                        "tier": b.tier,
                        "field": err.field,
                        "message": err.message,
                    })

        if all_errors:
            raise ValueError(all_errors)

        # Persist
        upsert_data = [
            {
                "tier": b.tier,
                "primary_model_id": b.primary_model_id,
                "fallback_model_ids": b.fallback_model_ids,
                "per_candidate_config": b.per_candidate_config,
                "budget_aware": b.budget_aware,
            }
            for b in bindings
        ]
        self._tier_repo.upsert_all(self.user_id, upsert_data)

        # Return updated state
        updated = self.get_tier_bindings()
        return [updated[b.tier] for b in bindings if b.tier in updated]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_chain(
        self,
        tier: str,
        primary_model_id: str,
        fallback_model_ids: Optional[List[str]] = None,
    ) -> ValidationResult:
        """
        Validate a tier binding chain:
          1. tier must be valid
          2. primary_model_id must exist and be enabled
          3. primary provider must be enabled
          4. each fallback_model_id must exist and be enabled
          5. each fallback provider must be enabled
          6. no duplicate model_ids in chain
          7. chain length (1 + fallbacks) ≤ MAX_CHAIN_LENGTH (5)
        """
        errors: List[ValidationError] = []
        fallback_model_ids = fallback_model_ids or []

        # 1. Tier validity
        if tier not in VALID_TIERS:
            errors.append(ValidationError(
                field="tier",
                message=f"Invalid tier '{tier}'. Must be one of {VALID_TIERS}",
            ))
            return ValidationResult(valid=False, errors=errors)

        # 2. Primary model must exist and be enabled
        primary_model = self._get_model_safe(primary_model_id)
        if primary_model is None:
            errors.append(ValidationError(
                field="primary_model_id",
                message=f"Model '{primary_model_id}' not found",
            ))
        elif not primary_model.enabled:
            errors.append(ValidationError(
                field="primary_model_id",
                message=f"Model '{primary_model_id}' ({primary_model.model_code}) is disabled",
            ))
        else:
            # 3. Primary provider must be enabled
            primary_provider = self._get_provider_safe(primary_model.provider_id)
            if primary_provider is None:
                errors.append(ValidationError(
                    field="primary_model_id",
                    message=f"Provider for model '{primary_model_id}' not found",
                ))
            elif not primary_provider.enabled:
                errors.append(ValidationError(
                    field="primary_model_id",
                    message=f"Provider '{primary_provider.provider_code}' for primary model is disabled",
                ))

        # 4 & 5. Fallback models
        for idx, fid in enumerate(fallback_model_ids):
            fb_model = self._get_model_safe(fid)
            if fb_model is None:
                errors.append(ValidationError(
                    field=f"fallback_model_ids[{idx}]",
                    message=f"Fallback model '{fid}' not found",
                ))
            elif not fb_model.enabled:
                errors.append(ValidationError(
                    field=f"fallback_model_ids[{idx}]",
                    message=f"Fallback model '{fid}' ({fb_model.model_code}) is disabled",
                ))
            else:
                fb_provider = self._get_provider_safe(fb_model.provider_id)
                if fb_provider is None:
                    errors.append(ValidationError(
                        field=f"fallback_model_ids[{idx}]",
                        message=f"Provider for fallback model '{fid}' not found",
                    ))
                elif not fb_provider.enabled:
                    errors.append(ValidationError(
                        field=f"fallback_model_ids[{idx}]",
                        message=f"Provider '{fb_provider.provider_code}' for fallback model[{idx}] is disabled",
                    ))

        # 6. No duplicates
        all_ids = [primary_model_id] + fallback_model_ids
        seen: set = set()
        for idx, mid in enumerate(all_ids):
            if mid in seen:
                field_name = "primary_model_id" if idx == 0 else f"fallback_model_ids[{idx - 1}]"
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Duplicate model_id '{mid}' in chain",
                ))
            seen.add(mid)

        # 7. Chain length ≤ 5
        if len(all_ids) > MAX_CHAIN_LENGTH:
            errors.append(ValidationError(
                field="fallback_model_ids",
                message=f"Chain length {len(all_ids)} exceeds maximum of {MAX_CHAIN_LENGTH} (1 primary + 4 fallbacks)",
            ))

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_model_safe(self, model_id: str) -> Optional[LLMModel]:
        try:
            return self._model_repo.get(model_id)
        except Exception:
            return None

    def _get_provider_safe(self, provider_id: str) -> Optional[LLMProvider]:
        try:
            return self._provider_repo.get(provider_id)
        except Exception:
            return None

    def _fetch_model_out(self, model_id: str) -> Optional[ModelOut]:
        """Fetch model + provider and return ModelOut. Returns None on error."""
        model = self._get_model_safe(model_id)
        if model is None:
            return None
        provider = self._get_provider_safe(model.provider_id)
        return ModelOut(
            id=model.id,
            model_code=model.model_code,
            display_name=model.display_name,
            provider_id=model.provider_id,
            provider_code=provider.provider_code if provider else "unknown",
            provider_display_name=provider.display_name if provider else "Unknown",
            enabled=model.enabled,
            input_cost_per_1k=model.input_cost_per_1k,
            output_cost_per_1k=model.output_cost_per_1k,
            capabilities={
                "tool_calling": model.capability_tool_calling,
                "vision": model.capability_vision,
                "json_mode": model.capability_json_mode,
                "streaming": model.capability_streaming,
                "embeddings": model.capability_embeddings,
            },
        )

    def _estimate_daily_cost(
        self,
        primary: Optional[ModelOut],
        fallbacks: List[ModelOut],
    ) -> Optional[float]:
        """
        Rough daily cost estimate based on primary model's cost.
        Assumes ~100K input tokens + ~20K output tokens per day.
        """
        if primary is None:
            return None
        input_cost = float(primary.input_cost_per_1k or 0)
        output_cost = float(primary.output_cost_per_1k or 0)
        # 100K input + 20K output tokens per day
        daily = (input_cost * 100) + (output_cost * 20)
        return round(daily, 4)
