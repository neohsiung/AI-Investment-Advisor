from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Dict, Any
from src.utils.jwt_utils import decode_token
from src.utils.logger import setup_logger

# 1. Configuration
logger = setup_logger("API_v1")
api_v1_router = APIRouter()

# 2. Security Setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

from fastapi import Request

def get_current_user_id(request: Request, token: str = Depends(oauth2_scheme)) -> str:
    """
    Primary dependency for identifying the user via Bearer Token or Cookie.
    Ensures strict User Isolation for all v1 endpoints.
    """
    # Fallback to Cookie if Header is missing
    if not token:
        token = request.cookies.get("access_token")
        
    if not token:
        logger.warning("Missing Authorization Bearer token or access_token cookie")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please provide Bearer Token or access_token cookie.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        logger.warning(f"Invalid or expired access token: {token[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity not found in token",
        )
        
    return user_id

# 3. Import and Include Endpoints
from src.api.v1.endpoints import auth, dashboard, transactions, settings, chat
from src.api.v1.endpoints import llm_settings
from src.api.v1.endpoints import ticker_universe

api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

api_v1_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_v1_router.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
api_v1_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["AI Advisor"])

# Ticker Universe
api_v1_router.include_router(
    ticker_universe.router,
    prefix="/ticker-universe",
    tags=["Ticker Universe"],
)

# Phase A: LLM multi-provider settings
api_v1_router.include_router(
    llm_settings.router,
    prefix="/settings/llm",
    tags=["LLM Settings"],
)
