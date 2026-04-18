"""
Pydantic schemas for LLM multi-provider settings API (Phase A + B).

See docs/architecture/multi_provider_multi_model_design.md §6 / §4.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────
# Shared
# ──────────────────────────────────────────────────────────────────────
class CapabilitiesSchema(BaseModel):
    tool_calling: bool = False
    streaming: bool = True
    vision: bool = False
    json_mode: bool = False
    embeddings: bool = False
    local: bool = False


class ModelCapabilitiesSchema(BaseModel):
    tool_calling: bool = False
    vision: bool = False
    json_mode: bool = False
    streaming: bool = True
    embeddings: bool = False


# ──────────────────────────────────────────────────────────────────────
# Provider
# ──────────────────────────────────────────────────────────────────────
class ProviderCreateRequest(BaseModel):
    provider_code: str = Field(..., description="Must match a code in ProviderCatalog YAML")
    display_name: str = Field(..., min_length=1, max_length=200)
    base_url: Optional[str] = Field(None, description="null → inherit spec.default_base_url at runtime")
    api_key: Optional[str] = Field(None, description="Plaintext; encrypted before persisting")
    enabled: bool = True
    extra_config: Dict[str, Any] = Field(default_factory=dict)


class ProviderUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(
        None,
        description="null=leave unchanged; ''=clear; str=replace",
    )
    enabled: Optional[bool] = None
    extra_config: Optional[Dict[str, Any]] = None


class ProviderResponse(BaseModel):
    id: str
    provider_code: str
    display_name: str
    base_url: Optional[str] = None
    api_key_masked: Optional[str] = None
    enabled: bool
    extra_config: Dict[str, Any] = Field(default_factory=dict)
    default_capabilities: CapabilitiesSchema = Field(default_factory=CapabilitiesSchema)
    health_status: Optional[str] = None
    health_detail: Optional[Dict[str, Any]] = None
    last_checked_at: Optional[str] = None
    model_count: int = 0

    model_config = {"from_attributes": True}


class ProviderTestRequest(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class ProviderTestResponse(BaseModel):
    status: str
    ok: bool
    latency_ms: float
    detail: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# Model
# ──────────────────────────────────────────────────────────────────────
class ModelCreateRequest(BaseModel):
    provider_id: str
    model_code: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=200)
    capabilities: ModelCapabilitiesSchema = Field(default_factory=ModelCapabilitiesSchema)
    context_window: Optional[int] = Field(None, ge=1)
    input_cost_per_1k: Optional[Decimal] = Field(None, ge=0)
    output_cost_per_1k: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None


class ModelUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    capabilities: Optional[ModelCapabilitiesSchema] = None
    context_window: Optional[int] = Field(None, ge=1)
    input_cost_per_1k: Optional[Decimal] = Field(None, ge=0)
    output_cost_per_1k: Optional[Decimal] = Field(None, ge=0)
    enabled: Optional[bool] = None
    notes: Optional[str] = None


class ModelResponse(BaseModel):
    id: str
    provider_id: str
    provider_code: Optional[str] = None
    provider_display_name: Optional[str] = None
    model_code: str
    display_name: str
    capabilities: ModelCapabilitiesSchema = Field(default_factory=ModelCapabilitiesSchema)
    context_window: Optional[int] = None
    input_cost_per_1k: Optional[Decimal] = None
    output_cost_per_1k: Optional[Decimal] = None
    source: Literal["manual", "auto_discovered", "seed"] = "manual"
    enabled: bool = True
    notes: Optional[str] = None
    usages_count: int = 0

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────────────────────────────
class DiscoverRequest(BaseModel):
    force_refresh: bool = False


class DiscoveredModelSchema(BaseModel):
    model_code: str
    display_name: str
    context_window: Optional[int] = None
    input_cost_per_1k: Optional[Decimal] = None
    output_cost_per_1k: Optional[Decimal] = None
    capabilities: Optional[ModelCapabilitiesSchema] = None
    already_imported: bool = False
    existing_model_id: Optional[str] = None


class DiscoverResponse(BaseModel):
    status: str = "success"
    provider_id: str
    discovered_at: str
    cached: bool
    data: List[DiscoveredModelSchema]


# ──────────────────────────────────────────────────────────────────────
# Batch import
# ──────────────────────────────────────────────────────────────────────
class BatchImportItem(BaseModel):
    model_code: str
    display_name: str
    context_window: Optional[int] = None
    input_cost_per_1k: Optional[Decimal] = None
    output_cost_per_1k: Optional[Decimal] = None
    capabilities: Optional[ModelCapabilitiesSchema] = None


class BatchImportRequest(BaseModel):
    provider_id: str
    items: List[BatchImportItem] = Field(..., min_length=1, max_length=50)


class BatchImportResponse(BaseModel):
    status: str = "success"
    imported: int
    skipped: int
    data: List[ModelResponse]


# ──────────────────────────────────────────────────────────────────────
# Usages
# ──────────────────────────────────────────────────────────────────────
class TierUsageItem(BaseModel):
    binding_id: str
    tier: str
    role: Literal["primary", "fallback"]
    user_id: str
    index: Optional[int] = None


class ModelUsagesResponse(BaseModel):
    status: str = "success"
    model_id: str
    model_code: Optional[str] = None
    provider_code: Optional[str] = None
    usages: Dict[str, List[Any]]
    total_references: int
    can_delete: bool


class ProviderModelUsageItem(BaseModel):
    model_id: str
    model_code: str
    tier_bindings: List[TierUsageItem]
    agent_overrides: List[Any] = Field(default_factory=list)


class ProviderUsagesResponse(BaseModel):
    status: str = "success"
    provider_id: str
    total_models: int
    referenced_models: int
    usages: List[ProviderModelUsageItem]


# ──────────────────────────────────────────────────────────────────────
# Tier Binding (Phase B)
# ──────────────────────────────────────────────────────────────────────

class PerCandidateConfig(BaseModel):
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    conditions: Optional[Dict[str, Any]] = None


class TierBindingUpdate(BaseModel):
    """Request body for a single tier binding (used in PUT /tiers)."""
    tier: Literal["nano", "fast", "smart", "advanced"]
    primary_model_id: str = Field(..., description="UUID of the primary model")
    fallback_model_ids: List[str] = Field(
        default_factory=list,
        max_length=4,
        description="Ordered list of fallback model UUIDs (max 4)",
    )
    per_candidate_config: Dict[str, PerCandidateConfig] = Field(
        default_factory=dict,
        description="Per-model config keyed by model_id",
    )
    budget_aware: bool = True


class TierBindingsUpdateRequest(BaseModel):
    """PUT /tiers request body."""
    bindings: List[TierBindingUpdate] = Field(..., min_length=1, max_length=4)


class ModelOut(BaseModel):
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
    capabilities: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class TierBindingOut(BaseModel):
    """Single tier binding with expanded model details."""
    tier: str
    primary_model_id: str
    primary_model: Optional[ModelOut] = None
    fallback_model_ids: List[str] = Field(default_factory=list)
    fallback_models: List[ModelOut] = Field(default_factory=list)
    per_candidate_config: Dict[str, Any] = Field(default_factory=dict)
    budget_aware: bool = True
    estimated_daily_cost: Optional[float] = None

    model_config = {"from_attributes": True}


class TierBindingsResponse(BaseModel):
    """GET /tiers response body."""
    status: str = "success"
    data: List[TierBindingOut]


class ValidationErrorDetail(BaseModel):
    tier: str
    field: str
    message: str


class TierBindingValidationError(BaseModel):
    """422 response body for PUT /tiers validation failures."""
    status: str = "error"
    error_code: str = "TIER_BINDING_VALIDATION_ERROR"
    detail: str = "One or more tier bindings failed validation"
    errors: List[ValidationErrorDetail]


# ──────────────────────────────────────────────────────────────────────
# Agent Override (Phase C)
# ──────────────────────────────────────────────────────────────────────

class AgentOverrideUpdate(BaseModel):
    """Single agent override upsert payload (used in PUT /agent-overrides)."""
    agent_name: str = Field(..., min_length=1, max_length=100)
    override_tier: Optional[Literal["nano", "fast", "smart", "advanced"]] = Field(
        None,
        description="If set, use this tier's chain instead of primary_model_id",
    )
    primary_model_id: Optional[str] = Field(
        None,
        description="UUID of the primary model; overrides tier's primary if set",
    )
    fallback_model_ids: List[str] = Field(
        default_factory=list,
        max_length=4,
        description="Ordered list of fallback model UUIDs (max 4)",
    )
    forbid_local: bool = Field(
        False,
        description="If True, filter out local (Ollama) candidates from the chain",
    )
    forbid_fallback: bool = Field(
        False,
        description="If True, only keep the primary candidate; fail immediately on error",
    )
    enabled: bool = True
    notes: Optional[str] = None


class AgentOverridesUpdateRequest(BaseModel):
    """PUT /agent-overrides request body."""
    overrides: List[AgentOverrideUpdate] = Field(..., min_length=0, max_length=50)


class AgentOverrideOut(BaseModel):
    """Single agent override with expanded model details."""
    id: str
    user_id: str
    agent_name: str
    override_tier: Optional[str] = None
    primary_model_id: Optional[str] = None
    primary_model: Optional[ModelOut] = None
    fallback_model_ids: List[str] = Field(default_factory=list)
    fallback_models: List[ModelOut] = Field(default_factory=list)
    forbid_local: bool = False
    forbid_fallback: bool = False
    enabled: bool = True
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class AgentOverridesResponse(BaseModel):
    """GET /agent-overrides response body."""
    status: str = "success"
    data: List[AgentOverrideOut]


# ──────────────────────────────────────────────────────────────────────
# Generic wrappers
# ──────────────────────────────────────────────────────────────────────
class SuccessListResponse(BaseModel):
    status: str = "success"
    data: List[Any]


class SuccessItemResponse(BaseModel):
    status: str = "success"
    data: Any


class ErrorResponse(BaseModel):
    status: str = "error"
    error_code: str
    detail: str
    models_count: Optional[int] = None
    usages: Optional[Dict[str, Any]] = None
