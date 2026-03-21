"""
Tests for MCP Server and Market Tools (src/tools/).
測試 MCP 伺服器與市場工具。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.tools.mcp_server import McpServer, McpTool
from src.tools.market_tools import create_market_server

class TestMcpTool:
    
    def test_tool_creation(self):
        """Test creating an MCP tool."""
        def sample_func(ticker: str):
            return {"price": 100}
        
        tool = McpTool(
            name="get_price",
            description="Get stock price",
            func=sample_func
        )
        
        assert tool.name == "get_price"
        assert tool.description == "Get stock price"
        assert tool.func == sample_func
        assert tool.schema is not None
    
    def test_tool_execution(self):
        """Test executing an MCP tool."""
        def add_numbers(a: int, b: int):
            return a + b
        
        tool = McpTool(
            name="add",
            description="Add two numbers",
            func=add_numbers
        )
        
        result = tool.execute(a=5, b=3)
        assert result == 8
    
    def test_tool_to_dict(self):
        """Test tool serialization."""
        tool = McpTool(
            name="test_tool",
            description="Test",
            func=lambda x: x
        )
        
        d = tool.to_dict()
        assert d["name"] == "test_tool"
        assert "input_schema" in d

class TestMcpServer:
    
    def test_server_creation(self):
        """Test creating an MCP server."""
        server = McpServer(name="TestServer")
        assert server.name == "TestServer"
        assert server.tools == {}
    
    def test_register_tool(self):
        """Test registering a tool with the server."""
        server = McpServer(name="TestServer")
        
        tool = McpTool(
            name="get_data",
            description="Get data",
            func=lambda: "data"
        )
        
        server.register_tool(tool)
        assert "get_data" in server.tools
    
    def test_list_tools(self):
        """Test listing registered tools."""
        server = McpServer(name="TestServer")
        
        tool1 = McpTool(name="tool1", description="Tool 1", func=lambda: 1)
        tool2 = McpTool(name="tool2", description="Tool 2", func=lambda: 2)
        
        server.register_tool(tool1)
        server.register_tool(tool2)
        
        tools_list = server.list_tools()
        assert len(tools_list) == 2
        names = [t["name"] for t in tools_list]
        assert "tool1" in names
        assert "tool2" in names
    
    def test_call_tool_success(self):
        """Test calling a registered tool."""
        server = McpServer(name="TestServer")
        
        tool = McpTool(
            name="multiply",
            description="Multiply numbers",
            func=lambda x, y: x * y
        )
        
        server.register_tool(tool)
        result = server.call_tool("multiply", {"x": 4, "y": 5})
        assert result == 20
    
    def test_call_tool_not_found(self):
        """Test calling a non-existent tool."""
        server = McpServer(name="TestServer")
        
        with pytest.raises(ValueError) as exc_info:
            server.call_tool("unknown_tool", {})
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_call_tool_with_error(self):
        """Test handling errors during tool execution."""
        server = McpServer(name="TestServer")
        
        def error_func():
            raise Exception("Tool Error")
        
        tool = McpTool(name="error_tool", description="Error", func=error_func)
        server.register_tool(tool)
        
        with pytest.raises(Exception) as exc_info:
            server.call_tool("error_tool", {})
        
        assert "Tool Error" in str(exc_info.value)

class TestMarketTools:
    
    def test_create_market_server(self):
        """Test creating market data server."""
        with patch('src.tools.market_tools.MarketDataService') as MockService:
            server = create_market_server()
            
            assert server is not None
            assert server.name == "MarketData"
            assert len(server.tools) > 0
    
    def test_market_tools_registered(self):
        """Test that market tools are registered."""
        with patch('src.tools.market_tools.MarketDataService') as MockService:
            server = create_market_server()
            
            # Verify tools are registered
            tool_names = list(server.tools.keys())
            assert "get_current_price" in tool_names
            assert "get_news" in tool_names
            assert "get_financials" in tool_names
