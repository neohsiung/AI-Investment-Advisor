"""
MCP Service - FastAPI 微服務入口點
Model Context Protocol Service - FastAPI Microservice Entry Point
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCPService")

from contextlib import asynccontextmanager

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
        
        # 2. Register Tools
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

    services.clear()

app = FastAPI(
    title="MCP Server",
    description="Model Context Protocol 工具伺服器 | Tool Server for Agent Mesh",
    version="1.1.0",
    lifespan=lifespan
)

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

# --- LINE Bot Webhook Support ---
import os
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from fastapi import Request, Header

# Initialize LINE Bot
line_channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
line_channel_secret = os.getenv("LINE_CHANNEL_SECRET")

if line_channel_access_token and line_channel_secret:
    line_bot_api = LineBotApi(line_channel_access_token)
    handler = WebhookHandler(line_channel_secret)
    logger.info("LINE Bot initialized.")
else:
    line_bot_api = None
    handler = None
    logger.warning("LINE Bot credentials not found. Webhook disabled.")

@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """
    LINE Messaging API Webhook Callback
    """
    if handler is None:
        raise HTTPException(status_code=503, detail="LINE Bot not configured")
        
    body = await request.body()
    body_str = body.decode('utf-8')
    logger.info(f"LINE Webhook body: {body_str}")

    try:
        handler.handle(body_str, x_line_signature)
    except InvalidSignatureError:
        logger.error("Invalid LINE signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"

# Basic Message Handler (Echo for verification)
if handler:
    @handler.add(MessageEvent, message=TextMessage)
    def handle_message(event):
        try:
            line_user_id = event.source.user_id
            logger.info(f"[LINE] Received message from {line_user_id}: {event.message.text}")
            
            # Simple Echo for Verification
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"收到: {event.message.text}\nUser ID: {line_user_id}")
            )
        except Exception as e:
            logger.error(f"Error handling LINE message: {e}")
