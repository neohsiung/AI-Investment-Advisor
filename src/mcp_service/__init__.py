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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    服務生命週期管理
    Service Lifespan Management
    """
    # Startup logic
    builtin_tools = [
        {"name": "get_current_price", "description": "取得即時股價", "parameters": {"ticker": "股票代碼"}},
        {"name": "get_news", "description": "取得相關新聞", "parameters": {"ticker": "股票代碼"}},
        {"name": "get_financials", "description": "取得財務數據", "parameters": {"ticker": "股票代碼"}},
        {"name": "search", "description": "網路搜尋", "parameters": {"query": "搜尋關鍵字"}},
    ]
    for tool in builtin_tools:
        registered_tools[tool["name"]] = tool
    logger.info(f"Pre-registered {len(builtin_tools)} built-in tools")
    
    yield
    # Shutdown logic (if any) can go here

app = FastAPI(
    title="MCP Server",
    description="Model Context Protocol 工具伺服器 | Tool Server for Agent Mesh",
    version="1.0.0",
    lifespan=lifespan
)
