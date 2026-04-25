"""
Unit tests for src/infrastructure/llm/error_classifier.py

Tests:
  - classify_error() for various exception types and HTTP status codes
  - should_fallback() for each ErrorCategory
"""
import pytest

from src.infrastructure.llm.error_classifier import (
    ErrorCategory,
    classify_error,
    should_fallback,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers — fake exceptions with HTTP status codes
# ──────────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeHTTPError(Exception):
    """Simulates httpx.HTTPStatusError / requests.HTTPError."""
    def __init__(self, status_code: int, message: str = ""):
        self.response = FakeResponse(status_code)
        super().__init__(message or f"HTTP {status_code}")


class FakeAPIError(Exception):
    """Simulates openai.APIStatusError style."""
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(message or f"API error {status_code}")


class FakeTimeoutError(Exception):
    """Simulates httpx.TimeoutException."""
    pass


class FakeConnectionError(Exception):
    """Simulates httpx.ConnectError."""
    pass


# ──────────────────────────────────────────────────────────────────────
# classify_error — HTTP status code based
# ──────────────────────────────────────────────────────────────────────

class TestClassifyErrorByStatusCode:
    def test_429_is_rate_limit(self):
        exc = FakeHTTPError(429, "Too Many Requests")
        assert classify_error(exc) == ErrorCategory.RATE_LIMIT

    def test_401_is_auth_failure(self):
        exc = FakeHTTPError(401, "Unauthorized")
        assert classify_error(exc) == ErrorCategory.AUTH_FAILURE

    def test_403_is_auth_failure(self):
        exc = FakeHTTPError(403, "Forbidden")
        assert classify_error(exc) == ErrorCategory.AUTH_FAILURE

    def test_404_is_model_not_found(self):
        exc = FakeHTTPError(404, "Not Found")
        assert classify_error(exc) == ErrorCategory.MODEL_NOT_FOUND

    def test_408_is_timeout(self):
        exc = FakeHTTPError(408, "Request Timeout")
        assert classify_error(exc) == ErrorCategory.TIMEOUT

    def test_413_is_context_too_long(self):
        exc = FakeHTTPError(413, "Payload Too Large")
        assert classify_error(exc) == ErrorCategory.CONTEXT_TOO_LONG

    def test_500_is_server_error(self):
        exc = FakeHTTPError(500, "Internal Server Error")
        assert classify_error(exc) == ErrorCategory.SERVER_ERROR

    def test_502_is_server_error(self):
        exc = FakeHTTPError(502, "Bad Gateway")
        assert classify_error(exc) == ErrorCategory.SERVER_ERROR

    def test_503_is_server_error(self):
        exc = FakeHTTPError(503, "Service Unavailable")
        assert classify_error(exc) == ErrorCategory.SERVER_ERROR

    def test_504_is_timeout(self):
        exc = FakeHTTPError(504, "Gateway Timeout")
        assert classify_error(exc) == ErrorCategory.TIMEOUT

    def test_api_error_with_status_code(self):
        exc = FakeAPIError(429, "rate limit exceeded")
        assert classify_error(exc) == ErrorCategory.RATE_LIMIT


# ──────────────────────────────────────────────────────────────────────
# classify_error — Exception type name based
# ──────────────────────────────────────────────────────────────────────

class TestClassifyErrorByTypeName:
    def test_timeout_in_class_name(self):
        class ReadTimeoutError(Exception):
            pass
        assert classify_error(ReadTimeoutError("timed out")) == ErrorCategory.TIMEOUT

    def test_connection_in_class_name(self):
        class ConnectionError(Exception):
            pass
        assert classify_error(ConnectionError("connection refused")) == ErrorCategory.NETWORK_ERROR

    def test_ratelimit_in_class_name(self):
        class RateLimitError(Exception):
            pass
        assert classify_error(RateLimitError("rate limit")) == ErrorCategory.RATE_LIMIT


# ──────────────────────────────────────────────────────────────────────
# classify_error — Message keyword based
# ──────────────────────────────────────────────────────────────────────

class TestClassifyErrorByMessage:
    def test_rate_limit_message(self):
        exc = Exception("rate limit exceeded, please retry after 60s")
        assert classify_error(exc) == ErrorCategory.RATE_LIMIT

    def test_quota_exceeded_message(self):
        exc = Exception("quota exceeded for this billing period")
        assert classify_error(exc) == ErrorCategory.RATE_LIMIT

    def test_invalid_api_key_message(self):
        exc = Exception("invalid api key provided")
        assert classify_error(exc) == ErrorCategory.AUTH_FAILURE

    def test_context_length_message(self):
        exc = Exception("context length exceeded: 128000 tokens")
        assert classify_error(exc) == ErrorCategory.CONTEXT_TOO_LONG

    def test_content_policy_message(self):
        exc = Exception("content policy violation detected")
        assert classify_error(exc) == ErrorCategory.CONTENT_POLICY

    def test_model_not_found_message(self):
        exc = Exception("model not found: gpt-99-turbo")
        assert classify_error(exc) == ErrorCategory.MODEL_NOT_FOUND

    def test_connection_refused_message(self):
        exc = Exception("connection refused to localhost:11434")
        assert classify_error(exc) == ErrorCategory.NETWORK_ERROR

    def test_timeout_message(self):
        exc = Exception("request timed out after 30 seconds")
        assert classify_error(exc) == ErrorCategory.TIMEOUT

    def test_unknown_message(self):
        exc = Exception("something completely unexpected happened")
        assert classify_error(exc) == ErrorCategory.UNKNOWN


# ──────────────────────────────────────────────────────────────────────
# should_fallback
# ──────────────────────────────────────────────────────────────────────

class TestShouldFallback:
    @pytest.mark.parametrize("category", [
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.TIMEOUT,
        ErrorCategory.SERVER_ERROR,
        ErrorCategory.NETWORK_ERROR,
        ErrorCategory.MODEL_NOT_FOUND,
    ])
    def test_fallback_eligible_categories(self, category):
        assert should_fallback(category) is True

    @pytest.mark.parametrize("category", [
        ErrorCategory.AUTH_FAILURE,
        ErrorCategory.CONTENT_POLICY,
        ErrorCategory.CONTEXT_TOO_LONG,
        ErrorCategory.UNKNOWN,
    ])
    def test_non_fallback_categories(self, category):
        assert should_fallback(category) is False
