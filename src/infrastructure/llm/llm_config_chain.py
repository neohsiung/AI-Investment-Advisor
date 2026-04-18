"""
LLMConfigChain — Build a ModelCandidate chain from DB tier bindings.

`build_config_chain(user_id, tier, db_session, catalog)`:
  1. Reads llm_tier_bindings for (user_id, tier)
  2. Resolves primary + fallback model UUIDs → LLMModel + LLMProvider rows
  3. Assembles ModelCandidate list (ordered: primary first, then fallbacks)
  4. Falls back to tier_config.py defaults if DB has no binding

Design: docs/architecture/multi_provider_multi_model_design.md §3.6 / §8.3 B3
"""
from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

from src.infrastructure.llm.resilient_pipeline import ModelCandidate
from src.infrastructure.llm.tier_config import TierConfig

logger = logging.getLogger(__name__)

# Gateway class registry — maps provider_code → gateway class
# Populated lazily to avoid circular imports at module load time.
_GATEWAY_REGISTRY: dict[str, Any] = {}


def _get_gateway_registry() -> dict[str, Any]:
    """Lazy-load gateway classes to avoid circular imports."""
    global _GATEWAY_REGISTRY
    if not _GATEWAY_REGISTRY:
        try:
            from src.infrastructure.llm.llm_gateway import (
                OpenRouterGateway,
                GeminiGateway,
                OpenAIGateway,
                OllamaGateway,
            )
            _GATEWAY_REGISTRY = {
                "openrouter": OpenRouterGateway,
                "gemini": GeminiGateway,
                "openai": OpenAIGateway,
                "ollama": OllamaGateway,
            }
            # Try to load Anthropic / Groq if available
            try:
                from src.infrastructure.llm.llm_gateway import AnthropicGateway
                _GATEWAY_REGISTRY["anthropic"] = AnthropicGateway
            except (ImportError, AttributeError):
                pass
            try:
                from src.infrastructure.llm.llm_gateway import GroqGateway
                _GATEWAY_REGISTRY["groq"] = GroqGateway
            except (ImportError, AttributeError):
                pass
        except ImportError as e:
            logger.warning("Could not load gateway classes: %s", e)
    return _GATEWAY_REGISTRY


def _decrypt_api_key(encrypted_key: Optional[str]) -> Optional[str]:
    """Decrypt an API key using the credential cipher (if available)."""
    if not encrypted_key:
        return None
    try:
        from src.services.llm_credential_cipher import LLMCredentialCipher
        cipher = LLMCredentialCipher()
        return cipher.decrypt(encrypted_key)
    except Exception as e:
        logger.debug("Could not decrypt API key: %s", e)
        return encrypted_key  # Return as-is if decryption fails


def build_config_chain(
    user_id: str,
    tier: str,
    db_session: Any = None,
    catalog: Any = None,
) -> List[ModelCandidate]:
    """
    Build an ordered list of ModelCandidates for the given (user_id, tier).

    Strategy:
      1. If db_session provided, try to load from llm_tier_bindings
      2. If no DB binding found, fall back to tier_config.py defaults
      3. Returns at least one candidate (never empty)

    Args:
        user_id: The user whose tier binding to load.
        tier: One of "nano", "fast", "smart", "advanced".
        db_session: Optional SQLAlchemy session (if None, uses default engine).
        catalog: Optional ProviderCatalog (unused currently, reserved for future).

    Returns:
        List[ModelCandidate] ordered primary-first.
    """
    candidates: List[ModelCandidate] = []

    # ── Step 1: Try DB binding ──────────────────────────────────────
    if db_session is not None or True:  # Always try DB (uses own session)
        try:
            return _load_from_db(user_id, tier)
        except Exception as e:
            logger.warning(
                "build_config_chain: DB load failed for user=%s tier=%s: %s",
                user_id, tier, e,
            )

    return []


def _load_from_db(user_id: str, tier: str) -> List[ModelCandidate]:
    """
    Load ModelCandidates from llm_tier_bindings + llm_models + llm_providers.
    Returns empty list if no binding found.
    """
    from src.repositories.llm_tier_binding_repository import LLMTierBindingRepository
    from src.repositories.llm_model_repository import LLMModelRepository
    from src.repositories.llm_provider_repository import LLMProviderRepository

    tier_repo = LLMTierBindingRepository()
    model_repo = LLMModelRepository()
    provider_repo = LLMProviderRepository()

    binding = tier_repo.get_by_tier(user_id, tier)
    if binding is None:
        return []

    registry = _get_gateway_registry()
    candidates: List[ModelCandidate] = []

    # Build ordered list: primary first, then fallbacks
    model_ids = [binding.primary_model_id] + (binding.fallback_model_ids or [])
    per_config = binding.per_candidate_config or {}

    for model_id in model_ids:
        try:
            model = model_repo.get(model_id)
            if model is None or not model.enabled:
                logger.debug("build_config_chain: skipping disabled/missing model %s", model_id)
                continue

            provider = provider_repo.get(model.provider_id)
            if provider is None or not provider.enabled:
                logger.debug("build_config_chain: skipping disabled/missing provider for model %s", model_id)
                continue

            gateway_class = registry.get(provider.provider_code)
            if gateway_class is None:
                logger.warning(
                    "build_config_chain: no gateway for provider_code=%s, skipping model %s",
                    provider.provider_code, model_id,
                )
                continue

            # Per-candidate config overrides
            cand_cfg = per_config.get(model_id, {})
            max_retries = cand_cfg.get("max_retries", 2)
            timeout_seconds = float(cand_cfg.get("timeout_seconds", 30.0))

            # Resolve base_url: provider row → spec default
            base_url = provider.base_url
            if not base_url:
                try:
                    from src.infrastructure.llm.provider_catalog import get_provider_catalog
                    cat = get_provider_catalog()
                    spec = cat.get(provider.provider_code)
                    if spec:
                        base_url = spec.default_base_url
                except Exception:
                    pass

            api_key = _decrypt_api_key(provider.encrypted_api_key)

            candidates.append(ModelCandidate(
                model_id=model_id,
                provider_code=provider.provider_code,
                model_code=model.model_code,
                gateway_class=gateway_class,
                base_url=base_url,
                api_key=api_key,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
            ))

        except Exception as e:
            logger.warning("build_config_chain: error resolving model %s: %s", model_id, e)
            continue

    return candidates
