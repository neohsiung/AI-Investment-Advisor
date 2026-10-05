"""
Unit tests for A6: Council Counterfactual Reasoning & Stress Scenario Generation Service.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.counterfactual_reasoning_service import (
    CounterfactualReasoningService,
    ScenarioCategory,
    ScenarioSeverity,
    CounterfactualInoculationResult,
)
from src.api.v1.endpoints.council import (
    router as council_router,
    get_counterfactual_service,
)


def test_bullish_consensus_scenarios():
    """Verify counterfactual scenario generation for bullish consensus (e.g. NVDA Tech)."""
    service = CounterfactualReasoningService(user_id="test_a6_user")
    result = service.evaluate_inoculation(
        symbol="NVDA",
        consensus_stance="BUY",
        conviction=0.90,
        sector="Technology",
    )

    assert result.is_stress_tested
    assert len(result.scenarios) == 3
    # Should include rate shock, capex moderation, and geopolitical ban
    cats = [s.category for s in result.scenarios]
    assert ScenarioCategory.MACRO in cats
    assert ScenarioCategory.IDIOSYNCRATIC in cats
    assert ScenarioCategory.GEOPOLITICAL in cats

    # Check prompt contents
    prompt = result.cio_inoculation_prompt
    assert "NVDA" in prompt
    assert "BUY" in prompt
    assert "Mandatory Checkpoints" in prompt
    assert len(result.required_defense_checkpoints) == 3


def test_bearish_consensus_scenarios():
    """Verify counterfactual scenario generation for bearish consensus (short squeeze / turnaround)."""
    service = CounterfactualReasoningService(user_id="test_a6_user")
    result = service.evaluate_inoculation(
        symbol="TSLA",
        consensus_stance="SELL",
        conviction=0.85,
    )

    assert result.is_stress_tested
    assert len(result.scenarios) >= 2
    cats = [s.category for s in result.scenarios]
    assert ScenarioCategory.LIQUIDITY in cats
    assert any("Squeeze" in s.title or "軋空" in s.title for s in result.scenarios)


def test_neutral_consensus_scenarios():
    """Verify counterfactual scenario generation for neutral/HOLD consensus (breakout risk)."""
    service = CounterfactualReasoningService(user_id="test_a6_user")
    result = service.evaluate_inoculation(
        symbol="SPY",
        consensus_stance="HOLD",
        conviction=0.75,
    )

    assert result.is_stress_tested
    assert len(result.scenarios) >= 1
    assert any("Breakout" in s.title or "突破" in s.title for s in result.scenarios)


def test_non_tech_consumer_scenarios():
    """Verify sector-specific adaptation for non-tech stocks (e.g. Consumer Discretionary)."""
    service = CounterfactualReasoningService(user_id="test_a6_user")
    result = service.evaluate_inoculation(
        symbol="NKE",
        consensus_stance="BUY",
        sector="Consumer Discretionary",
    )

    titles = [s.title for s in result.scenarios]
    assert any("消費" in t or "Consumer" in t or "Squeeze" in t for t in titles)


def test_max_scenarios_limit():
    """Verify max_scenarios limit constraint."""
    service = CounterfactualReasoningService(user_id="test_a6_user", default_max_scenarios=2)
    result = service.evaluate_inoculation(symbol="AAPL", consensus_stance="BUY", max_scenarios=1)
    assert len(result.scenarios) == 1


def test_disabled_counterfactual_service():
    """Verify disabled mode returns empty inoculation."""
    mock_settings = MagicMock()
    mock_settings.get.side_effect = lambda key: False if key == "council_counterfactual_enabled" else None

    service = CounterfactualReasoningService(user_id="test_a6_user", settings_service=mock_settings)
    result = service.evaluate_inoculation(symbol="MSFT", consensus_stance="BUY")

    assert not result.is_stress_tested
    assert len(result.scenarios) == 0
    assert result.cio_inoculation_prompt == ""


def test_api_counterfactual_inoculate_endpoint():
    """Test POST /api/v1/council/counterfactual/inoculate endpoint."""
    app = FastAPI()
    app.include_router(council_router, prefix="/api/v1/council")

    mock_service = CounterfactualReasoningService(user_id="test_api_user")
    app.dependency_overrides[get_counterfactual_service] = lambda: mock_service

    client = TestClient(app)

    payload = {
        "symbol": "AMD",
        "consensus_stance": "BUY",
        "conviction": 0.88,
        "sector": "Semiconductors",
        "max_scenarios": 2,
    }

    resp = client.post("/api/v1/council/counterfactual/inoculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "AMD"
    assert data["consensus_stance"] == "BUY"
    assert data["is_stress_tested"] is True
    assert len(data["scenarios"]) == 2
    assert "cio_inoculation_prompt" in data
    assert len(data["required_defense_checkpoints"]) == 3
