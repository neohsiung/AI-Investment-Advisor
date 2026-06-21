"""Shared API dependencies - avoids circular imports between endpoints and router."""
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer


oauth2_internal = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user_id(request: Request, token: str = Depends(oauth2_internal)) -> str:
    """
    Lazy-load get_current_user_id logic from router to avoid circular imports.
    Same behavior as router.get_current_user_id.
    """
    from src.api.v1.router import get_current_user_id as _get_user_id
    return _get_user_id(request, token)