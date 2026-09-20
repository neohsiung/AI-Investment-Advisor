"""Shared API dependencies - avoids circular imports between endpoints and router."""
import os
import secrets

from typing import Iterator, Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, sessionmaker

# Moved here with get_current_user_id — it resolves the single owner.
# 隨 get_current_user_id 一併移入：用於解析單一擁有者。
from src.config.owner import get_owner_id


oauth2_internal = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_db() -> Iterator[Session]:
    """
    Per-request SQLAlchemy session (opt-in unit of work).

    Commits on clean exit, rolls back on exception, always closes. Pass the
    yielded session into repositories via `Repository(engine, session=db)` when
    a handler writes through MORE THAN ONE repository and those writes must
    land together.

    Deliberately opt-in, NOT applied to all endpoints: most handlers make a
    single repository call and gain nothing, while switching them wholesale
    would change transaction semantics (an early failure would start rolling
    back unrelated later work in the same request). Repositories are already
    safe by default — each owns its own session (see src/data/database.py).
    每個請求一個 session（選用）。只在「一個 handler 要跨多個 repository 且必須同生共死」
    時採用；預設不套用到所有端點，因為那會改變交易語意，而 repository 本身已各自安全。
    """
    from src.data.database import get_db_engine

    factory = sessionmaker(bind=get_db_engine(), expire_on_commit=False)
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Identity
#
# This is the real implementation, moved here from router.py.
#
# It lived in router.py while 21 endpoint modules imported it from there — and
# router.py imports those same endpoint modules to mount them. That cycle was
# survivable at application start (the router is imported first) but broke any
# attempt to import an endpoint module directly: `import
# src.api.v1.endpoints.agents` raised "partially initialized module ... has no
# attribute 'router'". It bit twice while building the settings and agents
# endpoints, each time only from tests.
#
# The shim that used to be here delegated BACK to router.py, so it did not break
# the cycle — it just deferred it to call time. Now dependencies.py depends on
# nothing in this package and router.py re-exports from here, so the arrow points
# one way.
#
# 此為真正的實作，自 router.py 移入。原本 21 個 endpoint 模組從 router 匯入它，
# 而 router 又匯入那些 endpoint 以掛載路由——這個循環在應用啟動時可行，
# 但任何直接 import 單一 endpoint 模組的行為都會失敗（建置 settings 與 agents
# 端點時各踩到一次，都是由測試發現）。原本的 shim 會轉回 router，只是把循環延後。
# 現在 dependencies.py 不依賴本套件任何模組，router.py 改為從此處重新匯出。
# ─────────────────────────────────────────────────────────────────────────────

def auth_mode() -> str:
    """
    'none' (default) or 'token'. Read per-call rather than cached at import so
    tests and a restart-free config change both take effect.
    """
    mode = os.getenv("AUTH_MODE", "none").strip().lower()
    return mode if mode in ("none", "token") else "none"


def admin_token() -> str:
    return os.getenv("ADMIN_TOKEN", "").strip()


def _presented_token(request: Request, bearer: Optional[str]) -> str:
    """Token from Authorization: Bearer, X-Admin-Token, or the legacy cookie."""
    if bearer:
        return bearer
    header = request.headers.get("X-Admin-Token", "")
    if header:
        return header.strip()
    return (request.cookies.get("access_token") or "").strip()


def get_current_user_id(request: Request, token: str = Depends(oauth2_internal)) -> str:
    """
    Identity for every v1 endpoint. Signature is unchanged from the multi-tenant
    version on purpose — all 40+ `Depends(get_current_user_id)` call sites and
    the `src.api.v1.dependencies` shim keep working untouched.

    Single-owner deployment:
      * AUTH_MODE=none  (default) — no login; returns the owner id.
      * AUTH_MODE=token           — requires ADMIN_TOKEN via Authorization
                                    Bearer or X-Admin-Token, else 401.

    單機單人部署：預設免登入；對外暴露時用 ADMIN_TOKEN 保護。
    """
    if auth_mode() == "token":
        expected = admin_token()
        if not expected:
            # Refusing is the safe failure: an empty expected token would
            # otherwise make every request authenticate successfully.
            logger.error("AUTH_MODE=token but ADMIN_TOKEN is empty — denying all requests")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfigured: AUTH_MODE=token requires ADMIN_TOKEN.",
            )
        presented = _presented_token(request, token)
        if not presented or not secrets.compare_digest(presented, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated. Provide the admin token via "
                       "'Authorization: Bearer <token>' or 'X-Admin-Token'.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return get_owner_id()
