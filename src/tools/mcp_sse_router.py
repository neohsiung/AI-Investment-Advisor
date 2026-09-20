"""
MCP SSE Router — Context-Standardized Tooling Gateway [Phase 6].
MCP SSE 路由 — 上下文標準化工具閘道。

Implements the Model Context Protocol (MCP) using the SDK's high-level FastMCP.

**This endpoint currently exposes zero tools.** The two bridge functions below
have been `pass` since they were written, so the mount at `/mcp` serves the
protocol handshake and an empty tool list. The docstring here used to claim it
"bridges existing SkillRegistry and MarketTools into the standard MCP ecosystem",
which was never true — that claim is the reason nobody noticed.

Bridging is deliberately still not implemented: the tools an agent holds include
`run_script`, which spawns subprocesses, and exporting the agent tool set over a
network transport is an exposure decision rather than a refactor. Tools are
declared in `config/tools.yaml` and registered into each agent's `McpServer`
(`src/tools/tool_manifest.py`); wiring that set to this transport needs an
explicit choice about which categories may leave the process.

**本端點目前不提供任何工具。** 下方兩個 bridge 函式自始即為 `pass`，
`/mcp` 只回應協定握手與空工具清單。原本的 docstring 聲稱已橋接 SkillRegistry 與
MarketTools——從未成立，也正因如此沒人發現。仍刻意不實作：agent 的工具集包含會啟動
子行程的 run_script，將其導出到網路傳輸是暴露面決策而非重構。

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
    """Not implemented — see the module docstring. Kept as the named seam."""
    return 0


# 3. Bridge Market Tools
def bridge_market_tools():
    """Not implemented — see the module docstring. Kept as the named seam."""
    return 0


# Run bridging
try:
    _bridged = bridge_skills() + bridge_market_tools()
    if HAS_FASTMCP and not _bridged:
        # Say it out loud at startup. A mounted endpoint that serves an empty tool
        # list looks identical to a working one from the outside.
        # 啟動時明確說出來：對外看不出「掛載成功但工具清單為空」與「正常運作」的差別。
        logger.warning(
            "MCP SSE mounted at /mcp with 0 tools — bridging is not implemented "
            "(src/tools/mcp_sse_router.py). Agent tools come from config/tools.yaml."
        )
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
