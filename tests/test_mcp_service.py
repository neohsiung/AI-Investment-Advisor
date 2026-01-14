"""
Tests for MCP Microservice.
測試 MCP 微服務。
"""
import pytest
from fastapi.testclient import TestClient
from src.mcp_service import app, services
from unittest.mock import MagicMock

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_mcp_services():
    """Mock the global services dictionary to avoid real API calls."""
    services["market"] = MagicMock()
    # Mock return values for standard calls
    services["market"].get_current_prices.return_value = {"AAPL": 150.0}
    services["market"].get_valuation_metrics.return_value = {"pe": 20}
    services["market"].get_financials.return_value = {"description": "Apple Inc."}
    services["market"].get_macro_data.return_value = {"gdp": 2.0}
    
    services["search"] = MagicMock()
    services["search"].search_financial_context.return_value = [{"title": "News"}]
    
    services["fred"] = MagicMock()

def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "mcp_server"

def test_health():
    """Test health check."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_list_tools():
    """Test listing tools."""
    with client as c:
        response = c.get("/tools/list")
        assert response.status_code == 200
        assert "tools" in response.json()
        assert response.json()["count"] >= 4  # Built-in tools

def test_register_tool():
    """Test tool registration."""
    tool_data = {
        "name": "test_tool",
        "description": "A test tool",
        "parameters": {"param1": "string"}
    }
    with client as c:
        response = c.post("/tools/register", json=tool_data)
        assert response.status_code == 200
        assert response.json()["tool"] == "test_tool"
        
        # Verify it's in the list
        list_resp = c.get("/tools/list")
        tool_names = [t["name"] for t in list_resp.json()["tools"]]
        assert "test_tool" in tool_names

def test_call_tool():
    """Test calling a tool."""
    call_data = {"arguments": {"ticker": "AAPL"}}
    with client as c:
        response = c.post("/tools/call/get_current_price", json=call_data)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["tool"] == "get_current_price"

def test_call_tool_not_found():
    """Test calling a non-existent tool."""
    call_data = {"arguments": {}}
    response = client.post("/tools/call/non_existent_tool", json=call_data)
    assert response.status_code == 404

def test_agent_message():
    """Test agent-to-agent messaging."""
    msg_data = {
        "sender": "AgentA",
        "receiver": "AgentB",
        "content": "Hello AgentB",
        "context": {"priority": "high"}
    }
    response = client.post("/agents/message", json=msg_data)
    assert response.status_code == 200
    assert response.json()["status"] == "delivered"
    assert response.json()["sender"] == "AgentA"
