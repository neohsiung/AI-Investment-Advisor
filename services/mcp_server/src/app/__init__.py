"""
MCP Service - FastAPI 微服務入口點
Model Context Protocol Service - FastAPI Microservice Entry Point
"""
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from fastapi import FastAPI, HTTPException, Request, Header, WebSocket, WebSocketDisconnect, Depends, Cookie
from pydantic import BaseModel
from typing import Dict, List, Any, Optional, Union, Awaitable, Tuple, Callable
from datetime import datetime
import logging
import os
import asyncio

from src.utils.logger import setup_logger
logger = setup_logger("MCPService")

from contextlib import asynccontextmanager

# --- OpenTelemetry Setup ---
from src.utils.tracing import init_tracing

# 1. Initialize OpenTelemetry Tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
tracer = init_tracing("mcp_server")
# -------------------------

# Define Models (Restored)
class ToolRegistration(BaseModel):
    """工具註冊請求"""
    name: str
    description: str
    parameters: Dict[str, Any] = {}

class ToolCallRequest(BaseModel):
    """工具調用請求"""
    arguments: Dict[str, Any] = {}

class AgentMessage(BaseModel):
    """Agent 間訊息"""
    sender: str
    receiver: str
    content: str
    context: Optional[Dict[str, Any]] = None

# 工具註冊表
registered_tools: Dict[str, Dict] = {}

# Services Global Instance (Moved to .state to avoid circular imports)
from .state import services

from src.services.market_data_service import MarketDataService
from src.services.search_service import InternetSearchService
from src.services.fred_service import FredService
from src.services.sentinel_service import SentinelService
from src.services.interaction_service import InteractionService

from src.services.socket_manager import socket_manager
from src.utils.jwt_utils import decode_token

async def websocket_broadcast_loop():
    """定期為所有活躍連線推送數據更新 (每 5 秒)"""
    from src.services.dashboard_service import DashboardService
    logger.info("✓ Starting WebSocket Broadcast Loop...")
    while True:
        try:
            active_users = list(socket_manager.active_connections.keys())
            for user_id in active_users:
                # 獲取該使用者的最新數據 (DashboardService 內部有快取，因此 5s 頻率是安全的)
                service = DashboardService(user_id=user_id)
                data = service.prepare_dashboard_data(user_id=user_id)
                
                # 廣播更新
                await socket_manager.broadcast_to_user(user_id, {
                    "type": "PORTFOLIO_UPDATE",
                    "payload": {
                        "summary": data.get('metrics', {}),
                        "positions": data.get('positions_df', {}).to_dict('records') if hasattr(data.get('positions_df'), 'to_dict') else [],
                        "timestamp": datetime.now().isoformat()
                    }
                })
            
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"WebSocket broadcast loop error: {e}")
            await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    (Lifespan) Initialize all services and tools.
    """
    logger.info("Initializing MCP Services...")
    
    # 啟動 WebSocket 廣播任務
    broadcast_task = asyncio.create_task(websocket_broadcast_loop())
    
    try:
        # 0. Resolve Primary User UUID (Rule #4.3 - No 'system' user)
        # 透過資料庫解析主要使用者 UUID，確保所有服務綁定至真實上下文。
        from src.repositories.user_repository import AlchemyUserRepository
        from sqlalchemy import text
        user_repo = AlchemyUserRepository()
        primary_user_id = None
        
        try:
            with user_repo.engine.connect() as conn:
                row = conn.execute(text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).fetchone()
                if row:
                    primary_user_id = row[0]
                    logger.info(f"✓ MCP Services binding to primary user: {primary_user_id}")
                else:
                    logger.warning("⚠️ No users found in database. Services may fail to initialize correctly.")
        except Exception as e:
            logger.error(f"Failed to resolve primary user from DB: {e}")

        if not primary_user_id:
            # Fallback for bootstrap/tests if DB is empty
            primary_user_id = os.getenv("PRIMARY_USER_ID")
            if primary_user_id:
                logger.info(f"Using PRIMARY_USER_ID from environment: {primary_user_id}")
            else:
                 # Last resort fallback to prevent startup crash if absolutely necessary, 
                 # but logged as ERROR as per user instruction.
                 logger.error("CRITICAL: No user context found. SettingsService WILL fail.")

        # 1. Instantiate Services
        services["market"] = MarketDataService(user_id=primary_user_id)
        services["search"] = InternetSearchService(user_id=primary_user_id)
        services["fred"] = FredService(user_id=primary_user_id)
        services["sentinel"] = SentinelService(
            market_service=services["market"],
            search_service=services["search"],
            user_id=primary_user_id
        )
        # services["github"] = GitHubService() # REMOVED (Shift to text-based records)
        
        from src.services.webhook_service import webhook_service_instance
        # sentinel is now instantiated per-request in webhook_service
        
        # Initialize Settings Service for Adapter Configuration
        from src.services.settings_service import SettingsService
        from src.infrastructure.channels.channel_factory import ChannelFactory
        from src.infrastructure.nlp.intent_classifier import IntentClassifier
        
        # v5.8.1: Global settings now bound to primary user context
        settings_svc_global = SettingsService(db_path=None, user_id=primary_user_id)
        settings_global = settings_svc_global.get_all_settings()
        
        # Create Adapters via Factory
        adapters = ChannelFactory.create_adapters(settings_global)
        
        # Create Intent Classifier
        intent_classifier = IntentClassifier()
        
        services["interaction"] = InteractionService(
            adapters=adapters,
            intent_classifier=intent_classifier,
            settings_service=settings_svc_global
        )
        # Phase 5: Register InteractionService in socket_manager for bidirectional updates
        from src.services.socket_manager import socket_manager
        socket_manager.set_interaction_service(services["interaction"])

        
        from src.services.dashboard_service import DashboardService
        services["dashboard"] = DashboardService(user_id=primary_user_id)
        
        # 2. Start Real-time Streaming (Polygon WebSocket)
        try:
            from src.infrastructure.streams.polygon_stream_client import PolygonStreamClient
            # [Optimization] v1.2: Resolve active tickers from portfolio to filter stream
            from src.services.transaction_service import TransactionService
            tx_svc = TransactionService()
            # Use correct method name: get_user_tickers with only_active=True
            active_tickers = tx_svc.get_user_tickers(user_id=primary_user_id, only_active=True)
            # Default fallback tickers if portfolio is empty
            filter_tickers = active_tickers if active_tickers else ["AAPL", "TSLA", "MSFT", "NVDA", "GOOG"]
            
            stream_client = PolygonStreamClient(user_id=primary_user_id)
            stream_client.add_callback(services["sentinel"].on_realtime_event)
            # [Optimization] v1.2: Subscribe only to relevant tickers
            asyncio.create_task(stream_client.connect(tickers=filter_tickers)) 
            services["polygon_stream"] = stream_client
            logger.info(f"Polygon Real-time Stream Client started for {len(filter_tickers)} tickers: {filter_tickers}")
        except Exception as e:
            logger.error(f"Failed to start Polygon Stream client: {e}")

        # 3. Register Tools
        tool_definitions = [
            # Market Data (FMP/Polygon)
            {
                "name": "get_current_price",
                "description": "取得即時股價 (Real-time Price)",
                "parameters": {"ticker": "股票代碼 (e.g., AAPL)"}
            },
            {
                "name": "get_valuation", 
                "description": "取得估值與財務比率 (Valuation & Ratios) - FMP Starter", 
                "parameters": {"ticker": "股票代碼"}
            },
            {
                "name": "get_company_profile",
                "description": "取得公司基本資料 (Profile) - FMP/Polygon",
                "parameters": {"ticker": "股票代碼"}
            },
            
            # Smart Search (Tavily)
            {
                "name": "web_search", 
                "description": "搜尋財經新聞與分析 (Financial Search) - Tavily Researcher", 
                "parameters": {"query": "搜尋關鍵字"}
            },
            
            # Macro (FRED)
            {
                "name": "get_macro_indicators", 
                "description": "取得總經指標 (Macro Data) - FRED", 
                "parameters": {}
            }
        ]

        for tool in tool_definitions:
            registered_tools[tool["name"]] = tool
            
        logger.info(f"MCP Services & {len(tool_definitions)} Tools Ready.")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        # Non-blocking, but tools won't work
    
    yield
    
    # Teardown
    services.clear()

app = FastAPI(
    title="MCP Server",
    description="Model Context Protocol 工具伺服器 | Tool Server for Agent Mesh",
    version="1.1.0",
    lifespan=lifespan
)

# --- CORS Middleware (New Phase 2) ---
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument the FastAPI app for OTel
FastAPIInstrumentor.instrument_app(app)

@app.get("/")
async def root():
    """健康檢查端點 (Root)"""
    return {"status": "ok", "service": "mcp_server", "version": "1.1.0"}

@app.get("/health")
async def health():
    """健康檢查 (Health Check)"""
    return {"status": "healthy"}

@app.post("/tools/register")
async def register_tool(tool: ToolRegistration):
    """
    註冊工具至 MCP Server
    Register a tool to MCP Server
    """
    registered_tools[tool.name] = {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters
    }
    logger.info(f"Tool registered: {tool.name}")
    return {"status": "registered", "tool": tool.name}

@app.get("/tools/list")
async def list_tools():
    """
    列出所有已註冊工具
    List all registered tools
    """
    return {
        "count": len(registered_tools),
        "tools": list(registered_tools.values())
    }

@app.post("/agents/message")
async def agent_message(message: AgentMessage):
    """
    Agent 間訊息傳遞
    Inter-agent message passing
    """
    logger.info(f"Message from {message.sender} to {message.receiver}: {message.content[:50]}...")
    
    return {
        "status": "delivered",
        "sender": message.sender,
        "receiver": message.receiver
    }

@app.post("/tools/call/{tool_name}")
async def call_tool(tool_name: str, request: ToolCallRequest):
    """
    Execute tool logic via internal services.
    """
    if tool_name not in registered_tools:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    
    args = request.arguments
    result = None
    
    try:
        # Dispatch Logic
        if tool_name == "get_current_price":
            ticker = args.get("ticker")
            if ticker:
                prices = services["market"].get_current_prices([ticker])
                result = prices.get(ticker)
                
        elif tool_name == "get_valuation":
            ticker = args.get("ticker")
            if ticker:
                result = services["market"].get_valuation_metrics(ticker)
                
        elif tool_name == "get_company_profile":
             ticker = args.get("ticker")
             if ticker:
                 result = services["market"].get_financials(ticker)
                 
        elif tool_name == "web_search":
            query = args.get("query")
            if query:
                result = services["search"].search_financial_context(query)
                
        elif tool_name == "get_macro_indicators":
            result = services["market"].get_macro_data()
            
        else:
            result = "Tool implementation not found in dispatch logic."
            
        logger.info(f"Tool {tool_name} executed. Result size: {len(str(result)) if result else 0} chars")
        
        return {
            "status": "success",
            "tool": tool_name,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Dashboard Router (New Phase 2) ---
from src.services.dashboard_router import dashboard_router
app.include_router(dashboard_router, prefix="/api/dashboard")

# --- Webhook Router & Inbound Adapters ---
from src.services.webhook_service import webhook_router

app.include_router(webhook_router, prefix="/webhook")
# --- LINE Bot Webhook Support (via InteractionService) ---
@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """
    LINE Messaging API Webhook Callback
    Routed to InteractionService -> LineBotAdapter
    v4.5: Using raw bytes for signature verification to avoid encoding issues.
    """
    interaction_svc = services.get("interaction")
    if not interaction_svc:
        logger.warning("InteractionService not initialized yet.")
        raise HTTPException(status_code=503, detail="Service Unavailable")

    # [CRITICAL] LINE verification MUST use raw request bytes
    body_bytes = await request.body()
    logger.info(f"LINE Webhook received {len(body_bytes)} bytes. Signature: {x_line_signature}")

    try:
        # Find LineBotAdapter
        adapter = next((a for a in interaction_svc.adapters if "LineBotAdapter" in a.__class__.__name__), None)
        
        if adapter:
            # We pass bytes now - the adapter must be updated to handle types correctly
            await adapter.handle_webhook(body_bytes, x_line_signature)
        else:
            logger.warning("No LineBotAdapter found in InteractionService.")
            raise HTTPException(status_code=500, detail="Adapter Missing")
            
    except ValueError as ve:
        logger.error(f"Invalid LINE signature: {ve}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Error handling LINE webhook: {e}", exc_info=True)
        return "OK"

    return "OK"

@app.post("/callback/{channel_name}")
async def generic_channel_callback(channel_name: str, request: Request):
    """
    Unified Callback Entry Point for specialized channels.
    Routes to: Slack, Telegram, Messenger
    """
    interaction_svc = services.get("interaction")
    if not interaction_svc:
         raise HTTPException(status_code=503, detail="Service Unavailable")

    # 1. Find Adapter by Name
    target_adapter = None
    target_name = channel_name.lower()
    
    for adapter in interaction_svc.adapters:
        cls_name = adapter.__class__.__name__.lower()
        if target_name in cls_name:
            target_adapter = adapter
            break
            
    if not target_adapter:
        logger.warning(f"Callback received for unknown/inactive channel: {channel_name}")
        raise HTTPException(status_code=404, detail="Channel not active")
        
    # 2. Extract Body and Headers
    try:
        content_type = request.headers.get("content-type", "")
        payload = None
        
        if "application/x-www-form-urlencoded" in content_type:
             # Parse form data (Slack)
             try:
                 form_data = await request.form()
                 # Slack sends 'payload' JSON string inside form
                 if "payload" in form_data:
                     import json
                     payload = json.loads(form_data["payload"])
                 else:
                     payload = dict(form_data)
             except Exception:
                 # Fallback if python-multipart is missing
                 from urllib.parse import parse_qs
                 body_bytes = await request.body()
                 body_str = body_bytes.decode("utf-8")
                 parsed = parse_qs(body_str)
                 # parse_qs returns lists, e.g. {'payload': ['...']}
                 if "payload" in parsed:
                     import json
                     payload = json.loads(parsed["payload"][0])
                 else:
                     payload = {k: v[0] for k, v in parsed.items()}
        elif "application/json" in content_type:
             payload = await request.json()
        else:
             # Fallback to generic JSON or raw body
             try:
                 payload = await request.json()
             except Exception:
                 body = await request.body()
                 payload = body.decode("utf-8")

        # Headers for verification
        headers = dict(request.headers)
        
        # 3. Delegate to Adapter
        result = await target_adapter.handle_webhook(payload, headers)
        
        return result or "OK"
        
    except Exception as e:
        logger.error(f"Error handling {channel_name} callback: {e}")
        raise HTTPException(status_code=500, detail="Processing Failed")
# --- Authentication Hub (New Phase 4) ---
from src.utils.google_auth import GoogleAuth
from fastapi.responses import RedirectResponse, HTMLResponse
import urllib.parse
import json

# Initialize Auth with backend configuration
# backend uses port 8000 for callback
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

auth_hub = GoogleAuth(
    secret_credentials_path=os.getenv('GOOGLE_CLIENT_SECRET_PATH', 'client_secret.json'),
    redirect_uri=f"{BACKEND_URL}/api/auth/callback",
    cookie_key=os.getenv('COOKIE_KEY', 'your_secret_cookie_key_should_be_long')
)

@app.get("/api/auth/login")
async def auth_login():
    """Start OAuth flow by redirecting to Google."""
    try:
        flow = auth_hub._get_flow()
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        return RedirectResponse(authorization_url)
    except Exception as e:
        logger.error(f"Auth login failed: {e}")
        return HTMLResponse(content="Auth Error: Initialization failed", status_code=500)

@app.get("/api/auth/callback")
async def auth_callback(code: str):
    """Handle Google callback, set HTTPOnly tokens, and redirect to Next.js."""
    try:
        flow = auth_hub._get_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Verify ID Token
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        from src.utils.jwt_utils import create_access_token, create_refresh_token
        
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, google_requests.Request(), flow.client_config['client_id']
        )
        
        user_id = id_info.get("sub")
        user_email = id_info.get("email")
        
        # Create Stateless JWT Tokens
        token_data = {"sub": user_id, "email": user_email}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        # Redirect back to Next.js
        response = RedirectResponse(url=f"{FRONTEND_URL}/auth/callback")
        
        # 1. Set Access Token (1 HR)
        response.set_cookie(
            key="access_token",
            value=access_token,
            max_age=3600,
            httponly=True,
            samesite="lax",
            secure=False # Set to True in production
        )
        
        # 2. Set Refresh Token (7 DAYS)
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            max_age=7*24*60*60,
            httponly=True,
            samesite="lax",
            secure=False
        )
        
        logger.info(f"User {user_email} authenticated. JWT tokens issued.")
        return response
        
    except Exception as e:
        logger.error(f"Auth callback failed: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/login?error=Authentication%20Failed")

@app.post("/api/auth/refresh")
async def auth_refresh(request: Request):
    """Exchange refresh token for a new access token."""
    from src.utils.jwt_utils import decode_token, create_access_token
    refresh_token = request.cookies.get("refresh_token")
    
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
        
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
        
    # Create new access token
    new_data = {"sub": payload.get("sub"), "email": payload.get("email")}
    new_access_token = create_access_token(new_data)
    
    response = JSONResponse(content={"status": "refreshed"})
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        max_age=3600,
        httponly=True,
        samesite="lax",
        secure=False
    )
    return response

async def get_current_user(access_token: Optional[str] = Cookie(None)):
    """依據 Cookie 中的 JWT token 驗證使用者身份"""
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = decode_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    return payload

@app.get("/api/auth/me")
async def auth_me(user: Dict[str, Any] = Depends(get_current_user)):
    """獲取當前登入的使用者資訊"""
    return {
        "status": "success",
        "data": {
            "user_id": user.get("sub"),
            "email": user.get("email"),
            "is_authenticated": True
        }
    }

@app.post("/api/auth/logout")
async def auth_logout():
    """Clear all auth cookies."""
    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response

# --- WebSocket Endpoint ---

@app.websocket("/api/dashboard/ws")
async def dashboard_websocket(
    websocket: WebSocket,
    access_token: Optional[str] = Cookie(None)
):
    """
    WebSocket endpoint for real-time dashboard updates.
    使用 HTTPOnly Cookie 中的 access_token 進行握手認證。
    """
    if not access_token:
        logger.warning("WebSocket attempt without access_token cookie.")
        await websocket.close(code=1008)  # Policy Violation
        return

    try:
        # 驗證 Token
        payload = decode_token(access_token)
        if not payload:
            logger.warning("Invalid WebSocket token.")
            await websocket.close(code=1008)
            return

        user_id = payload.get("sub")
        if not user_id:
            logger.warning("WebSocket token missing user_id.")
            await websocket.close(code=1008)
            return

        # 註冊連線
        await socket_manager.connect(websocket, user_id)
        
        try:
            # 保持連線開啟並處理來自客戶端的消息
            while True:
                data = await websocket.receive_text()
                
                # 處理心跳 (Ping-Pong)
                if data == "ping":
                    await websocket.send_text("pong")
                    continue
                
                # 處理 JSON 指令 (Phase 5)
                try:
                    command_data = json.loads(data)
                    await socket_manager.handle_command(user_id, command_data)
                except json.JSONDecodeError:
                    logger.warning(f"Received non-JSON data from user {user_id}: {data}")
                except Exception as cmd_e:
                    logger.error(f"Error handling WebSocket command for user {user_id}: {cmd_e}")

        except WebSocketDisconnect:
            socket_manager.disconnect(websocket, user_id)
            logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket handling error: {e}")
        try:
            await websocket.close(code=1011) # Internal Error
        except:
            pass
