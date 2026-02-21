import pytest
from fastapi.testclient import TestClient
from services.mcp_server.src.app import app, services, registered_tools
from unittest.mock import MagicMock, patch

def test_mcp_health_and_root():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

def test_mcp_tools_list():
    with TestClient(app) as client:
        response = client.get("/tools/list")
        assert response.status_code == 200
        assert "tools" in response.json()

def test_mcp_tool_register():
    with TestClient(app) as client:
        payload = {
            "name": "test_tool",
            "description": "desc",
            "parameters": {"a": "b"}
        }
        response = client.post("/tools/register", json=payload)
        assert response.status_code == 200
        assert response.json()["tool"] == "test_tool"

def test_mcp_agent_message():
    with TestClient(app) as client:
        payload = {
            "sender": "a1",
            "receiver": "a2",
            "content": "hello"
        }
        response = client.post("/agents/message", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "delivered"

def test_mcp_call_tool_not_found():
    with TestClient(app) as client:
        response = client.post("/tools/call/nonexistent", json={"arguments": {}})
        assert response.status_code == 404

def test_mcp_call_tool_success():
    with TestClient(app) as client:
        # Mock a service
        mock_market = MagicMock()
        mock_market.get_current_prices.return_value = {"AAPL": 150.0}
        services["market"] = mock_market
        
        registered_tools["get_current_price"] = {"name": "get_current_price"}
        
        response = client.post("/tools/call/get_current_price", json={"arguments": {"ticker": "AAPL"}})
        assert response.status_code == 200
        assert response.json()["result"] == 150.0
