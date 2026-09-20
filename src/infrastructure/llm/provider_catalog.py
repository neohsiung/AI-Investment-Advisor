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
            aliases=[str(a) for a in (entry.get("aliases") or [])],
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


    # ------------------------------------------------------------------
    # Alias resolution — the single provider-name lookup
    # ------------------------------------------------------------------
    def alias_map(self) -> Dict[str, str]:
        """
        Every accepted spelling -> provider_code.

        Each spec contributes its `provider_code`, its `display_name`, its
        declared `aliases`, and a lowercased form of each. Lowercased forms are
        added only where they do not collide with an existing entry, so an
        explicit alias always wins over a derived one.
        每個 spec 貢獻 provider_code、display_name、宣告的 aliases 及各自的小寫形式；
        小寫形式僅在不衝突時加入，明確宣告的別名優先。
        """
        mapping: Dict[str, str] = {}
        derived: Dict[str, str] = {}
        for spec in self._specs.values():
            names = [spec.provider_code, spec.display_name, *spec.aliases]
            for name in names:
                if not name:
                    continue
                mapping.setdefault(name, spec.provider_code)
                derived.setdefault(name.lower(), spec.provider_code)
        for name, code in derived.items():
            mapping.setdefault(name, code)
        return mapping

    def resolve_code(self, name: str) -> Optional[str]:
        """Map any accepted spelling to a provider_code, or None."""
        if not name:
            return None
        aliases = self.alias_map()
        return aliases.get(name) or aliases.get(name.lower())

    def gateway_class_for(self, name: str) -> type:
        """
        Import and return the gateway class for any accepted provider spelling.

        The `issubclass(ILLMGateway)` check in `build_gateway` is the reason a
        dotted `gateway_class:` in YAML is safe to import; this shares it rather
        than re-implementing the import.
        build_gateway 的 ILLMGateway 子類別檢查是 YAML dotted path 可安全匯入的原因；
        此處共用該檢查，不另行實作匯入。
        """
        code = self.resolve_code(name)
        if code is None:
            raise KeyError(name)
        return type(self.build_gateway(code))

    def gateway_map(self) -> Dict[str, type]:
        """
        Accepted spelling -> gateway class, for the two registries that used to
        hardcode this. A provider whose class cannot be imported is logged and
        omitted: a missing optional gateway must not stop the others loading, but
        it must not appear available either.
        供原本硬編此表的兩處查表使用。無法匯入的 provider 會記錄並略過：
        缺少選用 gateway 不該讓其他 provider 無法載入，但也不能看起來可用。
        """
        classes: Dict[str, type] = {}
        by_code: Dict[str, type] = {}
        for name, code in self.alias_map().items():
            if code not in by_code:
                try:
                    by_code[code] = type(self.build_gateway(code))
                except Exception as exc:
                    logger.error(
                        "Provider '%s' is declared but its gateway cannot be loaded: %s",
                        code, exc,
                    )
                    by_code[code] = None
            if by_code[code] is not None:
                classes[name] = by_code[code]
        return classes


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
