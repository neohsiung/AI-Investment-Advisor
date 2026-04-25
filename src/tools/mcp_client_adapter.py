"""
MCP Client Adapter — Standardized Protocol Integration [Phase 6].
MCP 客戶端適配器 — 標準協定整合。

Provides a client-side implementation of the Model Context Protocol (MCP) over SSE.
Allows the Agent to discover and call tools served by MCP-compliant servers.

遵循規範:
  - 規範十 (MCP 整合): 實現標準 MCP 客戶端
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
import time
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.types import Tool, CallToolResult
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class MCPClientAdapter:
    """
    Adapter for connecting to and interacting with MCP servers.
    v8.1: Added security background check and B2C user isolation.
    """
    
    def __init__(self, user_id: str, sse_url: str = None, command: str = None, args: List[str] = None, env: Dict[str, str] = None):
        self.user_id = user_id
        self.sse_url = sse_url
        self.command = command
        self.args = args or []
        self.env = env
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[asyncio.ExitStack] = None
        self._tools: Dict[str, Tool] = {}
        
        # Security Guard
        from src.services.mcp_installation_guard import MCPBackgroundCheckService
        self._guard = MCPBackgroundCheckService(user_id=user_id)

    async def connect(self):
        """Connect to the MCP server (SSE or Stdio) and discover tools."""
        with tracer.start_as_current_span(f"MCP.Connect.{self.user_id}") as span:
            span.set_attribute("mcp.user_id", self.user_id)
            if self.sse_url:
                span.set_attribute("mcp.sse_url", self.sse_url)
            else:
                span.set_attribute("mcp.command", self.command)

            start_time = time.time()
            try:
                from contextlib import AsyncExitStack
                self._exit_stack = AsyncExitStack()
                
                if self.sse_url:
                    # 1a. Establish SSE Connection
                    read_stream, write_stream = await self._exit_stack.enter_async_context(
                        sse_client(url=self.sse_url)
                    )
                elif self.command:
                    # 1b. Establish Stdio Connection
                    params = StdioServerParameters(
                        command=self.command,
                        args=self.args,
                        env=self.env
                    )
                    read_stream, write_stream = await self._exit_stack.enter_async_context(
                        stdio_client(params)
                    )
                else:
                    raise ValueError("MCP Client: Neither sse_url nor command provided")
                
                # 2. Initialize Session
                self._session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                
                await self._session.initialize()
                server_info = f"at {self.sse_url}" if self.sse_url else f"via {self.command}"
                logger.info(f"MCP Client ({self.user_id}): Connected to server {server_info}")
                
                # 3. Discover Tools
                await self.refresh_tools()
                span.set_attribute("mcp.tool_count", len(self._tools))
                
            except Exception as e:
                logger.error(f"MCP Client ({self.user_id}): Failed to connect to {self.sse_url}: {e}")
                span.record_exception(e)
                from opentelemetry.trace.status import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR, str(e)))
                await self.disconnect()
                raise
            finally:
                latency = time.time() - start_time
                span.set_attribute("mcp.latency_s", latency)

    async def refresh_tools(self):
        """
        Fetch the list of tools from the server and perform security background checks.
        """
        if not self._session:
            raise RuntimeError("MCP Client: Not connected")
            
        result = await self._session.list_tools()
        raw_tools = {tool.name: tool for tool in result.tools}
        
        # [Task 8.1] Background Check: Purpose Alignment
        verified_tools = {}
        for name, tool in raw_tools.items():
            # For external tools, we only verify purpose alignment (no AST scan possible for remote execution)
            is_valid, reason = await self._guard.verify_purpose_alignment(
                skill_name=name,
                description=tool.description,
                intent="Investment analysis and financial data retrieval" # Default system intent
            )
            
            if is_valid:
                verified_tools[name] = tool
            else:
                logger.warning(f"MCP Client ({self.user_id}): BLOCKED tool '{name}' from {self.sse_url} - {reason}")
        
        self._tools = verified_tools
        logger.info(f"MCP Client ({self.user_id}): Discovered {len(self._tools)} verified tools (Blocked {len(raw_tools) - len(verified_tools)})")

    def list_tools(self) -> List[Tool]:
        """List discovered tools."""
        return list(self._tools.values())

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call an MCP tool and return the text result."""
        if not self._session:
            raise RuntimeError("MCP Client: Not connected")
            
        if tool_name not in self._tools:
            raise ValueError(f"MCP Client: Tool '{tool_name}' not found or blocked by security policy")
            
        with tracer.start_as_current_span(f"MCP.ToolCall.{tool_name}") as span:
            span.set_attribute("mcp.tool_name", tool_name)
            span.set_attribute("mcp.user_id", self.user_id)
            
            logger.info(f"MCP Client ({self.user_id}): Calling tool '{tool_name}' with {arguments}")
            start_time = time.time()
            
            try:
                result: CallToolResult = await self._session.call_tool(tool_name, arguments)
            except Exception as e:
                span.record_exception(e)
                from opentelemetry.trace.status import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
            finally:
                latency = time.time() - start_time
                span.set_attribute("mcp.latency_s", latency)
                if latency > 2.0:
                    logger.warning(f"MCP Performance Warning: Tool '{tool_name}' for user {self.user_id} took {latency:.3f}s (Threshold: 2.0s)")
                else:
                    logger.debug(f"MCP Client Tool '{tool_name}' latency: {latency:.3f}s")
            
            # Standard MCP result can have multiple content items
            text_results = [
                content.text for content in result.content 
                if hasattr(content, "text") and content.type == "text"
            ]
            
            return "\n".join(text_results)

    async def disconnect(self):
        """Disconnect and cleanup."""
        if self._exit_stack:
            await self._exit_stack.aclose()
        self._session = None
        self._exit_stack = None
        logger.info(f"MCP Client ({self.user_id}): Disconnected")

# [Task 8.2] Global instances manager with B2C Isolation
# Cache key includes user_id to prevent leak between users
_clients: Dict[str, MCPClientAdapter] = {}

async def get_mcp_client(user_id: str, sse_url: str = None, command: str = None, args: List[str] = None) -> MCPClientAdapter:
    """
    Get or create an MCP client for a specific config and user context.
    Ensures B2C isolation.
    """
    config_id = sse_url or f"{command} {' '.join(args or [])}"
    cache_key = f"{user_id}::{config_id}"
    if cache_key not in _clients:
        client = MCPClientAdapter(user_id=user_id, sse_url=sse_url, command=command, args=args)
        await client.connect()
        _clients[cache_key] = client
    return _clients[cache_key]
