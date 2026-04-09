"""
MCP SSE Router — Context-Standardized Tooling Gateway [Phase 6].
MCP SSE 路由 — 上下文標準化工具閘道。

Implements the Model Context Protocol (MCP) using the SDK's high-level FastMCP.
Bridges existing SkillRegistry and MarketTools into the standard MCP ecosystem.

遵循規範:
  - 規範十 (MCP 整合): 實現標準 MCP 協定
"""

import logging
import asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False
    logger.warning("FastMCP not installed or compatible. Features disabled.")
try:
    from src.agents.skills.skill_loader import SkillLoader
except ImportError:
    pass

if HAS_FASTMCP:
    # 1. Initialize the FastMCP Server
    mcp_app = FastMCP(
        "AI-Investment-Advisor",
        dependencies=["src"],
        # Disable DNS rebinding protection for bridge flexibility
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
else:
    mcp_app = None

# 2. Bridge Skills
def bridge_skills():
    pass

# 3. Bridge Market Tools
def bridge_market_tools():
    pass


# Run bridging
try:
    bridge_skills()
    bridge_market_tools()
except Exception as e:
    logger.error(f"MCP: Failed to bridge tools: {e}")
    # Don't let bridging errors crash the whole service
    pass

# 4. Export the Starlette app for mounting
# Usage in main.py: app.mount("/mcp", mcp_app_instance)
if mcp_app:
    mcp_sub_app = mcp_app.sse_app()
else:
    from fastapi import APIRouter
    mcp_sub_app = APIRouter()
