"""
LLMCredentialCipher — encrypts/decrypts Provider API keys at rest.

Strategy:
  1. Read `LLM_CREDENTIAL_KEY` from the environment. If present, use
     `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256) — the industry
     default for symmetric secret storage.
  2. If `cryptography` is not installed OR `LLM_CREDENTIAL_KEY` is absent,
     fall back to a base64 + HMAC obfuscation with a warning log.
     TODO: In production we MUST require Fernet — the fallback only exists
     so the service layer doesn't hard-crash on dev boxes without deps.

The ciphertext is stored as a plain string with prefix:
  - "FERN:<fernet-ciphertext>"           (preferred)
  - "B64H:<base64>.<hex-hmac>"           (fallback)
Plain (legacy) values without prefix are returned as-is on decrypt.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from typing import Optional


logger = logging.getLogger(__name__)

_ENV_KEY = "LLM_CREDENTIAL_KEY"
_FERNET_PREFIX = "FERN:"
_FALLBACK_PREFIX = "B64H:"
_SETTINGS_PREFIX = "ENC:"
_APP_SECRET_KEY_ENV = "APP_SECRET_KEY"


class LLMCredentialCipher:
    """Thin wrapper so services can inject a cipher without knowing the impl."""

    def __init__(self, key: Optional[str] = None):
        self._key = key or os.getenv(_ENV_KEY) or ""
        self._fernet = self._try_build_fernet(self._key)
        # Secondary Fernet for ENC: prefix (uses APP_SECRET_KEY from settings repo)
        self._app_fernet = self._try_build_fernet(os.getenv(_APP_SECRET_KEY_ENV, ""))
        if self._fernet is None:
            logger.warning(
                "LLMCredentialCipher: Fernet unavailable (key=%s, cryptography=?). "
                "Falling back to base64+HMAC obfuscation. TODO: install 'cryptography' "
                "and set LLM_CREDENTIAL_KEY before running in production.",
                "set" if self._key else "missing",
            )

    # ------------------------------------------------------------------
    # Fernet
    # ------------------------------------------------------------------
    @staticmethod
    def _try_build_fernet(key: str):
        if not key:
            return None
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            return None
        try:
            # Fernet expects a URL-safe base64-encoded 32-byte key.
            return Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as exc:
            logger.error("Invalid LLM_CREDENTIAL_KEY for Fernet: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        """Encrypt a plaintext API key. `None` / empty passes through."""
        if plaintext is None:
            return None
        if plaintext == "":
            return ""

        if self._fernet is not None:
            token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
            return f"{_FERNET_PREFIX}{token}"

        # Fallback: base64 payload + HMAC of plaintext (key derived from env or constant)
        derivation_key = (self._key or "llm-cipher-fallback-key").encode("utf-8")
        b64 = base64.urlsafe_b64encode(plaintext.encode("utf-8")).decode("utf-8")
        mac = hmac.new(derivation_key, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{_FALLBACK_PREFIX}{b64}.{mac}"

    def decrypt(self, ciphertext: Optional[str]) -> Optional[str]:
        """Decrypt. Unknown / legacy plain strings are returned as-is."""
        if ciphertext is None:
            return None
        if ciphertext == "":
            return ""

        # ENC: prefix — encrypted by AlchemySettingsRepository with APP_SECRET_KEY
        if ciphertext.startswith(_SETTINGS_PREFIX):
            if self._app_fernet is None:
                logger.error("Cannot decrypt ENC: token — APP_SECRET_KEY Fernet not initialised.")
                return None
            token = ciphertext[len(_SETTINGS_PREFIX):]
            try:
                return self._app_fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except Exception as exc:
                logger.error("ENC: Fernet decrypt failed: %s", exc)
                return None

        if ciphertext.startswith(_FERNET_PREFIX):
            if self._fernet is None:
                logger.error("Cannot decrypt FERN: token — Fernet not initialised.")
                return None
            token = ciphertext[len(_FERNET_PREFIX):]
            try:
                return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except Exception as exc:
                logger.error("Fernet decrypt failed: %s", exc)
                return None

        if ciphertext.startswith(_FALLBACK_PREFIX):
            body = ciphertext[len(_FALLBACK_PREFIX):]
            if "." not in body:
                return None
            b64, _mac = body.rsplit(".", 1)
            try:
                return base64.urlsafe_b64decode(b64.encode("utf-8")).decode("utf-8")
            except Exception as exc:
                logger.error("B64H decrypt failed: %s", exc)
                return None

        # Legacy / plain — return as-is. Caller can decide how to handle.
        return ciphertext

    def mask(self, ciphertext: Optional[str]) -> Optional[str]:
        """
        Return a masked display form (e.g. `sk-****abcd`). Used by API `api_key_masked`.
        Returns None for None, "" for empty.
        """
        if ciphertext is None:
            return None
        if ciphertext == "":
            return ""
        plain = self.decrypt(ciphertext) or ""
        if not plain:
            return "****"
        if len(plain) <= 8:
            return "*" * len(plain)
        return f"{plain[:3]}****{plain[-4:]}"
