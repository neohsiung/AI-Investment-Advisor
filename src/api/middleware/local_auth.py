"""
Local single-operator access control.

This deployment has one owner and no login. That is safe only while the API is
reachable from loopback alone, so this module does two things:

1. `LocalAuthMiddleware` — when `AUTH_MODE=token`, every request must carry
   `ADMIN_TOKEN`. Applies to the whole app, not just `/api/v1`, so the dashboard
   router, the MCP sub-app and the admin endpoints are covered by the same gate
   as the v1 endpoints.
2. `assert_safe_bind()` — refuses to start when the server is bound to a
   non-loopback interface without a token. A wide-open trading API is the one
   failure mode of removing auth, so it fails loudly at boot rather than
   silently at request time.

單機單人模式：預設免登入，但只在綁 loopback 時成立。
綁到對外介面卻沒設 ADMIN_TOKEN 時直接拒絕啟動。
"""
from __future__ import annotations

import ipaddress
import logging
import os
import secrets
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Paths that must stay reachable without the admin token.
#   /health        — container healthchecks run before any secret is available
#   /webhook       — carries its own per-deployment X-API-Key (webhook_service)
#   /callback      — signed by the channel provider (e.g. X-Line-Signature)
#   /metrics       — scrape endpoint, loopback only
_ALWAYS_OPEN_PREFIXES = ("/health", "/webhook", "/callback", "/metrics")

# Reachable without a token only while AUTH_MODE=none.
_DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")


def auth_mode() -> str:
    mode = os.getenv("AUTH_MODE", "none").strip().lower()
    return mode if mode in ("none", "token") else "none"


def admin_token() -> str:
    return os.getenv("ADMIN_TOKEN", "").strip()


def _is_loopback(host: str) -> bool:
    host = (host or "").strip()
    if not host:
        return False
    if host in ("localhost", "::1"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def assert_safe_bind(host: str | None = None) -> None:
    """
    Raise unless this bind address is safe for the current auth mode.

    IMPORTANT — what this does and does not cover:

    Under Docker this check is a backstop, not the boundary. The container
    legitimately binds 0.0.0.0, and what actually keeps the API private is the
    port publish in docker-compose (`127.0.0.1:8000:8000`), which this process
    cannot see. `HOST`/`UVICORN_HOST` are unset there, so the check reads the
    safe default and passes without having verified anything.

    Where it does bite: a bare `uvicorn --host 0.0.0.0` outside compose, a
    systemd unit, or anyone who sets HOST explicitly — i.e. exactly the manual
    setups where nobody is managing a port mapping for you.

    **If you change the compose port publish away from 127.0.0.1, this function
    will not catch it. Set AUTH_MODE=token as well.**

    在 Docker 下真正的邊界是 compose 的 port 綁定（127.0.0.1），本檢查看不到它，
    僅作為手動啟動（uvicorn/systemd）時的防呆。改動 port 綁定時請一併設定
    AUTH_MODE=token。
    """
    if os.getenv("ALLOW_INSECURE_BIND", "").strip().lower() in ("1", "true", "yes"):
        logger.warning(
            "ALLOW_INSECURE_BIND is set — skipping the non-loopback bind check. "
            "The API may be reachable without authentication."
        )
        return

    bind = (host if host is not None else os.getenv("HOST") or os.getenv("UVICORN_HOST") or "127.0.0.1").strip()

    if _is_loopback(bind):
        return

    if auth_mode() == "token" and admin_token():
        return

    raise RuntimeError(
        f"Refusing to start: the API is bound to {bind!r} (not loopback) while "
        f"AUTH_MODE={auth_mode()!r} and ADMIN_TOKEN is "
        f"{'set' if admin_token() else 'empty'}. "
        "Either bind to 127.0.0.1, or set AUTH_MODE=token together with a "
        "non-empty ADMIN_TOKEN. Override only if you have another gate in "
        "front of this process: ALLOW_INSECURE_BIND=1."
    )


class LocalAuthMiddleware(BaseHTTPMiddleware):
    """Enforce ADMIN_TOKEN app-wide when AUTH_MODE=token."""

    def __init__(self, app, open_prefixes: Iterable[str] = _ALWAYS_OPEN_PREFIXES):
        super().__init__(app)
        self._open_prefixes = tuple(open_prefixes)

    def _exempt(self, path: str) -> bool:
        if path.startswith(self._open_prefixes):
            return True
        # Docs are open only when nothing is gated anyway.
        if auth_mode() == "none" and path.startswith(_DOCS_PREFIXES):
            return True
        return False

    async def dispatch(self, request: Request, call_next):
        if auth_mode() != "token" or self._exempt(request.url.path):
            return await call_next(request)

        # CORS preflight carries no custom headers by definition.
        if request.method == "OPTIONS":
            return await call_next(request)

        expected = admin_token()
        if not expected:
            logger.error("AUTH_MODE=token but ADMIN_TOKEN is empty — denying all requests")
            return JSONResponse(
                {"detail": "Server misconfigured: AUTH_MODE=token requires ADMIN_TOKEN."},
                status_code=500,
            )

        presented = request.headers.get("X-Admin-Token", "").strip()
        if not presented:
            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                presented = auth[7:].strip()
        if not presented:
            presented = (request.cookies.get("access_token") or "").strip()

        if not presented or not secrets.compare_digest(presented, expected):
            return JSONResponse(
                {"detail": "Not authenticated. Provide the admin token via "
                           "'Authorization: Bearer <token>' or 'X-Admin-Token'."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
