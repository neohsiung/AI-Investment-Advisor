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

app = FastAPI(
    title="MCP Server",
    description="Model Context Protocol 工具伺服器 | Tool Server for Agent Mesh",
    version="1.0.0"
)

# 工具註冊表
registered_tools: Dict[str, Dict] = {}


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


@app.get("/")
async def root():
    """健康檢查端點"""
    return {"status": "ok", "service": "mcp_server", "version": "1.0.0"}


@app.get("/health")
async def health():
    """健康檢查"""
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


@app.post("/tools/call/{tool_name}")
async def call_tool(tool_name: str, request: ToolCallRequest):
    """
    調用已註冊的工具
    Call a registered tool
    """
    if tool_name not in registered_tools:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    
    # 此處為模擬實作，實際工具邏輯需透過回呼或內部服務調用
    # This is a placeholder. Actual tool logic requires callback or internal service calls.
    logger.info(f"Tool called: {tool_name} with args: {request.arguments}")
    
    return {
        "status": "called",
        "tool": tool_name,
        "arguments": request.arguments,
        "result": f"Tool {tool_name} executed (placeholder)"
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


# 預註冊內建工具 (Pre-register built-in tools)
@app.on_event("startup")
async def startup_event():
    """服務啟動時註冊內建工具"""
    builtin_tools = [
        {"name": "get_current_price", "description": "取得即時股價", "parameters": {"ticker": "股票代碼"}},
        {"name": "get_news", "description": "取得相關新聞", "parameters": {"ticker": "股票代碼"}},
        {"name": "get_financials", "description": "取得財務數據", "parameters": {"ticker": "股票代碼"}},
        {"name": "search", "description": "網路搜尋", "parameters": {"query": "搜尋關鍵字"}},
    ]
    for tool in builtin_tools:
        registered_tools[tool["name"]] = tool
    logger.info(f"Pre-registered {len(builtin_tools)} built-in tools")
