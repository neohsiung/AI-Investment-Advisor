"""
MCP Service - FastAPI 微服務入口點
Model Context Protocol Service - FastAPI Microservice Entry Point
"""
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
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
from src.services.github_service import GitHubService

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    (Lifespan) Initialize all services and tools.
    """
    logger.info("Initializing MCP Services...")
    
    try:
        # 1. Instantiate Services
        services["market"] = MarketDataService()
        services["search"] = InternetSearchService()
        services["fred"] = FredService()
        services["sentinel"] = SentinelService(
            market_service=services["market"],
            search_service=services["search"]
        )
        services["github"] = GitHubService()
        
        from src.services.webhook_service import webhook_service_instance
        webhook_service_instance.set_sentinel_service(services["sentinel"])
        
        # Initialize Settings Service for Adapter Configuration
        from src.services.settings_service import SettingsService
        from src.infrastructure.channels.channel_factory import ChannelFactory
        from src.infrastructure.nlp.intent_classifier import IntentClassifier
        
        settings_svc_global = SettingsService(db_path=None)  # Use environment DB_URL or DB_TYPE
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
            stream_client = PolygonStreamClient()
            stream_client.add_callback(services["sentinel"].on_realtime_event)
            asyncio.create_task(stream_client.connect(tickers=["*"])) # Listen to all trades
            services["polygon_stream"] = stream_client
            logger.info("Polygon Real-time Stream Client started in background.")
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
            },
            
            # GitHub Operations
            {
                "name": "github_list_issues",
                "description": "列出 GitHub Repository 中的 Issues",
                "parameters": {"repo_full_name": "Repo完整名稱 (e.g., owner/repo)", "state": "狀態 (open/closed)"}
            },
            {
                "name": "github_get_issue_detail",
                "description": "取得 GitHub Issue 詳細內容與評論",
                "parameters": {"repo_full_name": "Repo完整名稱", "issue_number": "Issue編號"}
            },
            {
                "name": "github_create_issue_comment",
                "description": "在 GitHub Issue 下方新增評論",
                "parameters": {"repo_full_name": "Repo完整名稱", "issue_number": "Issue編號", "body": "評論內容"}
            },
            {
                "name": "github_search_repos",
                "description": "搜尋 GitHub 儲存庫",
                "parameters": {"query": "搜尋關鍵字"}
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
            
        # GitHub Dispatch
        elif tool_name == "github_list_issues":
            repo = args.get("repo_full_name")
            state = args.get("state", "open")
            if repo:
                result = services["github"].list_issues(repo, state)
                
        elif tool_name == "github_get_issue_detail":
            repo = args.get("repo_full_name")
            num = args.get("issue_number")
            if repo and num:
                result = services["github"].get_issue_detail(repo, int(num))
                
        elif tool_name == "github_create_issue_comment":
            repo = args.get("repo_full_name")
            num = args.get("issue_number")
            body = args.get("body")
            if repo and num and body:
                result = services["github"].create_issue_comment(repo, int(num), body)
                
        elif tool_name == "github_search_repos":
            query = args.get("query")
            if query:
                result = services["github"].search_repos(query)
            
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
# --- LINE Bot Webhook Support ---
# --- LINE Bot Webhook Support (via InteractionService) ---
@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """
    LINE Messaging API Webhook Callback
    Routed to InteractionService -> LineBotAdapter
    """
    interaction_svc = services.get("interaction")
    if not interaction_svc:
        # If service not ready, check if we can init it lazily or fail
        logger.warning("InteractionService not initialized yet.")
        raise HTTPException(status_code=503, detail="Service Unavailable")

    body = await request.body()
    body_str = body.decode('utf-8')
    logger.info(f"LINE Webhook body: {body_str}")

    try:
        # Find LineBotAdapter
        # We look for the adapter class name
        adapter = next((a for a in interaction_svc.adapters if "LineBotAdapter" in a.__class__.__name__), None)
        
        if adapter:
            await adapter.handle_webhook(body_str, x_line_signature)
        else:
            logger.warning("No LineBotAdapter found in InteractionService.")
            raise HTTPException(status_code=500, detail="Adapter Missing")
            
    except ValueError:
        logger.error("Invalid LINE signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Error handling LINE webhook: {e}")
        # Return OK to prevent LINE from retrying infinitely on logic errors
        # unless it's a critical infrastructure failure
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
