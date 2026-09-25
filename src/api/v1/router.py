import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Dict, Any, Optional
from src.config.owner import get_owner_id
from src.utils.logger import setup_logger

# 1. Configuration
logger = setup_logger("API_v1")
api_v1_router = APIRouter()

# 2. Security Setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

from fastapi import Request

# Identity lives in dependencies.py, which imports nothing from this package —
# see the note there. Re-exported so the 21 endpoint modules that already do
# `from src.api.v1.router import get_current_user_id` keep working.
# 身分解析實作在 dependencies.py（不依賴本套件）；此處重新匯出以維持既有匯入。
from src.api.v1.dependencies import (  # noqa: F401
    admin_token,
    auth_mode,
    get_current_user_id,
)

# 3. Import and Include Endpoints
from src.api.v1.endpoints import dashboard, transactions, settings, chat
from src.api.v1.endpoints import llm_settings
from src.api.v1.endpoints import ticker_universe
from src.api.v1.endpoints import backtest
from src.api.v1.endpoints import council
from src.api.v1.endpoints import loop_health
from src.api.v1.endpoints import workflows
from src.api.v1.endpoints import agents as agents_ep
from src.api.v1.endpoints import skills as skills_ep
from src.api.v1.endpoints import generated_code as generated_code_ep

# The /auth router (Google OAuth login/callback/exchange/refresh/me/logout)
# is gone. Identity comes from get_current_user_id() above.
# /auth 路由已移除，身分由上方 get_current_user_id() 提供。

api_v1_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_v1_router.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
api_v1_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["AI Advisor"])
api_v1_router.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])
api_v1_router.include_router(council.router, prefix="/council", tags=["Council Decisions"])
api_v1_router.include_router(loop_health.router, prefix="/loop-health", tags=["Loop Health"])
api_v1_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_v1_router.include_router(agents_ep.router, prefix="/agents", tags=["Agents"])
api_v1_router.include_router(skills_ep.router, prefix="/skills", tags=["Skills"])
api_v1_router.include_router(generated_code_ep.router, prefix="/generated-code", tags=["Autonomous Code Synthesis"])

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

