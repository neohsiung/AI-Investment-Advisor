"""
Unit tests for Ticker Universe API endpoints (src/api/v1/endpoints/ticker_universe.py).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.ticker_universe import router, get_service


@pytest.fixture
def app():
    fastapi_app = FastAPI()
    fastapi_app.include_router(router, prefix="/api/v1/ticker-universe")
    return fastapi_app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    return svc


@pytest.fixture
def client(app, mock_service):
    app.dependency_overrides[get_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_quality_check_endpoint(client, mock_service):
    mock_service.evaluate_ticker_quality = AsyncMock(return_value={
        "ticker": "AAPL",
        "passed": True,
        "overall_score": 8.5,
    })

    resp = client.get("/api/v1/ticker-universe/quality-check/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["passed"] is True
    assert data["data"]["overall_score"] == 8.5


def test_lifecycle_run_endpoint(client, mock_service):
    mock_service.run_lifecycle_evolution = AsyncMock(return_value={
        "success": True,
        "message": "Lifecycle run completed",
        "evicted": [],
        "admitted": [{"ticker": "MSFT", "score": 8.8}],
        "active_count": 15,
    })

    resp = client.post("/api/v1/ticker-universe/lifecycle/run?force=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["admitted"][0]["ticker"] == "MSFT"


def test_add_ticker_quality_gate_passed(client, mock_service):
    mock_service.add_ticker_with_quality_gate = AsyncMock(return_value={
        "success": True,
        "message": "AAPL added",
    })

    resp = client.post("/api/v1/ticker-universe", json={"ticker": "AAPL"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert "AAPL added" in resp.json()["message"]


def test_add_ticker_quality_gate_rejected(client, mock_service):
    mock_service.add_ticker_with_quality_gate = AsyncMock(return_value={
        "success": False,
        "message": "Quality Gate Rejected: JUNK failed criteria: Penny stock",
    })

    resp = client.post("/api/v1/ticker-universe", json={"ticker": "JUNK"})
    assert resp.status_code == 400
    assert "Quality Gate Rejected" in resp.json()["detail"]
