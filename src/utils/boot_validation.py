"""
Boot-time fail-fast validation — refuses to start with dev-default secrets.

2026-07-12 (open-source Phase 0): jwt_utils.py's JWT_SECRET silently
defaulted to a literal known string ("your-super-secret-key-for-jwt-signing")
and llm_credential_cipher.py silently falls back to a weaker base64+HMAC
obfuscation when LLM_CREDENTIAL_KEY is absent — both were documented TODOs
("MUST require in production") that nothing ever enforced. Self-hosters
copying `.env.example` verbatim would run with a publicly-known JWT secret
and unencrypted-at-rest provider API keys with no warning.

Only enforced when NODE_ENV=production (matches the existing convention in
docker-compose.prod.yml) — local/dev runs keep the convenient defaults.

開機 fail-fast（開源 Phase 0）：JWT_SECRET 曾預設為已知固定字串,
LLM_CREDENTIAL_KEY 缺席時靜默退回較弱加密——兩者原本只是程式碼裡的 TODO
註解,從未真正被強制執行。只在 NODE_ENV=production 時生效,本機開發維持
既有的便利預設值。
"""
from __future__ import annotations

import os

_KNOWN_DEFAULT_JWT_SECRET = "your-super-secret-key-for-jwt-signing"


class BootValidationError(RuntimeError):
    """Raised when a required production secret is missing or a known default."""


def validate_production_secrets() -> None:
    """
    Call once at app startup (FastAPI lifespan). No-op unless
    NODE_ENV=production. Raises BootValidationError — callers should let it
    propagate so the process exits rather than serve traffic insecurely.
    """
    if os.getenv("NODE_ENV") != "production":
        return

    errors = []

    jwt_secret = os.getenv("JWT_SECRET", _KNOWN_DEFAULT_JWT_SECRET)
    if jwt_secret == _KNOWN_DEFAULT_JWT_SECRET:
        errors.append(
            "JWT_SECRET is unset or equals the publicly-known default "
            "('your-super-secret-key-for-jwt-signing'). Set a random JWT_SECRET "
            "in .env — e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
        )

    if not os.getenv("LLM_CREDENTIAL_KEY"):
        errors.append(
            "LLM_CREDENTIAL_KEY is unset — provider API keys would be stored "
            "at rest with weak base64+HMAC obfuscation instead of Fernet "
            "encryption. Generate one: "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
        )

    if errors:
        raise BootValidationError(
            "Refusing to start in production with insecure defaults:\n- "
            + "\n- ".join(errors)
        )
