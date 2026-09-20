"""
Tests for MCP Microservice.
測試 MCP 微服務。
"""
import pytest
pytestmark = pytest.mark.integration
from typing import Any, Dict, List, Optional
from fastapi.testclient import TestClient
from services.mcp_server.src.app import app, services, registered_tools
from unittest.mock import MagicMock, patch, AsyncMock

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
         patch("services.mcp_server.src.app.InteractionService"), \
         patch("src.data.database.AsyncBaseRepository") as MockAsyncRepo:
         
        # Ensure instances are mocks
        MockMarket.return_value = MagicMock()
        MockSearch.return_value = MagicMock()
        MockFred.return_value = MagicMock()
        
        # Mock DB health check: prevent real DB connection in /health endpoint
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=None)
        MockAsyncRepo.return_value.get_session = AsyncMock(return_value=mock_session)
        
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

def test_tool_registration_endpoint_is_gone(client):
    """
    `POST /tools/register` accepted any name into the dict that gates
    `/tools/call/{name}`, but dispatch is a fixed if/elif chain — so a registered
    tool passed the gate, matched nothing, and came back HTTP 200
    {"status": "success", "result": "Tool implementation not found in dispatch
    logic."}. Registering a tool made it *look* callable and never made it
    callable. Tools are declared in config/tools.yaml now.
    註冊端點已刪除：註冊後會通過閘門但匹配不到分派，回傳 200 success 夾帶錯誤字串。
    """
    response = client.post("/tools/register", json={
        "name": "test_tool", "description": "A test tool", "parameters": {}
    })
    assert response.status_code in (404, 405)


def test_a_registered_tool_without_a_dispatch_branch_fails_loudly(client):
    """
    The pattern the deleted endpoint created, reproduced directly: a name present
    in `registered_tools` with no implementation must not return success.
    直接重現該端點造成的情境：registered_tools 內有名稱但無實作，不得回報成功。
    """
    from services.mcp_server.src.app import registered_tools

    registered_tools["ghost_tool"] = {"name": "ghost_tool", "description": "", "parameters": {}}
    try:
        response = client.post("/tools/call/ghost_tool", json={"arguments": {}})
        assert response.status_code == 501, response.text
        assert "not implemented" in response.json()["detail"]
    finally:
        registered_tools.pop("ghost_tool", None)

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
