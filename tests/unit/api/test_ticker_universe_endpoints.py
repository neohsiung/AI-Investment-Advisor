"""
Unit tests for Ticker Universe API endpoints (src/api/v1/endpoints/ticker_universe.py).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.ticker_universe import router, get_service, get_shadow_orchestrator


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
def mock_shadow_orchestrator():
    orch = MagicMock()
    return orch


@pytest.fixture
def client(app, mock_service, mock_shadow_orchestrator):
    app.dependency_overrides[get_service] = lambda: mock_service
    app.dependency_overrides[get_shadow_orchestrator] = lambda: mock_shadow_orchestrator
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


def test_reclaim_capital_endpoint(client, mock_service):
    mock_service.user_id = "test-user-001"
    with patch("src.services.confidence_rebalance_service.ConfidenceRebalanceService.reclaim_capital_for_buy", new_callable=AsyncMock) as mock_reclaim:
        mock_reclaim.return_value = {
            "status": "success",
            "message": "Capital planned",
            "needed_amount": 50.0,
            "reclaimed_amount": 60.0,
            "sales_planned": [{"ticker": "TSLA", "amount": 60.0}],
            "candidate_ticker": "NVDA",
        }
        resp = client.post(
            "/api/v1/ticker-universe/rebalance/reclaim-capital",
            json={
                "candidate_ticker": "NVDA",
                "target_amount": 50.0,
                "candidate_score": 8.8,
                "execute": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["reclaimed_amount"] == 60.0


def test_pyramid_screen_endpoint(client, mock_service):
    mock_service.run_pyramid_screen = AsyncMock(return_value={
        "stage1_total_scanned": 150,
        "stage1_candidates": [{"ticker": "NVDA", "quant_score": 9.2}],
        "stage2_approved": [{"ticker": "NVDA", "overall_score": 8.7}],
        "admitted_to_universe": ["NVDA"],
    })

    resp = client.post("/api/v1/ticker-universe/pyramid-screen?top_n=10&auto_admit=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["stage1_total_scanned"] == 150
    assert data["data"]["admitted_to_universe"] == ["NVDA"]


def test_pin_ticker_endpoint(client, mock_service):
    mock_service.set_ticker_pin.return_value = {
        "success": True,
        "message": "NVDA pinned (user-designated, immune to rotation/eviction)",
    }

    resp = client.put("/api/v1/ticker-universe/NVDA/pin", json={"is_pinned": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "NVDA pinned" in data["message"]
    mock_service.set_ticker_pin.assert_called_with("NVDA", True)


def test_evolve_active_endpoint(client, mock_service):
    mock_service.evolve_active = AsyncMock(return_value={
        "success": True,
        "message": "Active pool evolution complete",
        "rotation_count": 1,
        "rotations": [
            {
                "demoted_ticker": "OLD_TICKER",
                "promoted_ticker": "NEW_TICKER",
                "score_delta": 2.5,
            }
        ],
        "total_active": 8,
        "pinned_active_count": 4,
        "unpinned_active_count": 4,
    })

    resp = client.post("/api/v1/ticker-universe/active/evolve?rotation_hurdle=1.5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["rotation_count"] == 1
    assert data["data"]["rotations"][0]["promoted_ticker"] == "NEW_TICKER"


def test_get_shadow_promotions_endpoint(client, mock_shadow_orchestrator):
    from src.services.shadow_promotion_orchestrator import PromotionProposal
    mock_shadow_orchestrator.evaluate_promotions = AsyncMock(return_value=[
        PromotionProposal(
            candidate_ticker="NVDA",
            action_type="CAPITAL_ROTATION",
            qualified=True,
            candidate_metrics={"unrealized_pnl_pct": 12.5},
            displaced_ticker="INTC",
            displaced_metrics={"holding_days": 35, "has_decay": True},
            raw_score_delta=5.0,
            net_opportunity_delta=0.035,
            hurdle=0.0175,
            roundtrip_friction=0.003,
            estimated_capital=1500.0,
            sor_plans=[{"symbol": "INTC", "action": "SELL"}, {"symbol": "NVDA", "action": "BUY"}],
            rationale="Approved rotation displacing stagnant INTC",
            can_auto_execute=True,
            status="PENDING_APPROVAL",
        )
    ])

    resp = client.get("/api/v1/ticker-universe/shadow/promotions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_qualified"] == 1
    assert data["total_rotations"] == 1
    assert len(data["data"]) == 1
    item = data["data"][0]
    assert item["candidate_ticker"] == "NVDA"
    assert item["displaced_ticker"] == "INTC"
    assert item["action_type"] == "CAPITAL_ROTATION"


def test_execute_shadow_promotion_endpoint(client, mock_shadow_orchestrator):
    from src.services.shadow_promotion_orchestrator import PromotionExecutionResult
    mock_shadow_orchestrator.execute_promotion = AsyncMock(return_value=PromotionExecutionResult(
        success=True,
        action_type="CAPITAL_ROTATION",
        candidate_ticker="NVDA",
        displaced_ticker="INTC",
        graduated_position_id="shadow-123",
        sor_execution_plans=[{"symbol": "INTC"}, {"symbol": "NVDA"}],
        alert_dispatched=True,
        message="Promotion executed successfully",
    ))

    resp = client.post("/api/v1/ticker-universe/shadow/promotions/execute", json={
        "candidate_ticker": "NVDA",
        "displaced_ticker": "INTC",
        "auto_rebalance": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["candidate_ticker"] == "NVDA"
    assert data["data"]["displaced_ticker"] == "INTC"
    assert data["data"]["success"] is True




