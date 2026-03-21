"""
MCP Service - FastAPI 微服務入口點
Model Context Protocol Service - FastAPI Microservice Entry Point
"""
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from fastapi import FastAPI, HTTPException, Request, Header
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

# Services Global Instance
services: Dict[str, Any] = {}

from src.services.market_data_service import MarketDataService
from src.services.search_service import InternetSearchService
from src.services.fred_service import FredService
from src.services.sentinel_service import SentinelService
from src.services.interaction_service import InteractionService

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    (Lifespan) Initialize all services and tools.
    """
    logger.info("Initializing MCP Services...")
    
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
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")

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
    """Handle Google callback, set cookie, and redirect to Streamlit."""
    try:
        flow = auth_hub._get_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Verify ID Token
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, google_requests.Request(), flow.client_config['client_id']
        )
        
        user_info = {
            "email": id_info.get("email"),
            "name": id_info.get("name"),
            "picture": id_info.get("picture"),
            "sub": id_info.get("sub")
        }
        
        # Create Redirect Response back to Streamlit
        response = RedirectResponse(url=FRONTEND_URL)
        
        # Set Authentication Cookie (7 days)
        # We URL-encode the JSON to match standard practices
        cookie_val = urllib.parse.quote(json.dumps(user_info))
        response.set_cookie(
            key=auth_hub.cookie_name,
            value=cookie_val,
            max_age=7*24*60*60,
            path="/",
            domain=None, # Same origin/localhost
            httponly=False, # Must be readable by Streamlit/CookieManager if needed
            samesite="lax"
        )
        
        logger.info(f"User {user_info['email']} logged in via FastAPI Hub")
        return response
        
    except Exception as e:
        logger.error(f"Auth callback failed: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}?error=Authentication%20Failed")
