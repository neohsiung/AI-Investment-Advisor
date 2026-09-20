"""
Unit tests for boot-time production secret validation.
開機生產機密驗證單元測試。

The JWT_SECRET assertions that used to live here are gone with the JWT itself:
nothing issues or verifies tokens any more, so a check on that variable could
not fail for any reason that mattered. LLM_CREDENTIAL_KEY is the one secret this
function still guards — without it, provider API keys are written to the
database under weak base64+HMAC obfuscation instead of Fernet.

JWT_SECRET 相關斷言隨 JWT 一併移除；本函式現在只守 LLM_CREDENTIAL_KEY，
缺少它會讓 provider API key 以較弱的方式寫入資料庫。
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
    def test_raises_on_missing_credential_key(self):
        with patch.dict("os.environ", {"NODE_ENV": "production"}, clear=True):
            with pytest.raises(BootValidationError, match="LLM_CREDENTIAL_KEY"):
                validate_production_secrets()

    def test_jwt_secret_is_no_longer_required(self):
        """
        A leftover JWT_SECRET (or its absence) must not block startup. Keeping
        the old check would have meant refusing to boot over a variable that no
        longer affects anything.
        殘留或缺少 JWT_SECRET 都不應阻擋啟動——該變數已不影響任何行為。
        """
        env = {"NODE_ENV": "production", "LLM_CREDENTIAL_KEY": "a-real-fernet-key"}
        with patch.dict("os.environ", env, clear=True):
            validate_production_secrets()  # must not raise

    def test_passes_with_proper_secrets(self):
        env = {
            "NODE_ENV": "production",
            "LLM_CREDENTIAL_KEY": "a-real-fernet-key",
        }
        with patch.dict("os.environ", env, clear=True):
            validate_production_secrets()  # must not raise
