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
                NvidiaGateway,
            )
            _GATEWAY_REGISTRY = {
                "openrouter": OpenRouterGateway,
                "gemini": GeminiGateway,
                "openai": OpenAIGateway,
                "ollama": OllamaGateway,
                "nvidia": NvidiaGateway,  # NVIDIA NIM (OpenAI-compatible)
                # 2026-08-12: the llm_providers row for NIM has
                # provider_code='nvidia_nim', but this registry only had
                # 'nvidia'. build_config_chain looks the code up here and
                # skips the model when it misses, logging
                # "no gateway for provider_code=nvidia_nim" at WARNING — so
                # every NIM-backed candidate was silently dropped from every
                # chain. Registering both spellings is the safe fix: renaming
                # the DB rows would break any other install that already uses
                # 'nvidia_nim'.
                # 2026-08-12：DB 中 NIM 的 provider_code 是 'nvidia_nim'，但此註冊
                # 表只有 'nvidia'，導致所有 NIM 候選模型都被靜默剔除。同時註冊兩種
                # 拼法為安全解法；改 DB 命名會影響其他已使用該值的安裝。
                "nvidia_nim": NvidiaGateway,
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
        # 2026-08-12: raised from debug. Returning the still-encrypted blob is
        # the fail-silent shape — it is a plausible-looking string, so the
        # caller happily builds a candidate with it and the failure resurfaces
        # much later as an opaque 401 from the provider, with nothing linking
        # it back to a cipher problem. The ciphertext is deliberately NOT
        # logged; only the exception type and the fact it happened.
        # 2026-08-12：由 debug 提升。回傳仍加密的字串正是靜默失敗的形狀——它看起來
        # 像合法金鑰，呼叫端會照常建立候選，錯誤直到稍後才以難以追溯的 401 浮現。
        # 此處刻意不記錄密文本身，只記錄例外類型與發生事實。
        logger.warning(
            "Could not decrypt API key (%s); passing the stored value through unchanged, "
            "which will likely surface as a provider auth error", type(e).__name__
        )
        return encrypted_key  # Return as-is if decryption fails


import time

# Chain Cache: (user_id, tier) -> (timestamp, List[ModelCandidate])
_CHAIN_CACHE: dict[tuple[str, str], tuple[float, List[ModelCandidate]]] = {}
_CHAIN_CACHE_TTL = 300  # 5 minutes

def build_config_chain(
    user_id: str,
    tier: str,
    db_session: Any = None,
    catalog: Any = None,
) -> List[ModelCandidate]:
    """
    Build an ordered list of ModelCandidates for the given (user_id, tier).
    Includes a 5-minute TTL cache for performance.
    """
    cache_key = (user_id, tier)
    now = time.time()
    
    if cache_key in _CHAIN_CACHE:
        ts, candidates = _CHAIN_CACHE[cache_key]
        if now - ts < _CHAIN_CACHE_TTL:
            return candidates

    candidates: List[ModelCandidate] = []

    # ── Step 1: Try DB binding ──────────────────────────────────────
    try:
        candidates = _load_from_db(user_id, tier)
    except Exception as e:
        logger.warning(
            "build_config_chain: DB load failed for user=%s tier=%s: %s",
            user_id, tier, e,
        )

    # ── Step 2: STRICT: No defaults allowed (Rule #13) ─────────────────────
    if not candidates:
        logger.warning(
            "build_config_chain: No DB binding found for user=%s tier=%s. [STRICT] Fallback to defaults is disabled.",
            user_id, tier
        )
    
    # Update Cache
    _CHAIN_CACHE[cache_key] = (now, candidates)

    return candidates




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
        binding = tier_repo.get_default_by_tier(tier)
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
            if model is None:
                logger.debug("build_config_chain: skipping missing model %s", model_id)
                continue

            # Resolve provider_code from LLMProvider table
            provider = provider_repo.get(model.provider_id)
            if provider is None:
                logger.warning(
                    "build_config_chain: skipping model %s with missing provider_id %s",
                    model_id, model.provider_id
                )
                continue
                
            provider_code = provider.provider_code
            
            gateway_class = registry.get(provider_code)
            if gateway_class is None:
                logger.warning(
                    "build_config_chain: no gateway for provider_code=%s, skipping model %s",
                    provider_code, model_id,
                )
                continue

            # Per-candidate config overrides
            cand_cfg = per_config.get(model_id, {})
            max_retries = cand_cfg.get("max_retries", 2)
            timeout_seconds = float(cand_cfg.get("timeout_seconds", 120.0))

            # Resolve base_url from provider catalog (fallback if not configured in DB)
            base_url = provider.base_url
            if not base_url:
                try:
                    from src.infrastructure.llm.provider_catalog import get_provider_catalog
                    cat = get_provider_catalog()
                    spec = cat.get(provider_code)
                    if spec and spec.default_base_url:
                        base_url = spec.default_base_url
                except Exception as e:# nosec B110
                    logger.warning(f'Exception in llm_config_chain.py: {e}', exc_info=True)
                    logger.debug("Failed to get base_url from catalog for provider %s", provider_code)

            # Get API key from settings (fallback to provider.encrypted_api_key)
            api_key = _decrypt_api_key(provider.encrypted_api_key)
            try:
                from src.data.database import get_db_engine
                from sqlalchemy import text
                engine = get_db_engine()
                with engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT value FROM settings WHERE key = :key AND user_id = :user_id LIMIT 1"
                    ), {"key": f"{provider_code}_api_key", "user_id": user_id})
                    row = result.fetchone()
                    if row:
                        settings_key = _decrypt_api_key(row[0])
                        # Only override if decryption yielded a usable PLAINTEXT.
                        # Reject anything that still carries an encryption prefix
                        # (ENC:/FERN:/B64H:) — e.g. a double-wrapped ENC(FERN(key))
                        # settings value where only the outer layer peels off would
                        # otherwise overwrite a working provider key and cause 401s.
                        # (2026-07-11)
                        _enc_prefixes = ("ENC:", "FERN:", "B64H:")
                        if settings_key and not settings_key.startswith(_enc_prefixes):
                            api_key = settings_key
                        else:
                            logger.debug(
                                "Settings key for %s not usable (still encrypted?), "
                                "keeping provider key", provider_code
                            )
            except Exception as e:# nosec B110
                logger.warning(f'Exception in llm_config_chain.py: {e}', exc_info=True)
                logger.debug("Failed to get API key for provider %s from settings", provider_code)

            extra_config = {
                "tier": tier,
                # 2026-08-12: fast raised 300 -> 1200. Every model now backing
                # the fast tier is a reasoning model (NIM gpt-oss-120b,
                # Nemotron 3.5 Lightning, Nemotron 3 Super), and they spend
                # tokens on reasoning before emitting the answer. At 300 the
                # Risk agent's JSON was cut mid-string:
                #   Expecting ',' delimiter: line 1 column 200 (char 199)
                # which threw, so CompositorService returned _fallback_score()
                # — a hash of the ticker. The cap meant to save cost was
                # silently converting paid-for calls into fake scores.
                # 2026-08-12：fast 由 300 提高到 1200。目前 fast tier 背後全是推理
                # 模型，會先花 token 推理再輸出答案；300 會把 JSON 從中截斷而拋錯，
                # CompositorService 遂回傳以 ticker 雜湊產生的假分數——原本想省成本
                # 的上限，實際上把已付費的呼叫變成了假分數。
                "max_tokens": 1200 if tier == "fast" else (8192 if tier == "advanced" else 2048),
                "temperature": 0.2 if tier == "fast" else 0.7,
                "headers": {
                    "Cache-Control": "ephem",
                    "X-Prompt-Cache": "true",
                }
            }

            candidates.append(ModelCandidate(
                model_id=model_id,
                provider_code=provider_code,
                model_code=model.model_code,
                gateway_class=gateway_class,
                base_url=base_url,
                api_key=api_key,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                extra_config=extra_config,
            ))

        except Exception as e:
            logger.warning("build_config_chain: error resolving model %s: %s", model_id, e)
            continue

    return candidates
