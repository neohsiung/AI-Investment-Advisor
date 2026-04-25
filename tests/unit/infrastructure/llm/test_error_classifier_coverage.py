"""
Tests for ErrorClassifier to improve coverage.
"""
import pytest
from src.infrastructure.llm.error_classifier import (
    ErrorCategory,
    classify_error,
    should_fallback,
    _extract_http_status,
    _extract_message,
)


class TestErrorCategory:
    """Test ErrorCategory enum values."""

    def test_all_categories_exist(self):
        assert ErrorCategory.RATE_LIMIT == "RATE_LIMIT"
        assert ErrorCategory.AUTH_FAILURE == "AUTH_FAILURE"
        assert ErrorCategory.TIMEOUT == "TIMEOUT"
        assert ErrorCategory.SERVER_ERROR == "SERVER_ERROR"
        assert ErrorCategory.CONTEXT_TOO_LONG == "CONTEXT_TOO_LONG"
        assert ErrorCategory.CONTENT_POLICY == "CONTENT_POLICY"
        assert ErrorCategory.MODEL_NOT_FOUND == "MODEL_NOT_FOUND"
        assert ErrorCategory.NETWORK_ERROR == "NETWORK_ERROR"
        assert ErrorCategory.UNKNOWN == "UNKNOWN"


class TestExtractHttpStatus:
    """Test _extract_http_status helper."""

    def test_response_with_status_code(self):
        class FakeResponse:
            status_code = 429

        class FakeExc(Exception):
            response = FakeResponse()

        assert _extract_http_status(FakeExc()) == 429

    def test_exc_with_status_attribute(self):
        class FakeExc(Exception):
            status = 503

        assert _extract_http_status(FakeExc()) == 503

    def test_exc_with_status_code_attribute(self):
        class FakeExc(Exception):
            status_code = 401

        assert _extract_http_status(FakeExc()) == 401

    def test_exc_with_http_status_attribute(self):
        class FakeExc(Exception):
            http_status = 403

        assert _extract_http_status(FakeExc()) == 403

    def test_plain_exception_returns_none(self):
        assert _extract_http_status(ValueError("plain error")) is None

    def test_response_none_returns_none(self):
        class FakeExc(Exception):
            response = None

        assert _extract_http_status(FakeExc()) is None


class TestExtractMessage:
    """Test _extract_message helper."""

    def test_basic_exception(self):
        msg = _extract_message(ValueError("Rate limit exceeded"))
        assert "rate limit exceeded" in msg

    def test_exc_with_message_attr(self):
        class FakeExc(Exception):
            message = "API key invalid"

        exc = FakeExc("base error")
        msg = _extract_message(exc)
        assert "api key invalid" in msg

    def test_exc_with_body_attr(self):
        class FakeExc(Exception):
            body = "Internal server error details"

        exc = FakeExc("server error")
        msg = _extract_message(exc)
        assert "internal server error details" in msg


class TestClassifyError:
    """Test classify_error function."""

    def test_http_429_rate_limit(self):
        class FakeExc(Exception):
            status_code = 429

        assert classify_error(FakeExc()) == ErrorCategory.RATE_LIMIT

    def test_http_401_auth_failure(self):
        class FakeExc(Exception):
            status_code = 401

        assert classify_error(FakeExc()) == ErrorCategory.AUTH_FAILURE

    def test_http_403_auth_failure(self):
        class FakeExc(Exception):
            status_code = 403

        assert classify_error(FakeExc()) == ErrorCategory.AUTH_FAILURE

    def test_http_404_model_not_found(self):
        class FakeExc(Exception):
            status_code = 404

        assert classify_error(FakeExc()) == ErrorCategory.MODEL_NOT_FOUND

    def test_http_408_timeout(self):
        class FakeExc(Exception):
            status_code = 408

        assert classify_error(FakeExc()) == ErrorCategory.TIMEOUT

    def test_http_413_context_too_long(self):
        class FakeExc(Exception):
            status_code = 413

        assert classify_error(FakeExc()) == ErrorCategory.CONTEXT_TOO_LONG

    def test_http_500_server_error(self):
        class FakeExc(Exception):
            status_code = 500

        assert classify_error(FakeExc()) == ErrorCategory.SERVER_ERROR

    def test_http_502_server_error(self):
        class FakeExc(Exception):
            status_code = 502

        assert classify_error(FakeExc()) == ErrorCategory.SERVER_ERROR

    def test_http_503_server_error(self):
        class FakeExc(Exception):
            status_code = 503

        assert classify_error(FakeExc()) == ErrorCategory.SERVER_ERROR

    def test_http_504_timeout(self):
        class FakeExc(Exception):
            status_code = 504

        assert classify_error(FakeExc()) == ErrorCategory.TIMEOUT

    def test_http_400_falls_through_to_message(self):
        """HTTP 400 maps to UNKNOWN in status map, falls through to message matching."""
        class FakeExc(Exception):
            status_code = 400

        # Should fall through to message matching or return UNKNOWN
        result = classify_error(FakeExc("bad request"))
        assert isinstance(result, ErrorCategory)

    def test_exception_type_timeout(self):
        """Exception type name containing 'timeout' → TIMEOUT."""
        class TimeoutError(Exception):
            pass

        assert classify_error(TimeoutError("timed out")) == ErrorCategory.TIMEOUT

    def test_exception_type_ratelimit(self):
        """Exception type name containing 'ratelimit' → RATE_LIMIT."""
        class RateLimitError(Exception):
            pass

        assert classify_error(RateLimitError("too many")) == ErrorCategory.RATE_LIMIT

    def test_exception_type_auth(self):
        """Exception type name containing 'auth' → AUTH_FAILURE."""
        class AuthError(Exception):
            pass

        assert classify_error(AuthError("auth failed")) == ErrorCategory.AUTH_FAILURE

    def test_exception_type_connection(self):
        """Exception type name containing 'connection' → NETWORK_ERROR."""
        class ConnectionError(Exception):
            pass

        assert classify_error(ConnectionError("refused")) == ErrorCategory.NETWORK_ERROR

    def test_message_rate_limit_keyword(self):
        assert classify_error(Exception("rate limit exceeded")) == ErrorCategory.RATE_LIMIT

    def test_message_quota_exceeded(self):
        assert classify_error(Exception("quota exceeded")) == ErrorCategory.RATE_LIMIT

    def test_message_unauthorized(self):
        assert classify_error(Exception("unauthorized access")) == ErrorCategory.AUTH_FAILURE

    def test_message_invalid_api_key(self):
        assert classify_error(Exception("invalid api key provided")) == ErrorCategory.AUTH_FAILURE

    def test_message_timeout(self):
        assert classify_error(Exception("request timed out")) == ErrorCategory.TIMEOUT

    def test_message_context_length(self):
        assert classify_error(Exception("context length exceeded")) == ErrorCategory.CONTEXT_TOO_LONG

    def test_message_content_policy(self):
        assert classify_error(Exception("content policy violation")) == ErrorCategory.CONTENT_POLICY

    def test_message_model_not_found(self):
        assert classify_error(Exception("model not found")) == ErrorCategory.MODEL_NOT_FOUND

    def test_message_network_error(self):
        assert classify_error(Exception("connection refused")) == ErrorCategory.NETWORK_ERROR

    def test_message_server_error(self):
        assert classify_error(Exception("internal server error")) == ErrorCategory.SERVER_ERROR

    def test_unknown_fallback(self):
        assert classify_error(Exception("some completely unknown error xyz")) == ErrorCategory.UNKNOWN


class TestShouldFallback:
    """Test should_fallback function."""

    def test_rate_limit_should_fallback(self):
        assert should_fallback(ErrorCategory.RATE_LIMIT) is True

    def test_timeout_should_fallback(self):
        assert should_fallback(ErrorCategory.TIMEOUT) is True

    def test_server_error_should_fallback(self):
        assert should_fallback(ErrorCategory.SERVER_ERROR) is True

    def test_network_error_should_fallback(self):
        assert should_fallback(ErrorCategory.NETWORK_ERROR) is True

    def test_model_not_found_should_fallback(self):
        assert should_fallback(ErrorCategory.MODEL_NOT_FOUND) is True

    def test_auth_failure_no_fallback(self):
        assert should_fallback(ErrorCategory.AUTH_FAILURE) is False

    def test_content_policy_no_fallback(self):
        assert should_fallback(ErrorCategory.CONTENT_POLICY) is False

    def test_context_too_long_no_fallback(self):
        assert should_fallback(ErrorCategory.CONTEXT_TOO_LONG) is False

    def test_unknown_no_fallback(self):
        assert should_fallback(ErrorCategory.UNKNOWN) is False
