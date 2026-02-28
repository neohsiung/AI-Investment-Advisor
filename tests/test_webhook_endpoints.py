import pytest
from fastapi.testclient import TestClient
import json
from unittest.mock import AsyncMock, patch
from src.services.webhook_service import webhook_router, webhook_service_instance
from fastapi import FastAPI

app = FastAPI()
app.include_router(webhook_router)
client = TestClient(app)

@pytest.fixture
def mock_sentinel():
    with patch('src.services.webhook_service.webhook_service_instance.sentinel_service') as mock_svc:
        mock_svc.process_tick = AsyncMock()
        mock_svc.process_event = AsyncMock()
        yield mock_svc

def test_heartbeat_webhook(mock_sentinel):
    response = client.get("/webhook/heartbeat")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    mock_sentinel.process_tick.assert_called_once()
    
    response_post = client.post("/webhook/heartbeat")
    assert response_post.status_code == 200
    assert response_post.json()["status"] == "alive"
    assert mock_sentinel.process_tick.call_count == 2

def test_market_alert_webhook(mock_sentinel):
    payload = {"ticker": "AAPL", "message": "Spike"}
    with patch("src.services.webhook_service.webhook_service_instance.handle_generic_webhook", new_callable=AsyncMock) as mock_handler:
        mock_handler.return_value = {"status": "accepted"}
        response = client.post("/webhook/market-alert", json=payload)
        assert response.status_code == 200
        mock_handler.assert_called_once()
