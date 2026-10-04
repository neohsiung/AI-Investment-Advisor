"""
Unit tests for Cognitive Blindspot Detector & Self-Reflection Alignment (A2 Engine).
Tests:
- Streak detection & failure pattern classification (TREND_OVERCONFIDENCE, DOWNTREND_DENIAL, etc.)
- Corrective guidance prompt generation
- Persistence and update of agent_cognitive_blindspots
- Retrieval of active blindspots & CIO summary prompt injection
- Blindspot manual resolution endpoint & scan endpoint
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import council as council_ep
from src.services.cognitive_blindspot_service import (
    CognitiveBlindspotService,
    BiasPattern,
    BlindspotSeverity,
    STANDARD_AGENT_ROSTER,
)
from src.data.models import AgentCognitiveBlindspot


@pytest.fixture
def blindspot_service():
    service = CognitiveBlindspotService(user_id="test_user_a2", consecutive_failure_threshold=2)
    return service


def test_classify_bias_pattern(blindspot_service):
    """Test pattern categorization based on agent role, regime, and failed signals."""
    # Technical with failed BUY signals -> TREND_OVERCONFIDENCE
    pattern, sev = blindspot_service._classify_bias_pattern(
        "Technical", ["BUY", "BUY"], avg_loss=0.03, current_regime="BULL_HIGH_VOL"
    )
    assert pattern == BiasPattern.TREND_OVERCONFIDENCE
    assert sev == BlindspotSeverity.HIGH

    # Any agent with failed BUY in BEAR regime -> DOWNTREND_DENIAL
    pattern_bear, sev_bear = blindspot_service._classify_bias_pattern(
        "Fundamental", ["BUY", "STRONG_BUY"], avg_loss=0.06, current_regime="BEAR_HIGH_VOL"
    )
    assert pattern_bear == BiasPattern.DOWNTREND_DENIAL
    assert sev_bear == BlindspotSeverity.CRITICAL

    # Valuation agent -> ANCHORING_BIAS
    pattern_val, _ = blindspot_service._classify_bias_pattern(
        "Valuation", ["BUY", "HOLD"], avg_loss=0.015, current_regime="SIDEWAYS_LOW_VOL"
    )
    assert pattern_val == BiasPattern.ANCHORING_BIAS

    # Risk agent with failed defensive calls -> FALSE_ALARM_PARANOIA
    pattern_risk, _ = blindspot_service._classify_bias_pattern(
        "Risk", ["SELL", "DEFENSIVE"], avg_loss=0.005, current_regime="BULL_LOW_VOL"
    )
    assert pattern_risk == BiasPattern.FALSE_ALARM_PARANOIA


def test_generate_corrective_guidance(blindspot_service):
    """Ensure guidance contains structured reflection alerts and concrete instructions."""
    guidance = blindspot_service._generate_corrective_guidance(
        agent_name="Technical",
        pattern=BiasPattern.TREND_OVERCONFIDENCE,
        streak=3,
        avg_loss=0.042,
        current_regime="SIDEWAYS_HIGH_VOL",
    )
    assert "COGNITIVE BLINDSPOT ALERT: [Technical]" in guidance
    assert "TREND OVERCONFIDENCE" in guidance
    assert "volume exhaustion" in guidance


def test_scan_and_detect_blindspots_with_mock_history(blindspot_service):
    """Test scanning history where Technical has 2 consecutive losses."""
    mock_rows = [
        # (agent_name, signal, realized_return_pct, benchmark_return_pct, alpha_pct, resolved_at)
        # Technical recent 2 misses (realized < 0 and alpha < 0)
        ("Technical", "BUY", -0.05, 0.01, -0.06, "2026-07-03"),
        ("Technical", "BUY", -0.03, 0.00, -0.03, "2026-07-02"),
        # Technical older hit
        ("Technical", "BUY", 0.08, 0.02, 0.06, "2026-07-01"),
        # Risk recent 1 hit
        ("Risk", "DEFENSIVE", -0.02, -0.05, 0.03, "2026-07-03"),
    ]

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = mock_rows
    blindspot_service.engine = MagicMock()
    blindspot_service.engine.connect.return_value.__enter__.return_value = mock_conn

    # Mock _persist_blindspot
    with patch.object(blindspot_service, "_persist_blindspot") as mock_persist:
        mock_persist.return_value = AgentCognitiveBlindspot(
            id="mock-bs-1",
            user_id="test_user_a2",
            agent_name="Technical",
            bias_pattern=BiasPattern.TREND_OVERCONFIDENCE.value,
            regime="BULL_HIGH_VOL",
            consecutive_failures=2,
            avg_alpha_loss=0.045,
            severity="HIGH",
            corrective_guidance="Mock guidance",
            is_active=True,
        )

        detected = blindspot_service.scan_and_detect_blindspots(current_regime="BULL_HIGH_VOL")
        assert len(detected) == 1
        assert detected[0].agent_name == "Technical"
        mock_persist.assert_called_once()


def test_get_cio_blindspot_summary(blindspot_service):
    """Test generating CIO summary across active agent blindspots."""
    with patch.object(blindspot_service, "get_active_blindspots") as mock_active:
        mock_active.return_value = [
            AgentCognitiveBlindspot(
                id="bs-1",
                user_id="test_user_a2",
                agent_name="Technical",
                bias_pattern="TREND_OVERCONFIDENCE",
                regime="SIDEWAYS_HIGH_VOL",
                consecutive_failures=3,
                avg_alpha_loss=0.035,
                severity="HIGH",
                corrective_guidance="Guidance",
                is_active=True,
            )
        ]
        summary = blindspot_service.get_cio_blindspot_summary()
        assert "Cognitive Blindspot Warnings for Debate Participants" in summary
        assert "Technical" in summary
        assert "TREND_OVERCONFIDENCE" in summary
        assert "CIO Directive" in summary


def test_blindspots_api_endpoints():
    """Verify GET /blindspots, POST /blindspots/scan, and POST /blindspots/{id}/resolve."""
    app = FastAPI()
    app.include_router(council_ep.router, prefix="/api/v1/council")

    mock_service = MagicMock()
    app.dependency_overrides[council_ep.get_blindspot_service] = lambda: mock_service
    client = TestClient(app)

    # 1. GET /blindspots
    mock_service.get_active_blindspots.return_value = [
        AgentCognitiveBlindspot(
            id="bs-test-123",
            user_id="system",
            agent_name="Technical",
            bias_pattern="TREND_OVERCONFIDENCE",
            regime="BULL_HIGH_VOL",
            consecutive_failures=2,
            avg_alpha_loss=0.04,
            severity="HIGH",
            corrective_guidance="Reflection guidance",
            is_active=True,
            detected_at=None,
            resolved_at=None,
        )
    ]
    resp = client.get("/api/v1/council/blindspots")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_active"] == 1
    assert data["blindspots"][0]["agent_name"] == "Technical"

    # 2. POST /blindspots/scan
    mock_service.scan_and_detect_blindspots.return_value = [mock_service.get_active_blindspots.return_value[0]]
    scan_resp = client.post("/api/v1/council/blindspots/scan?regime=BULL_HIGH_VOL")
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()
    assert scan_data["new_blindspots_detected"] == 1

    # 3. POST /blindspots/{id}/resolve
    mock_service.resolve_blindspot.return_value = True
    resolve_resp = client.post("/api/v1/council/blindspots/bs-test-123/resolve", json={"resolution_note": "Calibrated"})
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["blindspot_id"] == "bs-test-123"
