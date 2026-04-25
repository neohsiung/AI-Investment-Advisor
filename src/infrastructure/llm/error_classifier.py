"""
ErrorClassifier — Classify LLM gateway exceptions into actionable categories.

Used by ResilientLLMPipeline to decide whether to fallback to the next
candidate or propagate the error immediately.

Design: docs/architecture/multi_provider_multi_model_design.md §8.3 B3
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Categories of LLM gateway errors."""
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_FAILURE = "AUTH_FAILURE"
    TIMEOUT = "TIMEOUT"
    SERVER_ERROR = "SERVER_ERROR"
    CONTEXT_TOO_LONG = "CONTEXT_TOO_LONG"
    CONTENT_POLICY = "CONTENT_POLICY"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN = "UNKNOWN"


# HTTP status codes → ErrorCategory mapping
_HTTP_STATUS_MAP: dict[int, ErrorCategory] = {
    400: ErrorCategory.UNKNOWN,          # Bad Request — inspect message
    401: ErrorCategory.AUTH_FAILURE,
    403: ErrorCategory.AUTH_FAILURE,
    404: ErrorCategory.MODEL_NOT_FOUND,
    408: ErrorCategory.TIMEOUT,
    413: ErrorCategory.CONTEXT_TOO_LONG,
    422: ErrorCategory.UNKNOWN,          # Unprocessable — inspect message
    429: ErrorCategory.RATE_LIMIT,
    500: ErrorCategory.SERVER_ERROR,
    502: ErrorCategory.SERVER_ERROR,
    503: ErrorCategory.SERVER_ERROR,
    504: ErrorCategory.TIMEOUT,
}

# Keywords in error messages → ErrorCategory
_MESSAGE_PATTERNS: list[tuple[list[str], ErrorCategory]] = [
    (["rate limit", "rate_limit", "too many requests", "quota exceeded", "ratelimit"], ErrorCategory.RATE_LIMIT),
    (["unauthorized", "invalid api key", "api key", "authentication", "auth failed", "forbidden"], ErrorCategory.AUTH_FAILURE),
    (["timeout", "timed out", "read timeout", "connect timeout", "deadline exceeded"], ErrorCategory.TIMEOUT),
    (["context length", "context_length", "maximum context", "too long", "token limit", "max_tokens", "context window"], ErrorCategory.CONTEXT_TOO_LONG),
    (["content policy", "content_policy", "safety", "moderation", "harmful", "violates", "blocked"], ErrorCategory.CONTENT_POLICY),
    (["model not found", "model_not_found", "no such model", "does not exist", "invalid model", "unknown model"], ErrorCategory.MODEL_NOT_FOUND),
    (["connection", "network", "dns", "socket", "unreachable", "refused", "connect error"], ErrorCategory.NETWORK_ERROR),
    (["internal server error", "server error", "service unavailable", "bad gateway", "overloaded", "html error page", "provider unavailable", "provider down"], ErrorCategory.SERVER_ERROR),
]


def _extract_http_status(exc: Exception) -> Optional[int]:
    """Try to extract HTTP status code from various exception types."""
    # httpx.HTTPStatusError
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        return exc.response.status_code
    # requests.HTTPError
    if hasattr(exc, "response") and exc.response is not None:
        if hasattr(exc.response, "status_code"):
            return exc.response.status_code
    # aiohttp.ClientResponseError
    if hasattr(exc, "status"):
        return exc.status
    # openai.APIStatusError and similar
    if hasattr(exc, "status_code"):
        return exc.status_code
    # anthropic.APIStatusError
    if hasattr(exc, "http_status"):
        return exc.http_status
    return None


def _extract_message(exc: Exception) -> str:
    """Extract a normalised lowercase error message."""
    parts = [str(exc).lower()]
    # Some SDKs embed the message in .message
    if hasattr(exc, "message") and exc.message:
        parts.append(str(exc.message).lower())
    # Some SDKs embed body in .body
    if hasattr(exc, "body") and exc.body:
        parts.append(str(exc.body).lower())
    return " ".join(parts)


def classify_error(exc: Exception) -> ErrorCategory:
    """
    Classify an exception into an ErrorCategory.

    Priority:
      1. HTTP status code (most reliable)
      2. Exception type name
      3. Error message keyword matching
      4. UNKNOWN fallback
    """
    # 1. HTTP status code
    status_code = _extract_http_status(exc)
    if status_code is not None:
        category = _HTTP_STATUS_MAP.get(status_code)
        if category is not None and category != ErrorCategory.UNKNOWN:
            logger.debug("classify_error: HTTP %d → %s", status_code, category)
            return category

    # 2. Exception type name
    exc_type = type(exc).__name__.lower()
    if "timeout" in exc_type or "timedout" in exc_type:
        return ErrorCategory.TIMEOUT
    if "ratelimit" in exc_type or "rate_limit" in exc_type:
        return ErrorCategory.RATE_LIMIT
    if "auth" in exc_type or "unauthorized" in exc_type or "forbidden" in exc_type:
        return ErrorCategory.AUTH_FAILURE
    if "connection" in exc_type or "network" in exc_type or "connect" in exc_type:
        return ErrorCategory.NETWORK_ERROR

    # 3. Message keyword matching
    message = _extract_message(exc)
    for keywords, category in _MESSAGE_PATTERNS:
        if any(kw in message for kw in keywords):
            logger.debug("classify_error: keyword match → %s (msg=%r)", category, message[:80])
            return category

    # 4. Fallback
    logger.debug("classify_error: UNKNOWN for %s: %s", type(exc).__name__, str(exc)[:80])
    return ErrorCategory.UNKNOWN


def should_fallback(category: ErrorCategory) -> bool:
    """
    Determine whether the pipeline should try the next candidate.

    Fallback-eligible (transient / infrastructure errors):
      RATE_LIMIT, TIMEOUT, SERVER_ERROR, NETWORK_ERROR, MODEL_NOT_FOUND

    Non-fallback (permanent / policy errors — propagate immediately):
      AUTH_FAILURE, CONTENT_POLICY, CONTEXT_TOO_LONG, UNKNOWN
    """
    return category in {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.TIMEOUT,
        ErrorCategory.SERVER_ERROR,
        ErrorCategory.NETWORK_ERROR,
        ErrorCategory.MODEL_NOT_FOUND,
    }
