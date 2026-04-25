"""
LLMModelService — Phase A orchestrator for Model CRUD / Discovery / Batch import.

Key behaviours:
  - `discover(provider_id)` invokes `Gateway.list_models()` for the owning
    Provider, parses the response via `discovery_parsers.get_parser(spec.discovery_parser)`
    (already normalised to DiscoveredModel), and returns enriched items with
    `already_imported` + `existing_model_id`. Results cached 5 min (Redis if
    available; in-memory TTL otherwise).
  - `batch_import(provider_id, items)` writes those items to `llm_models`
    with `source='auto_discovered'`, skipping existing (provider_id, model_code).
  - `delete(model_id)` blocks deletion when usages exist (409 at API layer).
  - `update(model_id, patch)` disallows changing provider_id or model_code.

Design: §4.2 of docs/architecture/multi_provider_multi_model_design.md
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.data.models import LLMModel, LLMProvider
from src.domain.interfaces import DiscoveredModel, LLMConfig
from src.infrastructure.llm.discovery_parsers import get_parser  # noqa: F401 — used for explicit overrides if needed
from src.infrastructure.llm.provider_catalog import ProviderCatalog, get_provider_catalog
from src.repositories.llm_model_repository import LLMModelRepository
from src.repositories.llm_provider_repository import LLMProviderRepository
from src.services.llm_credential_cipher import LLMCredentialCipher
from src.services.llm_settings_errors import (
    DuplicateModel,
    ModelInUseError,
    ModelNotFound,
    ProviderDisabled,
    ProviderNotFound,
)
from src.services.llm_usages_service import LLMUsagesService


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# In-memory TTL cache (fallback when Redis unavailable).
# Thread/process-local — fine for a single gunicorn worker, OK for dev.
# ──────────────────────────────────────────────────────────────────────
_DISCOVERY_CACHE_TTL = 300  # 5 minutes (matches design §4.2.4)
_discovery_cache: Dict[str, Tuple[float, Any]] = {}


def _cache_get(key: str) -> Optional[Any]:
    item = _discovery_cache.get(key)
    if item is None:
        return None
    expires_at, value = item
    if time.time() > expires_at:
        _discovery_cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any, ttl: int = _DISCOVERY_CACHE_TTL) -> None:
    _discovery_cache[key] = (time.time() + ttl, value)


# ──────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────
class LLMModelService:
    """Model CRUD + Discovery + Batch import."""

    def __init__(
        self,
        user_id: str,
        provider_repo: Optional[LLMProviderRepository] = None,
        model_repo: Optional[LLMModelRepository] = None,
        catalog: Optional[ProviderCatalog] = None,
        cipher: Optional[LLMCredentialCipher] = None,
        usages_service: Optional[LLMUsagesService] = None,
    ):
        self.user_id = user_id
        self.provider_repo = provider_repo or LLMProviderRepository()
        self.model_repo = model_repo or LLMModelRepository()
        self.catalog = catalog or get_provider_catalog()
        self.cipher = cipher or LLMCredentialCipher()
        self.usages_service = usages_service or LLMUsagesService(
            provider_repo=self.provider_repo,
            model_repo=self.model_repo,
        )

    # ------------------------------------------------------------------
    # Access guards
    # ------------------------------------------------------------------
    def _load_user_provider(self, provider_id: str) -> LLMProvider:
        row = self.provider_repo.get_for_user(provider_id, self.user_id)
        if row is None:
            raise ProviderNotFound(provider_id)
        return row

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def _serialize(self, m: LLMModel, *, usages_count: Optional[int] = None) -> Dict[str, Any]:
        provider = self.provider_repo.get(m.provider_id) if m.provider_id else None
        if usages_count is None:
            refs = self.model_repo.get_references(m.id)
            usages_count = sum(len(v) for v in refs.values())

        return {
            "id": m.id,
            "provider_id": m.provider_id,
            "provider_code": provider.provider_code if provider else None,
            "provider_display_name": provider.display_name if provider else None,
            "model_code": m.model_code,
            "display_name": m.display_name,
            "capabilities": {
                "tool_calling": bool(m.capability_tool_calling),
                "vision": bool(m.capability_vision),
                "json_mode": bool(m.capability_json_mode),
                "streaming": bool(m.capability_streaming),
                "embeddings": bool(m.capability_embeddings),
            },
            "context_window": m.context_window,
            "input_cost_per_1k": float(m.input_cost_per_1k) if m.input_cost_per_1k is not None else None,
            "output_cost_per_1k": float(m.output_cost_per_1k) if m.output_cost_per_1k is not None else None,
            "source": m.source,
            "enabled": bool(m.enabled),
            "notes": m.notes,
            "usages_count": usages_count,
        }

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def list(
        self,
        provider_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        capability: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if provider_id:
            # Ensure the provider belongs to this user before returning models
            self._load_user_provider(provider_id)
            rows = self.model_repo.list_by_provider(provider_id, enabled=enabled)
        else:
            rows = self.model_repo.list_by_user(
                self.user_id, enabled=enabled, capability=capability,
            )
        return [self._serialize(r) for r in rows]

    def list_by_provider(self, provider_id: str) -> List[Dict[str, Any]]:
        return self.list(provider_id=provider_id)

    def get(self, model_id: str) -> Dict[str, Any]:
        m = self.model_repo.get(model_id)
        if m is None:
            raise ModelNotFound(model_id)
        # Authorisation: model must belong to a provider owned by user.
        prov = self.provider_repo.get(m.provider_id)
        if prov is None or prov.user_id != self.user_id:
            raise ModelNotFound(model_id)
        return self._serialize(m)

    # ------------------------------------------------------------------
    # Create / Update / Delete
    # ------------------------------------------------------------------
    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manual model creation (source='manual'). The owning provider must
        belong to the user AND be enabled.
        """
        provider = self._load_user_provider(payload["provider_id"])
        if not provider.enabled:
            raise ProviderDisabled(
                f"Provider {provider.id} is disabled; enable it before adding models."
            )

        # Uniqueness check (provider_id, model_code)
        existing = self.model_repo.get_by_provider_and_code(
            provider.id, payload["model_code"]
        )
        if existing is not None:
            raise DuplicateModel(
                f"Model '{payload['model_code']}' already exists under provider {provider.id}"
            )

        caps = payload.get("capabilities") or {}
        db_payload = {
            "provider_id": provider.id,
            "model_code": payload["model_code"],
            "display_name": payload["display_name"],
            "capability_tool_calling": bool(caps.get("tool_calling", False)),
            "capability_vision": bool(caps.get("vision", False)),
            "capability_json_mode": bool(caps.get("json_mode", False)),
            "capability_streaming": bool(caps.get("streaming", True)),
            "capability_embeddings": bool(caps.get("embeddings", False)),
            "context_window": payload.get("context_window"),
            "input_cost_per_1k": payload.get("input_cost_per_1k"),
            "output_cost_per_1k": payload.get("output_cost_per_1k"),
            "source": "manual",
            "notes": payload.get("notes"),
            "enabled": payload.get("enabled", True),
        }
        new_id = self.model_repo.create(db_payload)
        return self._serialize(self.model_repo.get(new_id))

    def update(self, model_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Partial update. `provider_id` and `model_code` are immutable."""
        m = self.model_repo.get(model_id)
        if m is None:
            raise ModelNotFound(model_id)
        prov = self.provider_repo.get(m.provider_id)
        if prov is None or prov.user_id != self.user_id:
            raise ModelNotFound(model_id)

        db_patch: Dict[str, Any] = {}
        for k in ("display_name", "context_window", "input_cost_per_1k",
                  "output_cost_per_1k", "enabled", "notes"):
            if k in patch:
                db_patch[k] = patch[k]
        if "capabilities" in patch and isinstance(patch["capabilities"], dict):
            caps = patch["capabilities"]
            for src_key, col in (
                ("tool_calling", "capability_tool_calling"),
                ("vision", "capability_vision"),
                ("json_mode", "capability_json_mode"),
                ("streaming", "capability_streaming"),
                ("embeddings", "capability_embeddings"),
            ):
                if src_key in caps:
                    db_patch[col] = bool(caps[src_key])

        # Explicitly forbid mutating provider_id / model_code
        for forbidden in ("provider_id", "model_code"):
            if forbidden in patch:
                logger.warning("Attempt to mutate immutable field '%s' on model %s",
                               forbidden, model_id)

        updated = self.model_repo.update(model_id, db_patch)
        return self._serialize(updated)

    def delete(self, model_id: str) -> None:
        """Delete a model. Blocks with ModelInUseError when references exist."""
        m = self.model_repo.get(model_id)
        if m is None:
            raise ModelNotFound(model_id)
        prov = self.provider_repo.get(m.provider_id)
        if prov is None or prov.user_id != self.user_id:
            raise ModelNotFound(model_id)

        refs = self.model_repo.get_references(model_id)
        if any(refs.values()):
            raise ModelInUseError(model_id, refs)

        self.model_repo.delete(model_id)
        logger.info("LLMModelService.delete: %s", model_id)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    async def discover(
        self, provider_id: str, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Discover models on the given Provider. Returns enriched items:
          - already_imported, existing_model_id
        Cached for 5 minutes per-provider.
        """
        provider = self._load_user_provider(provider_id)
        spec = self.catalog.get(provider.provider_code)

        cache_key = f"discover:{self.user_id}:{provider_id}"
        if not force_refresh:
            cached = _cache_get(cache_key)
            if cached is not None:
                logger.debug("discover: cache hit %s", cache_key)
                return self._enrich_discovered(provider_id, cached, cached=True)

        # Build gateway + config
        base_url = provider.base_url or spec.default_base_url
        api_key = self.cipher.decrypt(provider.encrypted_api_key) or ""
        config = LLMConfig(
            provider=provider.provider_code,
            model="",
            api_key=api_key,
            base_url=base_url or "",
            timeout_seconds=20,
        )
        gateway = self.catalog.build_gateway(provider.provider_code)

        try:
            discovered: List[DiscoveredModel] = await gateway.list_models(config)
        except NotImplementedError:
            # Providers without a discovery endpoint (e.g. Anthropic static)
            # can delegate directly to the parser with an empty payload.
            from src.infrastructure.llm.discovery_parsers import get_parser as _gp
            parser = _gp(spec.discovery_parser)
            discovered = parser({})

        # Serialise (DiscoveredModel → dict) for cache
        raw_items = [asdict(d) for d in discovered]
        _cache_set(cache_key, raw_items)

        return self._enrich_discovered(provider_id, raw_items, cached=False)

    def _enrich_discovered(
        self, provider_id: str, raw_items: List[Dict[str, Any]], *, cached: bool
    ) -> Dict[str, Any]:
        """Mark which discovered items are already imported for this provider."""
        existing = {
            m.model_code: m.id
            for m in self.model_repo.list_by_provider(provider_id)
        }
        data = []
        for item in raw_items:
            model_code = item.get("model_code")
            data.append({
                **item,
                "already_imported": model_code in existing,
                "existing_model_id": existing.get(model_code),
            })
        return {
            "provider_id": provider_id,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "cached": cached,
            "data": data,
        }

    # ------------------------------------------------------------------
    # Batch import
    # ------------------------------------------------------------------
    def batch_import(
        self, provider_id: str, items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Write selected discovery items to `llm_models`. Skips duplicates."""
        provider = self._load_user_provider(provider_id)
        if not provider.enabled:
            raise ProviderDisabled(
                f"Provider {provider.id} is disabled; enable it before importing models."
            )

        existing_codes = {
            m.model_code for m in self.model_repo.list_by_provider(provider_id)
        }
        payloads: List[Dict[str, Any]] = []
        skipped = 0
        for item in items:
            model_code = item.get("model_code")
            if not model_code:
                skipped += 1
                continue
            if model_code in existing_codes:
                skipped += 1
                continue
            caps = item.get("capabilities") or {}
            payloads.append({
                "provider_id": provider_id,
                "model_code": model_code,
                "display_name": item.get("display_name") or model_code,
                "capability_tool_calling": bool(caps.get("tool_calling", False)),
                "capability_vision": bool(caps.get("vision", False)),
                "capability_json_mode": bool(caps.get("json_mode", False)),
                "capability_streaming": bool(caps.get("streaming", True)),
                "capability_embeddings": bool(caps.get("embeddings", False)),
                "context_window": item.get("context_window"),
                "input_cost_per_1k": item.get("input_cost_per_1k"),
                "output_cost_per_1k": item.get("output_cost_per_1k"),
                "source": "auto_discovered",
                "raw_discovery": item.get("raw"),
                "enabled": True,
            })

        new_ids = self.model_repo.batch_create(payloads) if payloads else []
        new_rows = [self.model_repo.get(i) for i in new_ids]
        return {
            "imported": len(new_ids),
            "skipped": skipped,
            "data": [self._serialize(r) for r in new_rows if r is not None],
        }

    # ------------------------------------------------------------------
    # Usages
    # ------------------------------------------------------------------
    def list_usages(self, model_id: str) -> Dict[str, Any]:
        m = self.model_repo.get(model_id)
        if m is None:
            raise ModelNotFound(model_id)
        prov = self.provider_repo.get(m.provider_id)
        if prov is None or prov.user_id != self.user_id:
            raise ModelNotFound(model_id)
        return self.usages_service.get_model_usages(model_id)
