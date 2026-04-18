"""
Provider Spec — dataclasses describing supported LLM Provider categories.
Loaded from `config/llm_providers.yaml` at application start (Phase A).

See docs/architecture/multi_provider_multi_model_design.md §2.1 / §6.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal


AuthType = Literal["bearer", "api_key_query", "none", "custom"]


@dataclass(frozen=True)
class ProviderCapabilities:
    """
    Default capability flags for a Provider class. Individual Models may
    override these flags in `llm_models.capability_*`.
    """
    tool_calling: bool = False
    streaming: bool = True
    vision: bool = False
    json_mode: bool = False
    embeddings: bool = False
    local: bool = False


@dataclass(frozen=True)
class ProviderSpec:
    """
    Self-description of a supported LLM Provider class (plugin metadata).

    Distinct from the DB `llm_providers` row which stores *user instances*
    (credentials, base_url, enabled). A single ProviderSpec (e.g. `openrouter`)
    can back multiple user instances.
    """
    provider_code: str
    display_name: str
    gateway_class: str                # full import path, e.g. "src.infrastructure.llm.llm_gateway.OllamaGateway"
    default_base_url: str
    auth_type: AuthType
    api_key_env: Optional[str] = None
    models_endpoint: Optional[str] = None
    discovery_parser: str = "parse_openai_models"
    pricing_source: Optional[str] = None     # "openrouter" | "static" | "zero"
    healthcheck_endpoint: Optional[str] = None
    default_capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    notes: str = ""
