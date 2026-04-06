"""
Tests for MCP Microservice.
測試 MCP 微服務。
"""
import pytest
pytestmark = pytest.mark.integration
from typing import Any, Dict, List, Optional
from fastapi.testclient import TestClient
from services.mcp_server.src.app import app, services, registered_tools
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_mcp_services():
    """Mock the global services dictionary to avoid real API calls."""
    # Manually populate tools for testing if lifespan fails
    registered_tools["get_current_price"] = {"name": "get_current_price", "description": "test"}
    registered_tools["web_search"] = {"name": "web_search", "description": "test"}
    # We also need to patch the classes themselves if lifespan instantiates them
    with patch("services.mcp_server.src.app.MarketDataService") as MockMarket, \
         patch("services.mcp_server.src.app.InternetSearchService") as MockSearch, \
         patch("services.mcp_server.src.app.FredService") as MockFred, \
         patch("services.mcp_server.src.app.SentinelService"), \
         patch("src.services.settings_service.SettingsService"), \
         patch("src.infrastructure.channels.channel_factory.ChannelFactory"), \
         patch("src.infrastructure.nlp.intent_classifier.IntentClassifier"), \
         patch("services.mcp_server.src.app.InteractionService"):
         
        # Ensure instances are mocks
        MockMarket.return_value = MagicMock()
        MockSearch.return_value = MagicMock()
        MockFred.return_value = MagicMock()
        
        # Services dict mocking for tests that check 'services' directly
        services["market"] = MagicMock()
        services["market"].get_current_prices.return_value = {"AAPL": 150.0}
        services["market"].get_valuation_metrics.return_value = {"pe": 20}
        services["market"].get_financials.return_value = {"description": "Apple Inc."}
        services["market"].get_macro_data.return_value = {"gdp": 2.0}
        
        services["search"] = MagicMock()
        services["search"].search_financial_context.return_value = [{"title": "News"}]
        
        services["fred"] = MagicMock()

        # Allow the test to proceed
        yield

@pytest.fixture
def client(mock_mcp_services):
    """Create a TestClient instance."""
    # Using context manager to trigger lifespan events properly
    with TestClient(app) as c:
        yield c

def test_root(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "mcp_server"

def test_health(client):
    """Test health check."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_list_tools(client):
    """Test listing tools."""
    response = client.get("/tools/list")
    assert response.status_code == 200
    assert "tools" in response.json()
    assert response.json()["count"] >= 2  # Built-in tools

def test_register_tool(client):
    """Test tool registration."""
    tool_data = {
        "name": "test_tool",
        "description": "A test tool",
        "parameters": {"param1": "string"}
    }
    response = client.post("/tools/register", json=tool_data)
    assert response.status_code == 200
    assert response.json()["tool"] == "test_tool"
    
    # Verify it's in the list
    list_resp = client.get("/tools/list")
    tool_names = [t["name"] for t in list_resp.json()["tools"]]
    assert "test_tool" in tool_names

def test_call_tool(client):
    """Test calling a tool."""
    call_data = {"arguments": {"ticker": "AAPL"}}
    response = client.post("/tools/call/get_current_price", json=call_data)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["tool"] == "get_current_price"

def test_call_tool_not_found(client):
    """Test calling a non-existent tool."""
    call_data = {"arguments": {}}
    response = client.post("/tools/call/non_existent_tool", json=call_data)
    assert response.status_code == 404

def test_agent_message(client):
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
