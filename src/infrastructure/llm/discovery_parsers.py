"""
Discovery response parsers.

Pure functions that transform raw provider `/models`-style API responses
into a normalised `DiscoveredModel` list (see `src.domain.interfaces`).

Kept pure and side-effect-free so they're trivially unit-testable without
touching the network.

See docs/architecture/multi_provider_multi_model_design.md §2.4 / §4.2.4.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.domain.interfaces import DiscoveredModel


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# OpenAI-compatible
# ──────────────────────────────────────────────────────────────────────
def parse_openai_models(payload: Dict[str, Any]) -> List[DiscoveredModel]:
    """
    Parse `GET /v1/models` response.

    Expected shape (OpenAI / OpenRouter / Groq):
        {"data": [{"id": "gpt-4.1-nano", "object": "model", ...}, ...]}
    """
    items = payload.get("data") or []
    result: List[DiscoveredModel] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_code = item.get("id") or item.get("model")
        if not model_code:
            continue
        display_name = item.get("name") or model_code
        context_window = (
            item.get("context_length")
            or item.get("context_window")
            or item.get("top_provider", {}).get("context_length")
            if isinstance(item.get("top_provider"), dict)
            else item.get("context_length") or item.get("context_window")
        )
        # Pricing (OpenRouter style): {"pricing": {"prompt": "0.0000015", "completion": "..."}}
        pricing = item.get("pricing") or {}
        input_cost = _safe_float(pricing.get("prompt")) if pricing else None
        output_cost = _safe_float(pricing.get("completion")) if pricing else None

        result.append(
            DiscoveredModel(
                model_code=str(model_code),
                display_name=str(display_name),
                context_window=_safe_int(context_window),
                # OpenRouter pricing is already USD-per-token; caller may rescale.
                input_cost_per_1k=input_cost * 1000.0 if input_cost is not None else None,
                output_cost_per_1k=output_cost * 1000.0 if output_cost is not None else None,
                capabilities=None,
                raw=item,
            )
        )
    return result


# ──────────────────────────────────────────────────────────────────────
# Ollama `/api/tags`
# ──────────────────────────────────────────────────────────────────────
def parse_ollama_tags(payload: Dict[str, Any]) -> List[DiscoveredModel]:
    """
    Parse Ollama `GET /api/tags` response:
        {"models": [
            {"name": "qwen2.5:7b", "size": ..., "details": {
                "parameter_size": "7.6B", "family": "qwen2",
                "context_length": 32768  # may be absent
            }}
        ]}
    """
    items = payload.get("models") or []
    result: List[DiscoveredModel] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if not name:
            continue
        details = item.get("details") or {}
        context_window = (
            details.get("context_length")
            or item.get("context_length")
        )
        # Friendly display name: capitalise family + parameter_size if available
        family = details.get("family") or ""
        param_size = details.get("parameter_size") or ""
        display_name = f"{name}".strip()
        if family and param_size:
            display_name = f"{name} ({family}, {param_size})"

        result.append(
            DiscoveredModel(
                model_code=str(name),
                display_name=display_name,
                context_window=_safe_int(context_window),
                input_cost_per_1k=0.0,     # local = free
                output_cost_per_1k=0.0,
                capabilities={
                    "tool_calling": True,
                    "streaming": True,
                    "vision": False,
                    "json_mode": True,
                    "embeddings": True,
                    "local": True,
                },
                raw=item,
            )
        )
    return result


# ──────────────────────────────────────────────────────────────────────
# Google Gemini `GET /v1beta/models`
# ──────────────────────────────────────────────────────────────────────
def parse_gemini_models(payload: Dict[str, Any]) -> List[DiscoveredModel]:
    """
    Parse Gemini `GET /v1beta/models?key=...` response:
        {"models": [
            {"name": "models/gemini-2.5-pro",
             "displayName": "Gemini 2.5 Pro",
             "inputTokenLimit": 1048576,
             "supportedGenerationMethods": ["generateContent", ...]}
        ]}
    """
    items = payload.get("models") or []
    result: List[DiscoveredModel] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        # Strip "models/" prefix so we store plain model_code.
        model_code = name.split("/", 1)[1] if name.startswith("models/") else name
        if not model_code:
            continue
        supported = item.get("supportedGenerationMethods") or []
        capabilities = {
            "streaming": True,
            "tool_calling": "generateContent" in supported,
            "json_mode": True,
            "vision": "vision" in (item.get("displayName") or "").lower()
                      or "pro" in (item.get("displayName") or "").lower(),
            "embeddings": any("embed" in m.lower() for m in supported),
            "local": False,
        }
        result.append(
            DiscoveredModel(
                model_code=model_code,
                display_name=str(item.get("displayName") or model_code),
                context_window=_safe_int(item.get("inputTokenLimit")),
                capabilities=capabilities,
                raw=item,
            )
        )
    return result


# ──────────────────────────────────────────────────────────────────────
# Anthropic (no public /models endpoint → static list)
# ──────────────────────────────────────────────────────────────────────
_ANTHROPIC_STATIC_MODELS = [
    {
        "model_code": "claude-sonnet-4-5-20250929",
        "display_name": "Claude Sonnet 4.5",
        "context_window": 200000,
        "input_cost_per_1k": 0.003,
        "output_cost_per_1k": 0.015,
        "capabilities": {
            "tool_calling": True, "streaming": True, "vision": True,
            "json_mode": False, "embeddings": False, "local": False,
        },
    },
    {
        "model_code": "claude-opus-4-20250514",
        "display_name": "Claude Opus 4",
        "context_window": 200000,
        "input_cost_per_1k": 0.015,
        "output_cost_per_1k": 0.075,
        "capabilities": {
            "tool_calling": True, "streaming": True, "vision": True,
            "json_mode": False, "embeddings": False, "local": False,
        },
    },
    {
        "model_code": "claude-haiku-4-20250514",
        "display_name": "Claude Haiku 4",
        "context_window": 200000,
        "input_cost_per_1k": 0.00025,
        "output_cost_per_1k": 0.00125,
        "capabilities": {
            "tool_calling": True, "streaming": True, "vision": True,
            "json_mode": False, "embeddings": False, "local": False,
        },
    },
]


def parse_anthropic_static(payload: Optional[Dict[str, Any]] = None) -> List[DiscoveredModel]:
    """
    Anthropic has no public `/models` endpoint; return a hard-coded list of
    supported models. `payload` is accepted (and ignored) to keep the
    parser signature uniform for the Catalog.
    """
    result: List[DiscoveredModel] = []
    for item in _ANTHROPIC_STATIC_MODELS:
        result.append(
            DiscoveredModel(
                model_code=item["model_code"],
                display_name=item["display_name"],
                context_window=item.get("context_window"),
                input_cost_per_1k=item.get("input_cost_per_1k"),
                output_cost_per_1k=item.get("output_cost_per_1k"),
                capabilities=item.get("capabilities"),
                raw=item,
            )
        )
    return result


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────
def _safe_int(x: Any) -> Optional[int]:
    try:
        return int(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


# Registry — dynamic dispatcher by name (stored in ProviderSpec.discovery_parser)
PARSER_REGISTRY = {
    "parse_openai_models": parse_openai_models,
    "parse_ollama_tags": parse_ollama_tags,
    "parse_gemini_models": parse_gemini_models,
    "parse_anthropic_static": parse_anthropic_static,
}


def get_parser(name: str):
    """Lookup a parser function by its registered name."""
    if name not in PARSER_REGISTRY:
        raise KeyError(f"Unknown discovery_parser: {name}. "
                       f"Available: {sorted(PARSER_REGISTRY.keys())}")
    return PARSER_REGISTRY[name]
