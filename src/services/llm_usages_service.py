"""
LLMUsagesService — central query for "who references this Model / Provider?"

Used by:
  - DELETE /providers/{id}   → 409 preview (aggregates Models under Provider)
  - DELETE /models/{id}      → 409 preview (direct Tier + AgentOverride refs)
  - GET    /providers/{id}/usages
  - GET    /models/{id}/usages

Phase A: only `tier_bindings` references are known. `agent_overrides` will be
added in Phase C when that table lands.

See docs/architecture/multi_provider_multi_model_design.md §4.5 / §8.2 A5.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.repositories.llm_model_repository import LLMModelRepository
from src.repositories.llm_provider_repository import LLMProviderRepository
from src.repositories.llm_tier_binding_repository import LLMTierBindingRepository


logger = logging.getLogger(__name__)


class LLMUsagesService:
    def __init__(
        self,
        provider_repo: Optional[LLMProviderRepository] = None,
        model_repo: Optional[LLMModelRepository] = None,
        tier_repo: Optional[LLMTierBindingRepository] = None,
    ):
        self.provider_repo = provider_repo or LLMProviderRepository()
        self.model_repo = model_repo or LLMModelRepository()
        self.tier_repo = tier_repo or LLMTierBindingRepository()

    # ------------------------------------------------------------------
    # Per-model usages
    # ------------------------------------------------------------------
    def get_model_usages(self, model_id: str) -> Dict[str, Any]:
        """
        Return a response suitable for GET /models/{id}/usages.
        """
        model = self.model_repo.get(model_id)
        if model is None:
            return {
                "model_id": model_id,
                "model_code": None,
                "provider_code": None,
                "usages": {"tier_bindings": [], "agent_overrides": []},
                "total_references": 0,
                "can_delete": True,
            }

        provider = self.provider_repo.get(model.provider_id) if model.provider_id else None
        tier_refs = self.tier_repo.get_usages_for_model(model_id)

        usages = {
            "tier_bindings": tier_refs,
            "agent_overrides": [],  # Phase C
        }
        total = sum(len(v) for v in usages.values())
        return {
            "model_id": model_id,
            "model_code": model.model_code,
            "provider_code": provider.provider_code if provider else None,
            "usages": usages,
            "total_references": total,
            "can_delete": total == 0,
        }

    # ------------------------------------------------------------------
    # Per-provider usages (aggregated across all Models under it)
    # ------------------------------------------------------------------
    def get_provider_usages(self, provider_id: str) -> Dict[str, Any]:
        provider = self.provider_repo.get(provider_id)
        if provider is None:
            return {
                "provider_id": provider_id,
                "total_models": 0,
                "referenced_models": 0,
                "usages": [],
            }

        models = self.model_repo.list_by_provider(provider_id)
        per_model = []
        referenced_count = 0
        for m in models:
            tier_refs = self.tier_repo.get_usages_for_model(m.id)
            if tier_refs:
                referenced_count += 1
            per_model.append({
                "model_id": m.id,
                "model_code": m.model_code,
                "tier_bindings": tier_refs,
                "agent_overrides": [],  # Phase C
            })
        return {
            "provider_id": provider_id,
            "total_models": len(models),
            "referenced_models": referenced_count,
            "usages": per_model,
        }
