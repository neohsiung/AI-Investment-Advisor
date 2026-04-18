"""
ResilientLLMPipeline — Multi-candidate LLM execution with automatic fallback.

Executes a chain of ModelCandidates in order. On each failure:
  - Classifies the error via ErrorClassifier
  - If should_fallback() → tries next candidate
  - If not should_fallback() → re-raises immediately (e.g. AUTH_FAILURE)
  - If all candidates fail → raises AllCandidatesFailedError

Design: docs/architecture/multi_provider_multi_model_design.md §8.3 B3
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from src.domain.interfaces import ILLMGateway, LLMConfig, Message
from src.infrastructure.llm.error_classifier import (
    ErrorCategory,
    classify_error,
    should_fallback,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ModelCandidate:
    """
    A single candidate in the fallback chain.
    Carries all info needed to instantiate a Gateway and call it.
    """
    model_id: str                       # UUID from llm_models
    provider_code: str                  # e.g. "openrouter", "ollama"
    model_code: str                     # e.g. "google/gemini-2.5-pro"
    gateway_class: Type[ILLMGateway]    # Concrete gateway class
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    max_retries: int = 2
    timeout_seconds: float = 30.0
    extra_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AttemptRecord:
    """Record of a single attempt within the pipeline."""
    model_id: str
    provider_code: str
    model_code: str
    started_at: datetime
    duration_ms: float
    error_category: Optional[ErrorCategory]
    success: bool
    error_message: Optional[str] = None


class AllCandidatesFailedError(Exception):
    """Raised when every candidate in the chain has been tried and failed."""

    def __init__(self, attempts: List[AttemptRecord]):
        self.attempts = attempts
        summary = "; ".join(
            f"{a.model_code}({a.error_category})" for a in attempts
        )
        super().__init__(f"All {len(attempts)} candidates failed: {summary}")


# ──────────────────────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────────────────────

class ResilientLLMPipeline:
    """
    Executes a chain of ModelCandidates with automatic fallback.

    Usage:
        pipeline = ResilientLLMPipeline(
            config_chain=[candidate1, candidate2],
            gateway_factory=lambda candidate: candidate.gateway_class(),
        )
        response, attempts = await pipeline.execute(messages)
    """

    def __init__(
        self,
        config_chain: List[ModelCandidate],
        gateway_factory: Optional[Callable[[ModelCandidate], ILLMGateway]] = None,
    ):
        if not config_chain:
            raise ValueError("config_chain must have at least one candidate")
        self.config_chain = config_chain
        self._gateway_factory = gateway_factory or self._default_gateway_factory

    @staticmethod
    def _default_gateway_factory(candidate: ModelCandidate) -> ILLMGateway:
        """Instantiate the gateway class with no arguments (stateless gateways)."""
        return candidate.gateway_class()

    async def execute(
        self,
        messages: List[Message],
        **kwargs: Any,
    ) -> Tuple[str, List[AttemptRecord]]:
        """
        Try each candidate in order.

        Returns:
            (response_text, attempts) on success.

        Raises:
            AllCandidatesFailedError: if every candidate fails with a fallback-eligible error.
            Exception: immediately if a non-fallback error occurs (e.g. AUTH_FAILURE).
        """
        attempts: List[AttemptRecord] = []

        for candidate in self.config_chain:
            started_at = datetime.now(timezone.utc)
            t0 = time.monotonic()

            try:
                gateway = self._gateway_factory(candidate)
                config = self._build_llm_config(candidate, **kwargs)

                logger.info(
                    "ResilientLLMPipeline: trying %s/%s (model_id=%s)",
                    candidate.provider_code,
                    candidate.model_code,
                    candidate.model_id,
                )

                response = await self._call_with_retry(gateway, messages, config, candidate.max_retries)
                duration_ms = (time.monotonic() - t0) * 1000

                attempts.append(AttemptRecord(
                    model_id=candidate.model_id,
                    provider_code=candidate.provider_code,
                    model_code=candidate.model_code,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    error_category=None,
                    success=True,
                ))

                logger.info(
                    "ResilientLLMPipeline: success with %s/%s in %.0fms",
                    candidate.provider_code,
                    candidate.model_code,
                    duration_ms,
                )
                return response, attempts

            except Exception as exc:
                duration_ms = (time.monotonic() - t0) * 1000
                category = classify_error(exc)

                attempts.append(AttemptRecord(
                    model_id=candidate.model_id,
                    provider_code=candidate.provider_code,
                    model_code=candidate.model_code,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    error_category=category,
                    success=False,
                    error_message=str(exc)[:500],
                ))

                logger.warning(
                    "ResilientLLMPipeline: %s/%s failed with %s (%s) in %.0fms",
                    candidate.provider_code,
                    candidate.model_code,
                    category,
                    type(exc).__name__,
                    duration_ms,
                )

                if not should_fallback(category):
                    # Non-transient error — propagate immediately
                    logger.error(
                        "ResilientLLMPipeline: non-fallback error %s, aborting chain",
                        category,
                    )
                    raise

                # Transient error — try next candidate
                logger.info(
                    "ResilientLLMPipeline: falling back to next candidate (remaining: %d)",
                    len(self.config_chain) - len(attempts),
                )

        # All candidates exhausted
        raise AllCandidatesFailedError(attempts)

    async def _call_with_retry(
        self,
        gateway: ILLMGateway,
        messages: List[Message],
        config: LLMConfig,
        max_retries: int,
    ) -> str:
        """
        Call gateway.chat() with up to max_retries retries on transient errors.
        Only retries on should_fallback=True errors (same candidate, not next).
        """
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                return await gateway.chat(messages, config)
            except Exception as exc:
                category = classify_error(exc)
                if not should_fallback(category):
                    raise  # Non-transient — don't retry
                last_exc = exc
                if attempt < max_retries:
                    wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
                    logger.debug(
                        "ResilientLLMPipeline: retry %d/%d after %.1fs",
                        attempt + 1,
                        max_retries,
                        wait,
                    )
                    await asyncio.sleep(wait)

        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _build_llm_config(candidate: ModelCandidate, **kwargs: Any) -> LLMConfig:
        """Build an LLMConfig from a ModelCandidate."""
        return LLMConfig(
            provider=candidate.provider_code,
            model=candidate.model_code,
            api_key=candidate.api_key or "",
            base_url=candidate.base_url,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
            timeout_seconds=candidate.timeout_seconds,
        )
