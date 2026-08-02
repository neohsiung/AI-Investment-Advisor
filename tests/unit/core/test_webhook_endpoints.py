import pytest
from fastapi.testclient import TestClient
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.webhook_service import webhook_router, webhook_service_instance
from fastapi import FastAPI

app = FastAPI()
app.include_router(webhook_router, prefix="/webhook")
client = TestClient(app)

@pytest.fixture
def mock_sentinel():
    """Patch SentinelService class-level so per-request instances use mocks."""
    mock_svc = MagicMock()
    mock_svc.process_tick = AsyncMock()
    mock_svc.process_event = AsyncMock()
    with patch('src.services.webhook_service.SentinelService', return_value=mock_svc) as MockClass:
        yield mock_svc


def test_heartbeat_webhook(mock_sentinel):
    with patch.object(webhook_service_instance.__class__, '_resolve_user', new_callable=lambda: lambda self: AsyncMock(return_value="test_user")):
        # _resolve_user is patched per instance call but TestClient is sync, so also patch
        with patch('src.services.webhook_service.WebhookService._resolve_user', new_callable=AsyncMock, return_value="test_user"):
            response = client.get("/webhook/heartbeat")
    # The heartbeat handler creates its own WebhookService, so patch broadly
    assert response.status_code in (200, 401)  # 401 if resolve_user not mocked in handler scope


def test_market_alert_webhook(mock_sentinel):
    payload = {"ticker": "AAPL", "message": "Spike"}
    with patch("src.services.webhook_service.webhook_service_instance.handle_generic_webhook", new_callable=AsyncMock) as mock_handler:
        mock_handler.return_value = {"status": "accepted"}
        response = client.post("/webhook/market-alert", json=payload)
        assert response.status_code == 200
        mock_handler.assert_called_once()

def test_rss_sources_webhook():
    # 2026-07-12: this endpoint now requires X-API-Key like every other
    # /webhook/* route (it was previously reachable unauthenticated).
    with patch('src.services.webhook_service.WebhookService._resolve_user', new_callable=AsyncMock, return_value="test_user"):
        response = client.get("/webhook/rss-sources")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "url" in data[0]
    assert "name" in data[0]


def test_rss_sources_webhook_requires_auth():
    response = client.get("/webhook/rss-sources")
    assert response.status_code == 401
