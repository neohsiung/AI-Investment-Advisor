import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from services.mcp_server.src.app import app, services
from src.domain.interfaces import IChannelAdapter

# Define Mock Adapters with proper class names
class MockSlackAdapter(IChannelAdapter):
    async def send_alert(self, user_id, title, content, actions=None, **kwargs): pass
    def register_callback(self, callback_func): pass
    def register_text_callback(self, callback_func): pass
    async def handle_webhook(self, payload, headers=None):
        return {"status": "mock_slack_handled", "payload": payload}
    async def authenticate(self, request, **kwargs): return True
    async def receive_command(self, payload, **kwargs): return payload
    async def send_message(self, user_id, message, **kwargs): return True

class MockTelegramAdapter(IChannelAdapter):
    async def send_alert(self, user_id, title, content, actions=None, **kwargs): pass
    def register_callback(self, callback_func): pass
    def register_text_callback(self, callback_func): pass
    async def handle_webhook(self, payload, headers=None):
        return {"status": "mock_telegram_handled", "payload": payload}
    async def authenticate(self, request, **kwargs): return True
    async def receive_command(self, payload, **kwargs): return payload
    async def send_message(self, user_id, message, **kwargs): return True

@pytest.fixture
def mock_interaction_service():
    service = MagicMock()
    # Inject our mock adapters
    service.adapters = [MockSlackAdapter(), MockTelegramAdapter()]
    return service

def test_callback_routing_slack(mock_interaction_service):
    """Test routing to Slack Adapter"""
    with patch.dict(services, {"interaction": mock_interaction_service}):
        client = TestClient(app)
        
        # Simulate Slack Form Data
        import json
        response = client.post(
            "/callback/slack",
            data={"payload": json.dumps({"type": "block_actions", "action": "test"})},
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "mock_slack_handled"
        assert response.json()["payload"]["type"] == "block_actions"

def test_callback_routing_telegram(mock_interaction_service):
    """Test routing to Telegram Adapter"""
    with patch.dict(services, {"interaction": mock_interaction_service}):
        client = TestClient(app)
        
        # Simulate Telegram JSON
        response = client.post(
            "/callback/telegram",
            json={"callback_query": {"id": "123", "data": "action=buy"}},
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "mock_telegram_handled"
        assert response.json()["payload"]["callback_query"]["id"] == "123"

def test_callback_routing_unknown(mock_interaction_service):
    """Test routing to unknown channel"""
    with patch.dict(services, {"interaction": mock_interaction_service}):
        client = TestClient(app)
        
        response = client.post(
            "/callback/discord", # "DiscordAdapter" not in mock list
            json={}
        )
        
        assert response.status_code == 404
