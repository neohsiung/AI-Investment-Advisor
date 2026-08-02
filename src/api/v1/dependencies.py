"""Shared API dependencies - avoids circular imports between endpoints and router."""
from typing import Iterator

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, sessionmaker


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


def get_current_user_id(request: Request, token: str = Depends(oauth2_internal)) -> str:
    """
    Lazy-load get_current_user_id logic from router to avoid circular imports.
    Same behavior as router.get_current_user_id.
    """
    from src.api.v1.router import get_current_user_id as _get_user_id
    return _get_user_id(request, token)