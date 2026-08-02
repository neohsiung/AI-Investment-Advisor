"""
Unit Test: MCP SSE Server — Handshake and Tool Discovery [Phase 6].
單元測試：MCP SSE 伺服器 — 握手與工具發現。
"""

import pytest
import asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
import json

# httpx_sse only reaches the environment transitively (via mcp), so a hard
# top-level import made this module a collection landmine: CI resolves deps
# from pyproject.toml rather than uv.lock, and a newer mcp stopped pulling it
# in — aborting the entire pytest run with exit 2. The one test here is
# skipped anyway, so importorskip costs nothing.
# httpx_sse 是靠 mcp 傳遞進來的，硬 import 會讓整個 collection 掛掉；
# 這裡唯一的測試本來就 skip，改用 importorskip 沒有損失。
aconnect_sse = pytest.importorskip("httpx_sse").aconnect_sse

from src.tools.mcp_sse_router import mcp_sub_app, HAS_FASTMCP

@pytest.fixture
def app():
    _app = FastAPI()
    _app.mount("/mcp", mcp_sub_app)
    return _app

@pytest.mark.skip(reason="requires live MCP SSE server; hangs in CI without running event loop")
@pytest.mark.skipif(not HAS_FASTMCP, reason="FastMCP not installed or compatible")
@pytest.mark.asyncio
async def test_mcp_sse_handshake(app):
    """
    Test the basic SSE handshake and tool listing.
    測試基本的 SSE 握手與工具列表讀取。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        # We need a long-running SSE connection while we POST messages
        # SseServerTransport is designed for this.
        
        async with aconnect_sse(client, "GET", "/mcp/sse") as event_source:
            # 1. Read first event (endpoint)
            # Use an iterator directly to avoid blocking forever
            it = event_source.aiter_sse()
            event = await anext(it)
            
            assert event.event == "endpoint"
            endpoint_url = event.data
            assert "/mcp/messages" in endpoint_url
            
            # Extract session_id if needed, but endpoint_url has it
            
            # 2. Simulate JSON-RPC Initialize
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            }
            
            # The endpoint_url is likely relative or absolute within the app context
            # httpx_sse might have different ideas about it.
            # We'll just use the resolved path.
            path = endpoint_url.split("?")[0]
            query = endpoint_url.split("?")[1]
            
            resp = await client.post(f"{path}?{query}", json=init_msg)
            assert resp.status_code == 202

            # 3. Read initialize response from SSE
            resp_event = await anext(it)
            assert resp_event.event == "message"
            data = json.loads(resp_event.data)
            assert data["id"] == 1
            assert "capabilities" in data["result"]
            
            print("✓ MCP Handshake Success")
