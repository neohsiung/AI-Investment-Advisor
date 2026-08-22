"""
Provider Catalog — in-memory registry of supported Provider classes.

Loads ProviderSpec entries from YAML seed (default: `config/llm_providers.yaml`)
and provides factory helpers to instantiate the corresponding ILLMGateway.

See docs/architecture/multi_provider_multi_model_design.md §2.2 / §6.2.
"""
from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from src.domain.interfaces import ILLMGateway
from src.infrastructure.llm.provider_spec import ProviderSpec, ProviderCapabilities


logger = logging.getLogger(__name__)


DEFAULT_YAML_PATH = Path(__file__).resolve().parents[3] / "config" / "llm_providers.yaml"


class ProviderCatalog:
    """
    Registry of supported Provider classes (`ProviderSpec`). Singleton-ish by
    convention: call `ProviderCatalog.load_from_yaml()` once at startup.
    """

    def __init__(self, specs: Optional[Iterable[ProviderSpec]] = None):
        self._specs: Dict[str, ProviderSpec] = {}
        if specs:
            for s in specs:
                self.register(s)

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------
    @classmethod
    def load_from_yaml(cls, path: Optional[os.PathLike] = None) -> "ProviderCatalog":
        """Load Provider specs from YAML. Falls back to an empty catalog on I/O error."""
        yaml_path = Path(path) if path else DEFAULT_YAML_PATH
        if not yaml_path.exists():
            logger.warning("Provider YAML not found at %s — starting with empty catalog", yaml_path)
            return cls()

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as exc:  # pragma: no cover — defensive
            logger.error("Failed to parse provider YAML %s: %s", yaml_path, exc)
            return cls()

        specs: List[ProviderSpec] = []
        for entry in raw.get("providers", []) or []:
            try:
                specs.append(cls._spec_from_dict(entry))
            except Exception as exc:
                logger.warning("Skipping invalid provider entry %r: %s", entry, exc)
        logger.info("ProviderCatalog: loaded %d provider specs from %s", len(specs), yaml_path)
        return cls(specs)

    @staticmethod
    def _spec_from_dict(entry: dict) -> ProviderSpec:
        caps_raw = entry.get("default_capabilities") or {}
        caps = ProviderCapabilities(
            tool_calling=bool(caps_raw.get("tool_calling", False)),
            streaming=bool(caps_raw.get("streaming", True)),
            vision=bool(caps_raw.get("vision", False)),
            json_mode=bool(caps_raw.get("json_mode", False)),
            embeddings=bool(caps_raw.get("embeddings", False)),
            local=bool(caps_raw.get("local", False)),
        )
        return ProviderSpec(
            provider_code=entry["provider_code"],
            display_name=entry.get("display_name", entry["provider_code"]),
            gateway_class=entry["gateway_class"],
            default_base_url=entry.get("default_base_url", ""),
            auth_type=entry.get("auth_type", "bearer"),
            api_key_env=entry.get("api_key_env"),
            models_endpoint=entry.get("models_endpoint"),
            discovery_parser=entry.get("discovery_parser", "parse_openai_models"),
            pricing_source=entry.get("pricing_source"),
            healthcheck_endpoint=entry.get("healthcheck_endpoint"),
            default_capabilities=caps,
            notes=entry.get("notes", ""),
        )

    # ------------------------------------------------------------------
    # Lookup & registration
    # ------------------------------------------------------------------
    def register(self, spec: ProviderSpec) -> None:
        """Register (or override) a ProviderSpec by its provider_code."""
        self._specs[spec.provider_code] = spec

    def get(self, provider_code: str) -> ProviderSpec:
        """Return spec by code. Raises KeyError if unknown."""
        aliases = {"nvidia": "nvidia_nim", "nvidia_nim": "nvidia"}
        if provider_code not in self._specs and provider_code in aliases:
            alt_code = aliases[provider_code]
            if alt_code in self._specs:
                return self._specs[alt_code]

        if provider_code not in self._specs:
            raise KeyError(
                f"Unknown provider_code '{provider_code}'. "
                f"Registered: {sorted(self._specs.keys())}"
            )
        return self._specs[provider_code]

    def all(self) -> List[ProviderSpec]:
        """Return all registered specs."""
        return list(self._specs.values())

    def codes(self) -> List[str]:
        """Return list of registered provider_codes."""
        return sorted(self._specs.keys())

    # ------------------------------------------------------------------
    # Gateway factory
    # ------------------------------------------------------------------
    def build_gateway(
        self,
        provider_code: str,
        base_url: Optional[str] = None,   # noqa: ARG002 — reserved for symmetry; caller wires LLMConfig
        api_key: Optional[str] = None,    # noqa: ARG002 — reserved for symmetry
    ) -> ILLMGateway:
        """
        Dynamically import the configured Gateway class and return a fresh
        instance. The caller is responsible for supplying `LLMConfig(base_url,
        api_key)` to individual method calls — we don't bake credentials into
        the instance.
        """
        spec = self.get(provider_code)
        module_path, _, class_name = spec.gateway_class.rpartition(".")
        if not module_path or not class_name:
            raise ValueError(
                f"Invalid gateway_class path '{spec.gateway_class}' for provider {provider_code}"
            )
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise ImportError(
                f"Cannot import gateway module {module_path} for {provider_code}: {exc}"
            ) from exc
        gateway_cls = getattr(module, class_name, None)
        if gateway_cls is None:
            raise AttributeError(
                f"Gateway class {class_name} not found in {module_path}"
            )
        if not issubclass(gateway_cls, ILLMGateway):
            raise TypeError(
                f"Gateway class {spec.gateway_class} must subclass ILLMGateway"
            )
        return gateway_cls()


# ──────────────────────────────────────────────────────────────────────
# Module-level singleton accessor
# ──────────────────────────────────────────────────────────────────────
_catalog: Optional[ProviderCatalog] = None


def get_provider_catalog(force_reload: bool = False) -> ProviderCatalog:
    """Return the process-wide ProviderCatalog, loading on first call."""
    global _catalog
    if _catalog is None or force_reload:
        _catalog = ProviderCatalog.load_from_yaml()
    return _catalog
