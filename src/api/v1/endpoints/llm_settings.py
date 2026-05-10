"""
LLM Settings API — Phase A endpoints.

Mounted at: /api/v1/settings/llm/

Provider endpoints (5 + 1 test + 1 usages + 1 discover + 1 provider-models):
  GET    /providers
  POST   /providers
  PATCH  /providers/{id}
  DELETE /providers/{id}
  POST   /providers/{id}/test
  GET    /providers/{id}/usages
  POST   /providers/{id}/discover-models
  GET    /providers/{id}/models

Model endpoints (4 + 1 batch-import + 1 usages):
  GET    /models
  POST   /models
  POST   /models/batch-import
  PATCH  /models/{id}
  DELETE /models/{id}
  GET    /models/{id}/usages

Tier / Agent-Override endpoints are Phase B / C stubs (return 501).

See docs/architecture/multi_provider_multi_model_design.md §4.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import asdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.router import get_current_user_id
from src.api.v1.schemas.llm_settings_schemas import (
    AgentOverrideOut,
    AgentOverridesResponse,
    AgentOverridesUpdateRequest,
    AgentOverrideUpdate,
    BatchImportRequest,
    BatchImportResponse,
    DiscoverRequest,
    DiscoverResponse,
    ModelCreateRequest,
    ModelOut,
    ModelResponse,
    ModelUpdateRequest,
    ModelUsagesResponse,
    ProviderCreateRequest,
    ProviderResponse,
    ProviderTestRequest,
    ProviderTestResponse,
    ProviderUpdateRequest,
    ProviderUsagesResponse,
    SuccessItemResponse,
    SuccessListResponse,
    TierBindingOut,
    TierBindingsResponse,
    TierBindingsUpdateRequest,
    TierBindingValidationError,
    ValidationErrorDetail,
)
from src.services.llm_agent_override_service import (
    LLMAgentOverrideService,
    AgentOverrideUpdate as ServiceAgentOverrideUpdate,
    AgentOverrideOut as ServiceAgentOverrideOut,
    ModelOutMin,
)
from src.services.llm_model_service import LLMModelService
from src.services.llm_provider_service import LLMProviderService
from src.services.llm_settings_errors import (
    DuplicateModel,
    ModelInUseError,
    ModelNotFound,
    ProviderDisabled,
    ProviderHasModelsError,
    ProviderNotFound,
    UnknownProviderCode,
)
from src.services.llm_tier_binding_service import (
    LLMTierBindingService,
    ModelOut as ServiceModelOut,
    TierBindingOut as ServiceTierBindingOut,
    TierBindingUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────────────
# Dependency factories
# ──────────────────────────────────────────────────────────────────────
def get_provider_service(user_id: str = Depends(get_current_user_id)) -> LLMProviderService:
    return LLMProviderService(user_id=user_id)


def get_model_service(user_id: str = Depends(get_current_user_id)) -> LLMModelService:
    return LLMModelService(user_id=user_id)


def get_tier_service(user_id: str = Depends(get_current_user_id)) -> LLMTierBindingService:
    return LLMTierBindingService(user_id=user_id)


def get_agent_override_service(user_id: str = Depends(get_current_user_id)) -> LLMAgentOverrideService:
    return LLMAgentOverrideService(user_id=user_id)


# ──────────────────────────────────────────────────────────────────────
# Error translation helpers
# ──────────────────────────────────────────────────────────────────────
def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict_provider(exc: ProviderHasModelsError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "status": "error",
            "error_code": exc.error_code,
            "detail": str(exc),
            "models_count": exc.models_count,
        },
    )


def _conflict_model(exc: ModelInUseError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "status": "error",
            "error_code": exc.error_code,
            "detail": str(exc),
            "usages": exc.usages,
        },
    )


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ══════════════════════════════════════════════════════════════════════
# Provider endpoints
# ══════════════════════════════════════════════════════════════════════

@router.get("/providers", summary="List all Providers for the current user")
async def list_providers(
    svc: LLMProviderService = Depends(get_provider_service),
) -> Dict[str, Any]:
    data = svc.list()
    return {"status": "success", "data": data}


@router.post("/providers", status_code=status.HTTP_201_CREATED,
             summary="Create a new Provider instance")
async def create_provider(
    body: ProviderCreateRequest,
    svc: LLMProviderService = Depends(get_provider_service),
) -> Dict[str, Any]:
    try:
        data = svc.create(body.model_dump())
    except UnknownProviderCode as exc:
        raise _bad_request(exc)
    except Exception as exc:
        logger.error("create_provider error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "success", "data": data}


@router.patch("/providers/{provider_id}", summary="Partially update a Provider")
async def update_provider(
    provider_id: str,
    body: ProviderUpdateRequest,
    svc: LLMProviderService = Depends(get_provider_service),
) -> Dict[str, Any]:
    try:
        data = svc.update(provider_id, body.model_dump(exclude_unset=True))
    except ProviderNotFound as exc:
        raise _not_found(exc)
    except Exception as exc:
        logger.error("update_provider error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "success", "data": data}


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a Provider (409 if models exist)")
async def delete_provider(
    provider_id: str,
    svc: LLMProviderService = Depends(get_provider_service),
) -> None:
    try:
        svc.delete(provider_id)
    except ProviderNotFound as exc:
        raise _not_found(exc)
    except ProviderHasModelsError as exc:
        raise _conflict_provider(exc)
    except Exception as exc:
        logger.error("delete_provider error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/providers/{provider_id}/test", summary="Test Provider connectivity (ping)")
async def test_provider(
    provider_id: str,
    body: ProviderTestRequest = ProviderTestRequest(),
    svc: LLMProviderService = Depends(get_provider_service),
) -> Dict[str, Any]:
    try:
        result = await svc.test_connection(
            provider_id,
            base_url_override=body.base_url,
            api_key_override=body.api_key,
        )
    except ProviderNotFound as exc:
        raise _not_found(exc)
    except Exception as exc:
        logger.error("test_provider error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    # Always 200 — failures are expressed in the body (success=false)
    return {
        "status": "success" if result["ok"] else "error",
        "data": {
            "success": result["ok"],
            "latency_ms": result.get("latency_ms"),
            "error": result.get("error"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    }


@router.get("/providers/{provider_id}/usages", summary="Get usage summary for a Provider")
async def get_provider_usages(
    provider_id: str,
    svc: LLMProviderService = Depends(get_provider_service),
) -> Dict[str, Any]:
    try:
        data = svc.list_usages(provider_id)
    except ProviderNotFound as exc:
        raise _not_found(exc)
    return {"status": "success", **data}


@router.post("/providers/{provider_id}/discover-models",
             summary="Discover available models from a Provider")
async def discover_models(
    provider_id: str,
    body: DiscoverRequest = DiscoverRequest(),
    svc: LLMModelService = Depends(get_model_service),
) -> Dict[str, Any]:
    try:
        result = await svc.discover(provider_id, force_refresh=body.force_refresh)
    except ProviderNotFound as exc:
        raise _not_found(exc)
    except Exception as exc:
        logger.error("discover_models error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "success", **result}


@router.get("/providers/{provider_id}/models",
            summary="List models under a specific Provider")
async def list_provider_models(
    provider_id: str,
    enabled: Optional[bool] = Query(None),
    svc: LLMModelService = Depends(get_model_service),
) -> Dict[str, Any]:
    try:
        data = svc.list(provider_id=provider_id, enabled=enabled)
    except ProviderNotFound as exc:
        raise _not_found(exc)
    return {"status": "success", "data": data}


# ══════════════════════════════════════════════════════════════════════
# Model endpoints
# ══════════════════════════════════════════════════════════════════════

@router.get("/models", summary="List all Models (optionally filtered)")
async def list_models(
    provider_id: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    capability: Optional[str] = Query(None),
    svc: LLMModelService = Depends(get_model_service),
) -> Dict[str, Any]:
    try:
        data = svc.list(provider_id=provider_id, enabled=enabled, capability=capability)
    except ProviderNotFound as exc:
        raise _not_found(exc)
    return {"status": "success", "data": data}


@router.post("/models", status_code=status.HTTP_201_CREATED,
             summary="Manually create a Model (source=manual)")
async def create_model(
    body: ModelCreateRequest,
    svc: LLMModelService = Depends(get_model_service),
) -> Dict[str, Any]:
    try:
        data = svc.create(body.model_dump())
    except ProviderNotFound as exc:
        raise _not_found(exc)
    except ProviderDisabled as exc:
        raise _bad_request(exc)
    except DuplicateModel as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception as exc:
        logger.error("create_model error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "success", "data": data}


@router.post("/models/batch-import", summary="Batch import discovered models")
async def batch_import_models(
    body: BatchImportRequest,
    svc: LLMModelService = Depends(get_model_service),
) -> Dict[str, Any]:
    try:
        result = svc.batch_import(
            body.provider_id,
            [item.model_dump() for item in body.items],
        )
    except ProviderNotFound as exc:
        raise _not_found(exc)
    except ProviderDisabled as exc:
        raise _bad_request(exc)
    except Exception as exc:
        logger.error("batch_import_models error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "success", **result}


@router.patch("/models/{model_id}", summary="Partially update a Model")
async def update_model(
    model_id: str,
    body: ModelUpdateRequest,
    svc: LLMModelService = Depends(get_model_service),
) -> Dict[str, Any]:
    try:
        data = svc.update(model_id, body.model_dump(exclude_unset=True))
    except ModelNotFound as exc:
        raise _not_found(exc)
    except Exception as exc:
        logger.error("update_model error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "success", "data": data}


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a Model (409 if referenced by Tier/Override)")
async def delete_model(
    model_id: str,
    svc: LLMModelService = Depends(get_model_service),
) -> None:
    try:
        svc.delete(model_id)
    except ModelNotFound as exc:
        raise _not_found(exc)
    except ModelInUseError as exc:
        raise _conflict_model(exc)
    except Exception as exc:
        logger.error("delete_model error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/models/{model_id}/usages", summary="Get usage references for a Model")
async def get_model_usages(
    model_id: str,
    svc: LLMModelService = Depends(get_model_service),
) -> Dict[str, Any]:
    try:
        data = svc.list_usages(model_id)
    except ModelNotFound as exc:
        raise _not_found(exc)
    return {"status": "success", **data}


# ══════════════════════════════════════════════════════════════════════
# Tier Bindings (Phase B)
# ══════════════════════════════════════════════════════════════════════

def _service_model_out_to_schema(m: Optional[ServiceModelOut]) -> Optional[ModelOut]:
    """Convert service-layer ModelOut to Pydantic schema ModelOut."""
    if m is None:
        return None
    return ModelOut(
        id=m.id,
        model_code=m.model_code,
        display_name=m.display_name,
        provider_id=m.provider_id,
        provider_code=m.provider_code,
        provider_display_name=m.provider_display_name,
        enabled=m.enabled,
        input_cost_per_1k=m.input_cost_per_1k,
        output_cost_per_1k=m.output_cost_per_1k,
        capabilities=m.capabilities,
    )


def _service_tier_out_to_schema(t: ServiceTierBindingOut) -> TierBindingOut:
    """Convert service-layer TierBindingOut to Pydantic schema TierBindingOut."""
    return TierBindingOut(
        tier=t.tier,
        primary_model_id=t.primary_model_id,
        primary_model=_service_model_out_to_schema(t.primary_model),
        fallback_model_ids=t.fallback_model_ids,
        fallback_models=[
            m for m in (_service_model_out_to_schema(fm) for fm in t.fallback_models)
            if m is not None
        ],
        per_candidate_config=t.per_candidate_config,
        budget_aware=t.budget_aware,
        estimated_daily_cost=t.estimated_daily_cost,
    )


@router.get(
    "/tiers",
    summary="List Tier Bindings (GET /tiers)",
    response_model=TierBindingsResponse,
)
async def list_tiers(
    svc: LLMTierBindingService = Depends(get_tier_service),
) -> Dict[str, Any]:
    """
    Return all 4 tier bindings (nano/fast/smart/advanced) for the current user,
    with expanded primary_model and fallback_models details.
    """
    try:
        bindings_by_tier = svc.get_tier_bindings()
        data = [_service_tier_out_to_schema(v) for v in bindings_by_tier.values()]
        return {"status": "success", "data": data}
    except Exception as exc:
        logger.error("list_tiers error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put(
    "/tiers",
    summary="Update Tier Bindings (PUT /tiers)",
    response_model=TierBindingsResponse,
)
async def update_tiers(
    body: TierBindingsUpdateRequest,
    svc: LLMTierBindingService = Depends(get_tier_service),
) -> Dict[str, Any]:
    """
    Bulk-update tier bindings. Validates all chains before persisting.
    Returns 422 with detailed errors on validation failure.
    """
    # Convert Pydantic schema → service dataclass
    updates = [
        TierBindingUpdate(
            tier=b.tier,
            primary_model_id=b.primary_model_id,
            fallback_model_ids=b.fallback_model_ids,
            per_candidate_config={
                k: {"max_retries": v.max_retries, "timeout_seconds": v.timeout_seconds, "conditions": v.conditions}
                for k, v in b.per_candidate_config.items()
            },
            budget_aware=b.budget_aware,
        )
        for b in body.bindings
    ]

    try:
        updated = svc.update_tier_bindings(updates)
        data = [_service_tier_out_to_schema(t) for t in updated]
        return {"status": "success", "data": data}
    except ValueError as exc:
        # Validation errors from service layer
        raw_errors = exc.args[0] if exc.args else []
        if isinstance(raw_errors, list):
            errors = [
                ValidationErrorDetail(
                    tier=e.get("tier", ""),
                    field=e.get("field", ""),
                    message=e.get("message", str(e)),
                )
                for e in raw_errors
            ]
        else:
            errors = [ValidationErrorDetail(tier="", field="", message=str(exc))]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "status": "error",
                "error_code": "TIER_BINDING_VALIDATION_ERROR",
                "detail": "One or more tier bindings failed validation",
                "errors": [e.model_dump() for e in errors],
            },
        )
    except Exception as exc:
        logger.error("update_tiers error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ══════════════════════════════════════════════════════════════════════
# Agent Overrides (Phase C)
# ══════════════════════════════════════════════════════════════════════

def _service_agent_override_out_to_schema(svc_out: ServiceAgentOverrideOut) -> AgentOverrideOut:
    """Convert service AgentOverrideOut → Pydantic AgentOverrideOut schema."""

    def _model_min_to_schema(m: Optional[ModelOutMin]) -> Optional[ModelOut]:
        if m is None:
            return None
        return ModelOut(
            id=m.id,
            model_code=m.model_code,
            display_name=m.display_name,
            provider_id=m.provider_id,
            provider_code=m.provider_code,
            provider_display_name=m.provider_display_name,
            enabled=m.enabled,
            input_cost_per_1k=m.input_cost_per_1k,
            output_cost_per_1k=m.output_cost_per_1k,
            capabilities=m.capabilities,
        )

    return AgentOverrideOut(
        id=svc_out.id,
        user_id=svc_out.user_id,
        agent_name=svc_out.agent_name,
        override_tier=svc_out.override_tier,
        primary_model_id=svc_out.primary_model_id,
        primary_model=_model_min_to_schema(svc_out.primary_model),
        fallback_model_ids=svc_out.fallback_model_ids,
        fallback_models=[_model_min_to_schema(m) for m in svc_out.fallback_models if m],
        forbid_local=svc_out.forbid_local,
        forbid_fallback=svc_out.forbid_fallback,
        enabled=svc_out.enabled,
        notes=svc_out.notes,
    )


@router.get(
    "/agent-overrides",
    summary="List Agent Overrides (GET /agent-overrides)",
    response_model=AgentOverridesResponse,
)
async def list_agent_overrides(
    svc: LLMAgentOverrideService = Depends(get_agent_override_service),
) -> Dict[str, Any]:
    """
    Return all agent overrides for the current user.
    Each override includes expanded primary_model and fallback_models details.
    """
    try:
        overrides = svc.list_overrides()
        data = [_service_agent_override_out_to_schema(o) for o in overrides]
        return {"status": "success", "data": data}
    except Exception as exc:
        logger.error("list_agent_overrides error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put(
    "/agent-overrides",
    summary="Update Agent Overrides (PUT /agent-overrides)",
    response_model=AgentOverridesResponse,
)
async def update_agent_overrides(
    body: AgentOverridesUpdateRequest,
    svc: LLMAgentOverrideService = Depends(get_agent_override_service),
) -> Dict[str, Any]:
    """
    Bulk upsert agent overrides.

    Validates all overrides before persisting:
      - override_tier OR primary_model_id must be set
      - Model FKs must exist and be enabled
    Returns 422 with detailed errors on validation failure.
    """
    updates = [
        ServiceAgentOverrideUpdate(
            agent_name=o.agent_name,
            override_tier=o.override_tier,
            primary_model_id=o.primary_model_id,
            fallback_model_ids=o.fallback_model_ids,
            forbid_local=o.forbid_local,
            forbid_fallback=o.forbid_fallback,
            enabled=o.enabled,
            notes=o.notes,
        )
        for o in body.overrides
    ]

    try:
        updated = svc.update_overrides(updates)
        data = [_service_agent_override_out_to_schema(o) for o in updated]
        return {"status": "success", "data": data}
    except ValueError as exc:
        raw_errors = exc.args[0] if exc.args else []
        if isinstance(raw_errors, list):
            errors = [
                ValidationErrorDetail(
                    tier=e.get("agent_name", ""),
                    field=e.get("field", ""),
                    message=e.get("message", str(e)),
                )
                for e in raw_errors
            ]
        else:
            errors = [ValidationErrorDetail(tier="", field="", message=str(exc))]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "status": "error",
                "error_code": "AGENT_OVERRIDE_VALIDATION_ERROR",
                "detail": "One or more agent overrides failed validation",
                "errors": [e.model_dump() for e in errors],
            },
        )
    except Exception as exc:
        logger.error("update_agent_overrides error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
