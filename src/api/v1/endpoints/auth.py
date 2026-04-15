from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from typing import Optional, List
import os

from src.repositories.user_repository import AsyncAlchemyUserRepository
from src.utils.jwt_utils import create_access_token, create_refresh_token
from src.api.v1.router import oauth2_scheme, get_current_user_id

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

# --- Whitelist / Security ---
# 短期內建議將您的 Email 放在 .env 中作為管理員/白名單
AUTH_WHITELIST = os.getenv("AUTH_WHITELIST", "").split(",")

@router.get("/google/login")
async def login(request: Request):
    """
    導向 Google 登入頁面
    """
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
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
        
        # 安全檢查：白名單過濾
        if email not in AUTH_WHITELIST:
            raise HTTPException(status_code=403, detail=f"Access Denied: {email} is not authorized.")

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
        
        redirect_url = f"{frontend_callback_url}?access_token={access_token}&refresh_token={refresh_token}"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        print(f"Auth Callback Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/refresh")
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
async def get_me(user_id: str = Depends(get_current_user_id), user_repo: AsyncAlchemyUserRepository = Depends()):
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
async def logout():
    """
    登出 (目前由前端拋棄 Token 處理，後端可擴充 Token 黑名單)
    """
    return {"status": "success", "message": "Logged out"}
