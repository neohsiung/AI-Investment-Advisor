"""
LLMProviderService — Phase A orchestrator for Provider CRUD + test_connection.

Design contract (see docs/architecture/multi_provider_multi_model_design.md §4.1):
  - Providers are strictly per-user. NO env-variable fallback for credentials.
  - provider_code must exist in ProviderCatalog (YAML seed).
  - API keys are encrypted via `LLMCredentialCipher` before persisting.
  - Deletion is refused (409) when any model under the provider still exists.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.data.models import LLMProvider
from src.domain.interfaces import LLMConfig, PingResult
from src.infrastructure.llm.provider_catalog import ProviderCatalog, get_provider_catalog
from src.repositories.llm_model_repository import LLMModelRepository
from src.repositories.llm_provider_repository import LLMProviderRepository
from src.services.llm_credential_cipher import LLMCredentialCipher
from src.services.llm_settings_errors import (
    ProviderHasModelsError,
    ProviderNotFound,
    UnknownProviderCode,
)
from src.services.llm_usages_service import LLMUsagesService


logger = logging.getLogger(__name__)


class LLMProviderService:
    """Provider CRUD + test_connection + usages."""

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
    # Serialisation helpers
    # ------------------------------------------------------------------
    def _serialize(self, row: LLMProvider) -> Dict[str, Any]:
        """Convert an ORM row → API response dict (with capability resolution)."""
        # Resolve spec (may fail for legacy/imported providers — return empty caps)
        try:
            spec = self.catalog.get(row.provider_code)
            default_caps = {
                "tool_calling": spec.default_capabilities.tool_calling,
                "streaming": spec.default_capabilities.streaming,
                "vision": spec.default_capabilities.vision,
                "json_mode": spec.default_capabilities.json_mode,
                "embeddings": spec.default_capabilities.embeddings,
                "local": spec.default_capabilities.local,
            }
        except KeyError:
            default_caps = {}

        model_count = self.provider_repo.count_models(row.id)
        return {
            "id": row.id,
            "provider_code": row.provider_code,
            "display_name": row.display_name,
            "base_url": row.base_url,
            "api_key_masked": self.cipher.mask(row.encrypted_api_key),
            "enabled": bool(row.enabled),
            "extra_config": row.extra_config or {},
            "default_capabilities": default_caps,
            "health_status": row.health_status,
            "health_detail": row.health_detail,
            "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
            "model_count": model_count,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        rows = self.provider_repo.list_by_user(self.user_id)
        return [self._serialize(r) for r in rows]

    def get(self, provider_id: str) -> Dict[str, Any]:
        row = self.provider_repo.get_for_user(provider_id, self.user_id)
        if row is None:
            raise ProviderNotFound(provider_id)
        return self._serialize(row)

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new Provider instance.

        Required keys: provider_code, display_name.
        Optional: base_url (null → falls back to spec.default_base_url only
        at runtime; we persist null so user sees "inherit default"), api_key
        (plaintext → encrypted), enabled, extra_config.
        """
        provider_code = payload["provider_code"]
        # Validate against YAML catalog (Phase A requirement).
        if provider_code not in self.catalog.codes():
            raise UnknownProviderCode(
                f"provider_code '{provider_code}' is not registered in ProviderCatalog. "
                f"Known: {self.catalog.codes()}"
            )

        encrypted = self.cipher.encrypt(payload.get("api_key"))
        db_payload = {
            "provider_code": provider_code,
            "display_name": payload["display_name"],
            "base_url": payload.get("base_url"),
            "encrypted_api_key": encrypted,
            "enabled": payload.get("enabled", True),
            "extra_config": payload.get("extra_config") or {},
        }
        new_id = self.provider_repo.create(self.user_id, db_payload)
        row = self.provider_repo.get(new_id)
        logger.info("LLMProviderService.create: user=%s provider_id=%s code=%s",
                    self.user_id, new_id, provider_code)
        return self._serialize(row)

    def update(self, provider_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Partial update.
        `api_key` semantics per design §4.1.3:
          - null  → leave unchanged
          - ""    → clear
          - str   → encrypt + replace
        """
        row = self.provider_repo.get_for_user(provider_id, self.user_id)
        if row is None:
            raise ProviderNotFound(provider_id)

        db_patch: Dict[str, Any] = {}
        for k in ("display_name", "base_url", "enabled", "extra_config"):
            if k in patch:
                db_patch[k] = patch[k]

        if "api_key" in patch:
            api_key = patch["api_key"]
            if api_key is None:
                pass  # leave unchanged
            elif api_key == "":
                db_patch["encrypted_api_key"] = None
            else:
                db_patch["encrypted_api_key"] = self.cipher.encrypt(api_key)

        updated = self.provider_repo.update(provider_id, db_patch)
        return self._serialize(updated)

    def delete(self, provider_id: str) -> None:
        """
        Delete a Provider. Raises ProviderHasModelsError if any model exists.
        """
        row = self.provider_repo.get_for_user(provider_id, self.user_id)
        if row is None:
            raise ProviderNotFound(provider_id)
        models_count = self.provider_repo.count_models(provider_id)
        if models_count > 0:
            raise ProviderHasModelsError(provider_id, models_count)
        self.provider_repo.delete(provider_id)
        logger.info("LLMProviderService.delete: %s", provider_id)

    # ------------------------------------------------------------------
    # Test Connection
    # ------------------------------------------------------------------
    async def test_connection(
        self,
        provider_id: str,
        base_url_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Gateway.ping(). The caller can supply optional overrides
        (unsaved form state) for quick verification.

        Persists health_status / health_detail / last_checked_at on success.

        Returns a dict ready for API response (no HTTP wrapping).
        """
        row = self.provider_repo.get_for_user(provider_id, self.user_id)
        if row is None:
            raise ProviderNotFound(provider_id)
        spec = self.catalog.get(row.provider_code)

        base_url = base_url_override or row.base_url or spec.default_base_url
        api_key_plain = (
            api_key_override
            if api_key_override is not None
            else (self.cipher.decrypt(row.encrypted_api_key) or "")
        )

        config = LLMConfig(
            provider=row.provider_code,
            model="",           # ping does not need a model
            api_key=api_key_plain or "",
            base_url=base_url or "",
            timeout_seconds=15,
        )

        gateway = self.catalog.build_gateway(row.provider_code)

        try:
            # NOTE: only OllamaGateway currently implements ping; other
            # Gateways will raise NotImplementedError (default impl in ILLMGateway).
            result: PingResult = await gateway.ping(config)
        except NotImplementedError:
            # Graceful degradation — report "unknown" rather than 5xx.
            logger.info("test_connection: gateway for %s has no ping impl", row.provider_code)
            self.provider_repo.update(provider_id, {
                "health_status": "unknown",
                "health_detail": {"error": "Gateway.ping not implemented"},
                "last_checked_at": datetime.now(timezone.utc),
            })
            return {
                "ok": False,
                "latency_ms": 0.0,
                "detail": None,
                "error": f"Gateway for '{row.provider_code}' does not implement ping()",
            }
        except Exception as exc:
            logger.warning("test_connection failed for %s: %s", provider_id, exc)
            self.provider_repo.update(provider_id, {
                "health_status": "error",
                "health_detail": {"error": str(exc)},
                "last_checked_at": datetime.now(timezone.utc),
            })
            return {"ok": False, "latency_ms": 0.0, "detail": None, "error": "Connection test failed. Please verify provider settings and credentials."}

        self.provider_repo.update(provider_id, {
            "health_status": "ok" if result.ok else "error",
            "health_detail": {
                "latency_ms": result.latency_ms,
                "error": result.error,
                **(result.detail or {}),
            },
            "last_checked_at": datetime.now(timezone.utc),
        })
        return {
            "ok": result.ok,
            "latency_ms": result.latency_ms,
            "detail": result.detail,
            "error": result.error,
        }

    # ------------------------------------------------------------------
    # Usages
    # ------------------------------------------------------------------
    def list_usages(self, provider_id: str) -> Dict[str, Any]:
        """Delegate to UsagesService."""
        row = self.provider_repo.get_for_user(provider_id, self.user_id)
        if row is None:
            raise ProviderNotFound(provider_id)
        return self.usages_service.get_provider_usages(provider_id)
