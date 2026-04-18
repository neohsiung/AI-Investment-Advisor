"""
Domain-specific exceptions for the LLM multi-provider Phase A services.
Raised by service layer; translated to HTTP 4xx at the API layer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class LLMSettingsError(Exception):
    """Base class."""
    error_code: str = "LLM_SETTINGS_ERROR"


class UnknownProviderCode(LLMSettingsError):
    """provider_code not found in ProviderCatalog (YAML seed)."""
    error_code = "UNKNOWN_PROVIDER_CODE"


class ProviderNotFound(LLMSettingsError):
    error_code = "PROVIDER_NOT_FOUND"


class ProviderDisabled(LLMSettingsError):
    """Raised when trying to add Model under a disabled Provider."""
    error_code = "PROVIDER_DISABLED"


class ProviderHasModelsError(LLMSettingsError):
    """409 — deletion refused because provider still owns models."""
    error_code = "PROVIDER_HAS_MODELS"

    def __init__(self, provider_id: str, models_count: int):
        super().__init__(
            f"Provider {provider_id} still owns {models_count} models; "
            f"delete or move them first (or disable this provider)."
        )
        self.provider_id = provider_id
        self.models_count = models_count


class ModelNotFound(LLMSettingsError):
    error_code = "MODEL_NOT_FOUND"


class DuplicateModel(LLMSettingsError):
    """(provider_id, model_code) already exists."""
    error_code = "DUPLICATE_MODEL"


class ModelInUseError(LLMSettingsError):
    """409 — deletion refused because model is referenced by tier/override."""
    error_code = "MODEL_IN_USE"

    def __init__(self, model_id: str, usages: Dict[str, List[Dict[str, Any]]]):
        self.model_id = model_id
        self.usages = usages
        count = sum(len(v) for v in usages.values())
        super().__init__(
            f"Model {model_id} is referenced by {count} binding(s); "
            f"remove references first (or disable this model)."
        )
