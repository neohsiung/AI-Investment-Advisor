"""
Unit tests for boot-time production secret validation.
開機生產機密驗證單元測試。
"""
import pytest
from unittest.mock import patch

from src.utils.boot_validation import validate_production_secrets, BootValidationError


class TestNonProduction:
    def test_noop_when_not_production(self):
        with patch.dict("os.environ", {"NODE_ENV": "development"}, clear=False):
            validate_production_secrets()  # must not raise regardless of other env

    def test_noop_when_node_env_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            validate_production_secrets()


class TestProductionEnforcement:
    def test_raises_on_default_jwt_secret(self):
        env = {"NODE_ENV": "production", "LLM_CREDENTIAL_KEY": "some-fernet-key"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(BootValidationError, match="JWT_SECRET"):
                validate_production_secrets()

    def test_raises_on_missing_jwt_secret(self):
        env = {"NODE_ENV": "production", "LLM_CREDENTIAL_KEY": "some-fernet-key"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(BootValidationError, match="JWT_SECRET"):
                validate_production_secrets()

    def test_raises_on_missing_credential_key(self):
        env = {"NODE_ENV": "production", "JWT_SECRET": "a-real-random-secret"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(BootValidationError, match="LLM_CREDENTIAL_KEY"):
                validate_production_secrets()

    def test_both_errors_reported_together(self):
        with patch.dict("os.environ", {"NODE_ENV": "production"}, clear=True):
            with pytest.raises(BootValidationError) as exc_info:
                validate_production_secrets()
            msg = str(exc_info.value)
            assert "JWT_SECRET" in msg
            assert "LLM_CREDENTIAL_KEY" in msg

    def test_passes_with_proper_secrets(self):
        env = {
            "NODE_ENV": "production",
            "JWT_SECRET": "a-real-random-secret-value",
            "LLM_CREDENTIAL_KEY": "a-real-fernet-key",
        }
        with patch.dict("os.environ", env, clear=True):
            validate_production_secrets()  # must not raise
