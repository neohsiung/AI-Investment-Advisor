"""
Boot-time fail-fast validation — refuses to start with dev-default secrets.

2026-07-12 (open-source Phase 0): llm_credential_cipher.py silently falls back
to a weaker base64+HMAC obfuscation when LLM_CREDENTIAL_KEY is absent — a
documented TODO ("MUST require in production") that nothing ever enforced.
Self-hosters copying `.env.example` verbatim would store provider API keys
at rest unencrypted, with no warning.

The JWT_SECRET check that used to sit alongside it is gone: no JWTs are issued
or verified any more, so the variable it guarded has no effect on anything. A
check that cannot fail meaningfully is worse than no check — it reads as
coverage that does not exist. The secret that still matters is
LLM_CREDENTIAL_KEY, and the single-operator access gate is AUTH_MODE /
ADMIN_TOKEN, validated separately in src/api/middleware/local_auth.py.

Only enforced when NODE_ENV=production (matches the existing convention in
docker-compose.prod.yml) — local/dev runs keep the convenient defaults.

開機 fail-fast（開源 Phase 0）：LLM_CREDENTIAL_KEY 缺席時會靜默退回較弱加密。
JWT_SECRET 檢查已移除——系統不再簽發或驗證 JWT，該變數已無作用；
無法真正失敗的檢查比沒有檢查更糟，會讓人誤以為有防護。
存取控制改由 AUTH_MODE / ADMIN_TOKEN 負責（見 local_auth.py）。
"""
from __future__ import annotations

import os

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
