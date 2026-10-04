"""
Unit tests for Adaptive Council Meta-Learning Loop (A1 Engine).
Tests:
- Laplace smoothed outcome attribution and rolling win rate
- Regime-conditioned Bayesian meta-weights calibration
- EVT Black Swan tail risk detection and Risk Agent veto power
- Prior context generation and prompt guidance synthesis
- FastAPI endpoint responses for status, attributions, and calibration
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import council as council_ep
from src.services.adaptive_council_meta_learning_service import (
    AdaptiveCouncilMetaLearningService,
    AgentAttributionMetrics,
    AdaptiveCouncilContext,
    DEFAULT_REGIME_PRIORS,
    STANDARD_AGENT_ROSTER,
)


@pytest.fixture
def meta_service():
    service = AdaptiveCouncilMetaLearningService(user_id="test_user_a1")
    return service


def test_meta_service_default_priors():
    """Verify default regime priors sum to 1.0 across all known regimes."""
    for regime, weights in DEFAULT_REGIME_PRIORS.items():
        total_w = sum(weights.values())
        assert abs(total_w - 1.0) < 1e-4, f"Regime {regime} weights do not sum to 1.0 (got {total_w})"
        assert "Risk" in weights


def test_agent_attributions_empty_history(meta_service):
    """When no decision outcomes exist, attributions default to Laplace prior (0.50 win rate)."""
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []
    meta_service.engine = MagicMock()
    meta_service.engine.connect.return_value.__enter__.return_value = mock_conn

    attributions = meta_service.compute_agent_attributions()
    assert len(attributions) == len(STANDARD_AGENT_ROSTER)
    for agent in STANDARD_AGENT_ROSTER:
        attr = attributions[agent]
        assert attr.total_calls == 0
        assert attr.correct_calls == 0
        assert attr.rolling_win_rate == 0.50
        assert attr.avg_alpha_contribution == 0.0


def test_agent_attributions_with_mock_history(meta_service):
    """Verify Laplace smoothing and alpha calculation with historical outcomes."""
    mock_rows = [
        # (agent_name, signal, realized_return_pct, benchmark_return_pct, alpha_pct, resolved_at)
        ("Risk", "DEFENSIVE", -0.02, -0.05, 0.03, "2026-07-01"),
        ("Risk", "SELL", -0.01, -0.03, 0.02, "2026-07-02"),
        ("Risk", "SELL", 0.02, 0.01, -0.01, "2026-07-03"),
        ("Technical", "BUY", 0.05, 0.02, 0.03, "2026-07-01"),
        ("Technical", "BUY", -0.04, -0.01, -0.03, "2026-07-02"),
    ]

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = mock_rows
    meta_service.engine = MagicMock()
    meta_service.engine.connect.return_value.__enter__.return_value = mock_conn

    attributions = meta_service.compute_agent_attributions()
    risk_attr = attributions["Risk"]
    tech_attr = attributions["Technical"]
    assert risk_attr.total_calls == 3
    assert risk_attr.correct_calls == 2
    # Laplace smoothing: (2 + 1) / (3 + 2) = 3/5 = 0.60
    assert abs(risk_attr.rolling_win_rate - 0.60) < 1e-4
    assert risk_attr.avg_alpha_contribution > 0.0

    assert tech_attr.total_calls == 2
    assert tech_attr.correct_calls == 1
    # Laplace smoothing: (1 + 1) / (2 + 2) = 2/4 = 0.50
    assert abs(tech_attr.rolling_win_rate - 0.50) < 1e-4


def test_calibrate_meta_weights_normal_regime(meta_service):
    """In a normal bull regime, high win-rate agents gain weight, low win-rate lose weight."""
    mock_attributions = {
        "Technical": AgentAttributionMetrics(agent_name="Technical", rolling_win_rate=0.75),
        "Sentiment": AgentAttributionMetrics(agent_name="Sentiment", rolling_win_rate=0.30),
        "Fundamental": AgentAttributionMetrics(agent_name="Fundamental", rolling_win_rate=0.50),
        "Valuation": AgentAttributionMetrics(agent_name="Valuation", rolling_win_rate=0.50),
        "Risk": AgentAttributionMetrics(agent_name="Risk", rolling_win_rate=0.50),
    }

    calibrated = meta_service.calibrate_meta_weights(
        current_regime="BULL_LOW_VOL",
        is_black_swan_alert=False,
        attributions=mock_attributions,
    )

    prior = DEFAULT_REGIME_PRIORS["BULL_LOW_VOL"]
    # Technical should be amplified compared to prior
    assert calibrated["Technical"] > prior["Technical"]
    # Sentiment should be dampened compared to prior
    assert calibrated["Sentiment"] < prior["Sentiment"]
    # Sum of calibrated weights must remain 1.0
    assert abs(sum(calibrated.values()) - 1.0) < 1e-4


def test_calibrate_meta_weights_black_swan_veto(meta_service):
    """When Black Swan alert is active, Risk Agent receives >= 50% veto power."""
    mock_attributions = {
        agent: AgentAttributionMetrics(agent_name=agent, rolling_win_rate=0.50)
        for agent in STANDARD_AGENT_ROSTER
    }

    calibrated = meta_service.calibrate_meta_weights(
        current_regime="BULL_LOW_VOL",
        is_black_swan_alert=True,  # EVT WARNING or CRITICAL
        attributions=mock_attributions,
    )

    assert calibrated["Risk"] >= 0.50
    assert abs(sum(calibrated.values()) - 1.0) < 1e-4


def test_generate_adaptive_council_context_structure(meta_service):
    """Verify that synthesized context includes D1, O1, O2 metrics and prompt text."""
    ctx = meta_service.generate_adaptive_council_context()

    assert isinstance(ctx, AdaptiveCouncilContext)
    assert ctx.current_regime in DEFAULT_REGIME_PRIORS
    assert 0.0 <= ctx.regime_confidence <= 1.0
    assert ctx.black_swan_alert_level in ("NORMAL", "ELEVATED", "WARNING", "CRITICAL")
    assert ctx.var_999 > 0.0
    assert ctx.cvar_999 >= ctx.var_999
    assert ctx.health_score > 0.0
    assert "## [A1 Meta-Learning Prior Context]" in ctx.prompt_guidance
    assert "Risk" in ctx.meta_weights
    assert abs(sum(ctx.meta_weights.values()) - 1.0) < 1e-4


def test_api_council_meta_learning_endpoints():
    """Verify FastAPI GET /meta-learning/status, attributions, and POST /calibrate."""
    app = FastAPI()
    app.include_router(council_ep.router, prefix="/api/v1/council")
    client = TestClient(app)

    # 1. Status endpoint
    resp_status = client.get("/api/v1/council/meta-learning/status")
    assert resp_status.status_code == 200
    data_status = resp_status.json()
    assert data_status["status"] == "success"
    assert "current_regime" in data_status
    assert "meta_weights" in data_status
    assert "prompt_guidance" in data_status

    # 2. Attributions endpoint
    resp_attrs = client.get("/api/v1/council/meta-learning/attributions")
    assert resp_attrs.status_code == 200
    data_attrs = resp_attrs.json()
    assert data_attrs["status"] == "success"
    assert "Risk" in data_attrs["attributions"]
    assert "rolling_win_rate" in data_attrs["attributions"]["Risk"]

    # 3. Calibrate endpoint
    resp_calib = client.post("/api/v1/council/meta-learning/calibrate")
    assert resp_calib.status_code == 200
    data_calib = resp_calib.json()
    assert data_calib["status"] == "success"
    assert "meta_weights" in data_calib
