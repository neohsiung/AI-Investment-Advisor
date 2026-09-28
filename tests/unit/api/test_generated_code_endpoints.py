"""
Unit Tests for Autonomous Code Generation & Canary API Endpoints
==================================================================
驗測 /api/v1/generated-code 端點之查詢、觸發合成、人工核准與一鍵熔斷控制。
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_current_user_id
from src.api.v1.endpoints import generated_code as ep
from src.services.canary_shadow_runner import (
    ArtifactStatus,
    canary_runner,
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OWNER_ID", "test_user_001")
    app = FastAPI()
    app.include_router(ep.router, prefix="/api/v1/generated-code")

    # Dependency override for test user
    app.dependency_overrides[get_current_user_id] = lambda: "test_user_001"
    return TestClient(app)


def test_list_generated_artifacts_empty(client: TestClient):
    resp = client.get("/api/v1/generated-code")
    assert resp.status_code == 200
    data = resp.json()
    assert "artifacts" in data
    assert "total_count" in data


def test_synthesize_factor_endpoint(client: TestClient):
    payload = {
        "hypothesis": "Momentum factor with ATR normalization for rebound detection",
        "target_regime": "VOLATILITY_PIVOT",
        "tier": "smart",
    }
    resp = client.post("/api/v1/generated-code/synthesize", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] is not None
    assert "def calculate_factor" in data["source_code"]
    assert data["status"] in (ArtifactStatus.PROVISIONAL, ArtifactStatus.VERIFIED)
    assert len(data["ast_hash"]) == 64


def test_approve_and_kill_endpoints(client: TestClient):
    # Pre-register artifact in canary runner
    record = canary_runner.register_artifact(
        user_id="test_user_001",
        name="test_canary_factor",
        description="Factor for approval",
        source_code="def calc(): pass",
        test_code="",
        ast_hash="123456",
        status=ArtifactStatus.PROVISIONAL,
    )

    # 1. Approve
    resp = client.post(f"/api/v1/generated-code/{record.id}/approve")
    assert resp.status_code == 200
    assert resp.json()["new_status"] == ArtifactStatus.ACTIVE

    # 2. Kill switch
    resp = client.post(f"/api/v1/generated-code/{record.id}/kill")
    assert resp.status_code == 200
    assert resp.json()["new_status"] == ArtifactStatus.KILLED
