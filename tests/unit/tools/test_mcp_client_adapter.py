"""
Unit Test: MCP Client Adapter — Core functionality & Observability (Phase 10)
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.mcp_client_adapter import MCPClientAdapter
from mcp.types import Tool, CallToolResult, TextContent

@pytest.fixture
def mock_session():
    session = AsyncMock()
    # Mock list_tools
    tool = Tool(name="evaluate_trade", description="Trade evaluation", inputSchema={})
    session.list_tools.return_value = MagicMock(tools=[tool])
    # Mock call_tool
    session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="Decision: BUY")]
    )
    return session

@pytest.fixture
def mock_guard():
    guard = AsyncMock()
    guard.verify_purpose_alignment.return_value = (True, "Valid")
    return guard

@pytest.mark.asyncio
async def test_mcp_client_observability(mock_session, mock_guard):
    """
    Test tracing, latency warnings, and tool calls.
    """
    with patch("src.tools.mcp_client_adapter.ClientSession", return_value=mock_session), \
         patch("src.tools.mcp_client_adapter.sse_client") as mock_sse, \
         patch("src.services.mcp_installation_guard.MCPBackgroundCheckService", return_value=mock_guard), \
         patch("src.tools.mcp_client_adapter.tracer") as mock_tracer:        
        # Setup mock SSE streams
        mock_sse.return_value = (AsyncMock(), AsyncMock())
        
        # Mock span
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
         
        client = MCPClientAdapter("http://mock-server/sse", user_id="test_user")
        
        # Call connect directly, bypassing actual file/network setup for exit stack
        client._session = mock_session
        await client.refresh_tools()
        
        assert len(client.list_tools()) == 1
        
        # Call tool and trigger trace
        res = await client.call_tool("evaluate_trade", {"symbol": "AAPL"})
        
        assert "Decision: BUY" in res
        
        # Verify Trace Attributes were set
        assert mock_tracer.start_as_current_span.call_count >= 1
        mock_span.set_attribute.assert_any_call("mcp.tool_name", "evaluate_trade")
        mock_span.set_attribute.assert_any_call("mcp.user_id", "test_user")

@pytest.mark.asyncio
async def test_mcp_client_latency_warning(mock_session, mock_guard):
    """
    Test that a slow tool call triggers a logger warning.
    """
    client = MCPClientAdapter("http://mock-server/sse", user_id="test_user_slow")
    client._session = mock_session
    client._tools = {"slow_tool": Tool(name="slow_tool", description="", inputSchema={})}
    client._guard = mock_guard
    
    # Simulate a slow network call
    import asyncio
    async def slow_call(*args, **kwargs):
        await asyncio.sleep(2.1)
        return CallToolResult(content=[TextContent(type="text", text="Slow Result")])
    
    mock_session.call_tool.side_effect = slow_call
    
    with patch("src.tools.mcp_client_adapter.logger") as mock_logger:
        res = await client.call_tool("slow_tool", {})
        assert "Slow Result" in res
        
        # Since it took > 2.0s, logger.warning should be called
        warning_calls = [c for c in mock_logger.warning.call_args_list if "Performance Warning" in c[0][0]]
        assert len(warning_calls) == 1
