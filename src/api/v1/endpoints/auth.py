from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from typing import Optional, List
import os

from src.repositories.user_repository import AsyncAlchemyUserRepository
from src.utils.jwt_utils import create_access_token, create_refresh_token
from src.api.v1.router import oauth2_scheme, get_current_user_id
from src.utils.rate_limit import limiter

from src.utils.logger import setup_logger
logger = setup_logger("API_Auth")
router = APIRouter()

import json

# --- OAuth2 Configuration ---
config = Config(".env")
oauth = OAuth(config)

# 讀取 GCP 原生 client_secret.json (最佳實踐支援 Docker & 本地)
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not CREDENTIALS_PATH:
    # Fallback 檢查 Docker Root 與本地 secrets 目錄
    if os.path.exists("client_secret.json"):
        CREDENTIALS_PATH = "client_secret.json"
    elif os.path.exists("secrets/client_secret.json"):
        CREDENTIALS_PATH = "secrets/client_secret.json"
    else:
        CREDENTIALS_PATH = "client_secret.json"

try:
    with open(CREDENTIALS_PATH, "r") as f:
        google_creds = json.load(f)["web"]
        client_id = google_creds.get("client_id")
        client_secret = google_creds.get("client_secret")
except FileNotFoundError:
    print(f"Warning: {CREDENTIALS_PATH} not found. GCP Login may fail.")
    client_id = None
    client_secret = None

# 註冊 Google OAuth Client
oauth.register(
    name='google',
    client_id=client_id,
    client_secret=client_secret,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# (AUTH_WHITELIST feature removed to support multi-tenant access)

# --- OAuth exchange-code store (2026-07-12) ---
# Single-use, 30s-TTL Redis entry mapping an opaque code to the real JWTs,
# so the OAuth redirect URL never carries the tokens themselves.
_EXCHANGE_PREFIX = "auth:exchange:"
_EXCHANGE_TTL_SECONDS = 30


def _get_redis():
    import redis
    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)


def _store_exchange_code(access_token: str, refresh_token: str) -> str:
    import secrets
    code = secrets.token_urlsafe(32)
    payload = json.dumps({"access_token": access_token, "refresh_token": refresh_token})
    _get_redis().set(f"{_EXCHANGE_PREFIX}{code}", payload, ex=_EXCHANGE_TTL_SECONDS)
    return code


@router.post("/exchange")
@limiter.limit("5/minute")
async def exchange_code(request: Request):
    """
    Redeem a single-use OAuth exchange code (see /google/callback) for the
    real access/refresh tokens. Body: {"code": "..."}. The code is deleted
    on first read — a replay gets 400.
    兌換一次性 OAuth 交換碼取得真正的 tokens。用過即刪，重放即失敗。
    """
    body = await request.json()
    code = body.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    key = f"{_EXCHANGE_PREFIX}{code}"
    r = _get_redis()
    raw = r.get(key)
    if not raw:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    r.delete(key)

    data = json.loads(raw)
    return {"access_token": data["access_token"], "refresh_token": data["refresh_token"]}


@router.get("/google/login")
@limiter.limit("5/minute")
async def login(request: Request):
    """
    導向 Google 登入頁面
    """
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
@limiter.limit("5/minute")
async def auth_callback(request: Request, user_repo: AsyncAlchemyUserRepository = Depends()):
    """
    Google 授權回傳處理：
    1. 驗證 Token
    2. 檢查白名單
    3. 取得/建立本地 User
    4. 核發系統 JWT 並導向前端
    """
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise HTTPException(status_code=401, detail="無法取得使用者資訊")
        
        email = user_info.get('email')
        
        # (Whitelist check removed, all authenticated Google users can proceed)

        # 搜尋或建立使用者
        user = await user_repo.get_by_identity("email", email)
        if not user:
            # 自動為白名單使用者建立帳號
            user_id = await user_repo.create_user(email=email, name=user_info.get('name'))
            user = await user_repo.get_by_id(user_id)
        
        user_id = user['id']
        
        # B2C: Proactively ensure settings are initialized for this user
        # Runs in background to keep auth-flow responsive
        from src.services.settings_service import SettingsService
        import asyncio
        import logging
        
        async def _init_settings_task(uid: str):
            try:
                # Use a sync threadpool executor if SettingsService is sync-heavy
                svc = SettingsService(user_id=uid)
                svc.initialize_user_settings()
                logging.getLogger("Auth").info(f"Settings initialized for user: {uid}")
            except Exception as ex:
                logging.getLogger("Auth").warning(f"Failed to auto-init settings for {uid}: {ex}")

        asyncio.create_task(_init_settings_task(user_id))

        # 核發本系統的 JWT (Bearer Token 流)
        access_token = create_access_token(data={"sub": user_id, "email": email})
        refresh_token = create_refresh_token(data={"sub": user_id})

        # 重定向回前端的 Callback 頁面 (Sprint 3 剛建好的那個)
        frontend_callback_url = os.getenv("FRONTEND_CALLBACK_URL", "http://localhost:3000/auth/callback")

        # 2026-07-12: tokens no longer travel in the redirect URL query
        # string — they leaked into browser history, server access logs,
        # and Referer headers on the very first page the user lands on.
        # Instead of the real JWTs, the redirect carries a short-lived,
        # single-use opaque exchange code; the frontend POSTs it to
        # /auth/exchange to get the real tokens back in a JSON body (never
        # in a URL). Deliberately NOT switched to httpOnly cookies: the
        # dashboard WebSocket endpoint (dashboard_websocket) only accepts
        # access_token as a query param with no cookie fallback, and
        # several components (WebSocketContext, chat page) read the token
        # from localStorage — an httpOnly cookie would silently break all
        # of that. This keeps every existing consumer working unchanged.
        # 2026-07-12：Token 不再走 redirect URL query string——會外洩進瀏覽器
        # 歷史紀錄、伺服器 access log、以及首個頁面的 Referer 標頭。改用短效
        # 一次性 opaque 交換碼，前端 POST 到 /auth/exchange 換回真正的
        # tokens（走 JSON body，不進 URL）。刻意不用 httpOnly cookie：
        # dashboard WebSocket 端點只認 query param 裡的 access_token、無
        # cookie 備援，且多個元件仍從 localStorage 讀 token，httpOnly 會
        # 悄悄弄壞這些既有消費端。
        exchange_code = _store_exchange_code(access_token, refresh_token)
        redirect_url = f"{frontend_callback_url}?code={exchange_code}"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Auth Callback Error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Authentication failed")

@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(request: Request):
    """
    背景續約接口 (由 apiClient 背景發送)
    """
    data = await request.json()
    refresh_token = data.get("refresh_token")
    
    from src.utils.jwt_utils import decode_token
    payload = decode_token(refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid Refresh Token")
    
    user_id = payload.get("sub")
    email = payload.get("email") # Could be none if not stored, wait does refresh token have email? Let's check token creation.
    # 這裡可以加入 DB 檢查 User 是否仍有效
    from src.utils.jwt_utils import create_access_token
    new_access_token = create_access_token(data={"sub": user_id, "email": email} if email else {"sub": user_id})
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.get("/me")
@limiter.limit("20/minute")
async def get_me(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    user_repo: AsyncAlchemyUserRepository = Depends()
):
    """
    獲取當前登入者資訊 (由 useAuth 勾子調用)
    """
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "status": "success",
        "data": {
            "id": user["id"],
            "email": user["email"],
            "name": user.get("name"),
            "is_authenticated": True
        }
    }

@router.post("/logout")
@limiter.limit("5/minute")
async def logout(request: Request):
    """
    登出 (目前由前端拋棄 Token 處理，後端可擴充 Token 黑名單)
    """
    return {"status": "success", "message": "Logged out"}
