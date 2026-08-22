"""
LLMAgentOverrideService — Phase C orchestrator for Agent Override CRUD + resolve().

Responsibilities:
  - list_overrides(user_id) -> list[AgentOverrideOut]
  - update_overrides(user_id, overrides) -> list[AgentOverrideOut]
  - resolve(user_id, agent_name, default_tier, db_session) -> list[ModelCandidate]
      Checks for an enabled override; if found, builds a custom chain.
      Applies forbid_local / forbid_fallback filters.
      Falls back to build_config_chain(user_id, default_tier) if no override.

Design: docs/architecture/multi_provider_multi_model_design.md §3.4 / §4.4 / §8.4 C1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.data.models import LLMAgentOverride, LLMModel, LLMProvider
from src.repositories.llm_agent_override_repository import LLMAgentOverrideRepository
from src.repositories.llm_model_repository import LLMModelRepository
from src.repositories.llm_provider_repository import LLMProviderRepository
from src.services.llm_settings_errors import ModelNotFound

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Known agent names (for UI autocomplete / validation)
# ──────────────────────────────────────────────────────────────────────
KNOWN_AGENT_NAMES: List[str] = [
    "cio",
    "fundamental",
    "macro",
    "momentum",
    "sentiment",
    "thematic",
    "risk",
    "sentinel",
    "engineer",
    "conversation",
    "skill_router",
]

VALID_TIERS = ["nano", "fast", "smart", "advanced"]


# ──────────────────────────────────────────────────────────────────────
# Value objects
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ModelOutMin:
    """Minimal model info embedded in AgentOverrideOut."""
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
class AgentOverrideOut:
    """Full agent override record with expanded model details."""
    id: str
    user_id: str
    agent_name: str
    override_tier: Optional[str]
    primary_model_id: Optional[str]
    primary_model: Optional[ModelOutMin]
    fallback_model_ids: List[str]
    fallback_models: List[ModelOutMin]
    forbid_local: bool
    forbid_fallback: bool
    enabled: bool
    notes: Optional[str]


@dataclass
class AgentOverrideUpdate:
    """Input DTO for a single agent override upsert."""
    agent_name: str
    override_tier: Optional[str] = None
    primary_model_id: Optional[str] = None
    fallback_model_ids: List[str] = field(default_factory=list)
    forbid_local: bool = False
    forbid_fallback: bool = False
    enabled: bool = True
    notes: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────

class LLMAgentOverrideService:
    """
    Orchestrates agent override CRUD and model-chain resolution.

    Args:
        user_id: The authenticated user's ID.
        db_session: Optional injected SQLAlchemy session (for testing).
    """

    def __init__(self, user_id: str, db_session=None):
        self.user_id = user_id
        self._override_repo = LLMAgentOverrideRepository(db_session=db_session)
        self._model_repo = LLMModelRepository()
        self._provider_repo = LLMProviderRepository()

    # ──────────────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────────────

    def list_overrides(self) -> List[AgentOverrideOut]:
        """Return all agent overrides for the current user."""
        rows = self._override_repo.list_by_user(self.user_id)
        return [self._row_to_out(r) for r in rows]

    def update_overrides(self, overrides: List[AgentOverrideUpdate]) -> List[AgentOverrideOut]:
        """
        Bulk upsert agent overrides.

        Validates each override before persisting:
          - override_tier OR primary_model_id must be set
          - model FKs must exist and be enabled
          - override_tier must be in VALID_TIERS if provided

        Returns the updated list of all overrides for the user.
        """
        errors = []
        for ov in overrides:
            errs = self._validate_override(ov)
            errors.extend(errs)

        if errors:
            raise ValueError(errors)

        results = []
        for ov in overrides:
            row = self._override_repo.upsert(
                user_id=self.user_id,
                agent_name=ov.agent_name,
                override_tier=ov.override_tier,
                primary_model_id=ov.primary_model_id,
                fallback_model_ids=ov.fallback_model_ids,
                forbid_local=ov.forbid_local,
                forbid_fallback=ov.forbid_fallback,
                enabled=ov.enabled,
                notes=ov.notes,
            )
            results.append(self._row_to_out(row))

        return results

    def delete_override(self, agent_name: str) -> bool:
        """Delete an agent override. Returns True if deleted."""
        return self._override_repo.delete(self.user_id, agent_name)

    # ──────────────────────────────────────────────────────────────────
    # Resolve — core routing logic
    # ──────────────────────────────────────────────────────────────────

    def resolve(
        self,
        agent_name: str,
        default_tier: str,
        db_session: Any = None,
    ) -> List[Any]:
        """
        Resolve the ModelCandidate chain for a given agent.

        Algorithm:
          1. Look up override for (user_id, agent_name)
          2. If override exists and enabled:
             a. If override_tier set → use build_config_chain(user_id, override_tier)
             b. If primary_model_id set → build custom chain from primary + fallback_model_ids
          3. Apply forbid_local filter (remove ollama/local candidates)
          4. Apply forbid_fallback filter (keep only primary)
          5. If no override → fall back to build_config_chain(user_id, default_tier)

        Returns:
            list[ModelCandidate] — ordered primary-first.
        """
        from src.infrastructure.llm.llm_config_chain import build_config_chain

        override = self._override_repo.get_by_agent(self.user_id, agent_name)

        if override is None or not override.enabled:
            logger.debug(
                "resolve: no active override for agent=%s user=%s, using default tier=%s",
                agent_name, self.user_id, default_tier,
            )
            return build_config_chain(
                user_id=self.user_id,
                tier=default_tier,
                db_session=db_session,
            )

        # ── Build chain from override ──────────────────────────────────
        if override.override_tier:
            # Use the specified tier's chain
            logger.debug(
                "resolve: agent=%s using override_tier=%s",
                agent_name, override.override_tier,
            )
            candidates = build_config_chain(
                user_id=self.user_id,
                tier=override.override_tier,
                db_session=db_session,
            )
        elif override.primary_model_id:
            # Build custom chain from primary + fallback model IDs
            logger.debug(
                "resolve: agent=%s using custom primary=%s fallbacks=%s",
                agent_name, override.primary_model_id, override.fallback_model_ids,
            )
            candidates = self._build_custom_chain(
                primary_model_id=override.primary_model_id,
                fallback_model_ids=override.fallback_model_ids or [],
            )
        else:
            # Misconfigured override — fall back to default tier
            logger.warning(
                "resolve: override for agent=%s has neither override_tier nor primary_model_id, "
                "falling back to default tier=%s",
                agent_name, default_tier,
            )
            return build_config_chain(
                user_id=self.user_id,
                tier=default_tier,
                db_session=db_session,
            )

        # ── Apply filters ──────────────────────────────────────────────
        if override.forbid_local:
            before = len(candidates)
            candidates = [
                c for c in candidates
                if c.provider_code.lower() != "ollama"
            ]
            if len(candidates) < before:
                logger.info(
                    "resolve: forbid_local filtered %d local candidate(s) for agent=%s",
                    before - len(candidates), agent_name,
                )

        if override.forbid_fallback:
            # Keep only the primary (first) candidate
            if len(candidates) > 1:
                logger.info(
                    "resolve: forbid_fallback truncating chain to primary only for agent=%s",
                    agent_name,
                )
                candidates = candidates[:1]

        return candidates

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _build_custom_chain(
        self,
        primary_model_id: str,
        fallback_model_ids: List[str],
    ) -> List[Any]:
        """
        Build a ModelCandidate list from explicit model IDs.
        Skips disabled models / providers.
        """
        from src.infrastructure.llm.llm_config_chain import _get_gateway_registry, _decrypt_api_key

        registry = _get_gateway_registry()
        candidates = []

        for model_id in [primary_model_id] + list(fallback_model_ids):
            try:
                model = self._model_repo.get(model_id)
                if model is None or not model.enabled:
                    logger.debug("_build_custom_chain: skipping disabled/missing model %s", model_id)
                    continue

                provider = self._provider_repo.get(model.provider_id)
                if provider is None or not provider.enabled:
                    logger.debug("_build_custom_chain: skipping disabled/missing provider for model %s", model_id)
                    continue

                gateway_class = registry.get(provider.provider_code)
                if gateway_class is None:
                    logger.warning(
                        "_build_custom_chain: no gateway for provider_code=%s, skipping model %s",
                        provider.provider_code, model_id,
                    )
                    continue

                base_url = provider.base_url
                if not base_url:
                    try:
                        from src.infrastructure.llm.provider_catalog import get_provider_catalog
                        cat = get_provider_catalog()
                        spec = cat.get(provider.provider_code)
                        if spec:
                            base_url = spec.default_base_url
                    except Exception as e:
                        logger.warning(f'Exception in llm_agent_override_service.py: {e}', exc_info=True)

                api_key = _decrypt_api_key(provider.encrypted_api_key)

                from src.infrastructure.llm.resilient_pipeline import ModelCandidate
                candidates.append(ModelCandidate(
                    model_id=model_id,
                    provider_code=provider.provider_code,
                    model_code=model.model_code,
                    gateway_class=gateway_class,
                    base_url=base_url,
                    api_key=api_key,
                    max_retries=2,
                    timeout_seconds=30.0,
                ))

            except Exception as e:
                logger.warning("_build_custom_chain: error resolving model %s: %s", model_id, e)
                continue

        return candidates

    def _row_to_out(self, row: LLMAgentOverride) -> AgentOverrideOut:
        """Convert a DB row to AgentOverrideOut with expanded model details."""
        primary_model = None
        if row.primary_model_id:
            try:
                m = self._model_repo.get(row.primary_model_id)
                if m:
                    p = self._provider_repo.get(m.provider_id)
                    primary_model = self._model_to_min(m, p)
            except Exception as e:
                logger.debug("_row_to_out: could not expand primary model %s: %s", row.primary_model_id, e)

        fallback_models = []
        for fid in (row.fallback_model_ids or []):
            try:
                m = self._model_repo.get(fid)
                if m:
                    p = self._provider_repo.get(m.provider_id)
                    fallback_models.append(self._model_to_min(m, p))
            except Exception as e:
                logger.debug("_row_to_out: could not expand fallback model %s: %s", fid, e)

        return AgentOverrideOut(
            id=row.id,
            user_id=row.user_id,
            agent_name=row.agent_name,
            override_tier=row.override_tier,
            primary_model_id=row.primary_model_id,
            primary_model=primary_model,
            fallback_model_ids=row.fallback_model_ids or [],
            fallback_models=fallback_models,
            forbid_local=row.forbid_local,
            forbid_fallback=row.forbid_fallback,
            enabled=row.enabled,
            notes=row.notes,
        )

    def _model_to_min(
        self,
        model: LLMModel,
        provider: Optional[LLMProvider],
    ) -> ModelOutMin:
        """Convert LLMModel + LLMProvider rows to ModelOutMin."""
        return ModelOutMin(
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

    def _validate_override(self, ov: AgentOverrideUpdate) -> List[Dict[str, str]]:
        """Validate a single AgentOverrideUpdate. Returns list of error dicts."""
        errors = []

        if not ov.agent_name or not ov.agent_name.strip():
            errors.append({"field": "agent_name", "message": "agent_name is required"})
            return errors  # Can't continue without agent_name

        # At least one of override_tier or primary_model_id must be set
        if not ov.override_tier and not ov.primary_model_id:
            errors.append({
                "field": "override_tier",
                "message": "Either override_tier or primary_model_id must be provided",
            })

        # Validate override_tier
        if ov.override_tier and ov.override_tier not in VALID_TIERS:
            errors.append({
                "field": "override_tier",
                "message": f"override_tier must be one of {VALID_TIERS}, got '{ov.override_tier}'",
            })

        # Validate primary_model_id FK
        if ov.primary_model_id:
            try:
                model = self._model_repo.get(ov.primary_model_id)
                if model is None:
                    errors.append({
                        "field": "primary_model_id",
                        "message": f"Model {ov.primary_model_id} not found",
                    })
                elif not model.enabled:
                    errors.append({
                        "field": "primary_model_id",
                        "message": f"Model {ov.primary_model_id} is disabled",
                    })
            except Exception as e:
                errors.append({
                    "field": "primary_model_id",
                    "message": f"Error validating primary_model_id: {e}",
                })

        # Validate fallback_model_ids FKs
        for i, fid in enumerate(ov.fallback_model_ids or []):
            try:
                model = self._model_repo.get(fid)
                if model is None:
                    errors.append({
                        "field": f"fallback_model_ids[{i}]",
                        "message": f"Model {fid} not found",
                    })
                elif not model.enabled:
                    errors.append({
                        "field": f"fallback_model_ids[{i}]",
                        "message": f"Model {fid} is disabled",
                    })
            except Exception as e:
                errors.append({
                    "field": f"fallback_model_ids[{i}]",
                    "message": f"Error validating fallback model: {e}",
                })

        # Check for duplicate model IDs in chain
        all_ids = []
        if ov.primary_model_id:
            all_ids.append(ov.primary_model_id)
        all_ids.extend(ov.fallback_model_ids or [])
        if len(all_ids) != len(set(all_ids)):
            errors.append({
                "field": "fallback_model_ids",
                "message": "Duplicate model IDs in chain are not allowed",
            })

        # Chain length ≤ 5
        if len(all_ids) > 5:
            errors.append({
                "field": "fallback_model_ids",
                "message": f"Chain length must be ≤ 5, got {len(all_ids)}",
            })

        return errors
