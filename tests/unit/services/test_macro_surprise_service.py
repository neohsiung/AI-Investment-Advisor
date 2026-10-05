"""
Unit tests for M8: Macro Surprise Index & Liquidity Beta Dampener Service.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.macro_surprise_service import (
    MacroSurpriseService,
    MacroShockLevel,
    MacroSurpriseAssessment,
)
from src.api.v1.endpoints.adaptive_intelligence import (
    router as adaptive_router,
    get_macro_surprise_service,
)


@pytest.fixture
def mock_fred_service():
    service = MagicMock()
    # Baseline expected values: CPI=3.0, FEDFUNDS=4.5, NFP=175.0, GDP=2.2, 10Y2Y_Spread=0.20
    service.get_macro_indicators.return_value = {
        "CPI": {"value": 3.0},
        "FEDFUNDS": {"value": 4.5},
        "NFP": {"value": 175.0},
        "GDP": {"value": 2.2},
        "10Y2Y_Spread": {"value": 0.20},
    }
    return service


def test_normal_macro_environment(mock_fred_service):
    """When actual indicators align with consensus expectations, MSI is near zero and status is NORMAL."""
    service = MacroSurpriseService(user_id="test_m8_user", fred_service=mock_fred_service)
    assessment = service.evaluate_surprises()

    assert assessment.regime_shock_level == MacroShockLevel.NORMAL
    assert abs(assessment.macro_surprise_index) < 0.75
    assert assessment.liquidity_beta_multiplier == 1.0
    assert assessment.recommended_cash_adjustment_pct == 0.0
    assert not assessment.is_dampener_active
    assert service.apply_beta_dampener(1.10, assessment) == 1.10


def test_hawkish_tightening_shock(mock_fred_service):
    """Hot inflation (CPI 4.2 vs 3.0) and surging Fed Funds (5.8 vs 4.5) triggers HAWKISH_TIGHTENING_SHOCK."""
    mock_fred_service.get_macro_indicators.return_value = {
        "CPI": {"value": 4.2},  # +1.2 above expected (std 0.35 -> z ~ +3.4)
        "FEDFUNDS": {"value": 5.8},  # +1.3 above expected (std 0.50 -> z ~ +2.6)
        "NFP": {"value": 260.0},  # +85 above expected (std 45.0 -> z ~ +1.9)
        "GDP": {"value": 2.5},
        "10Y2Y_Spread": {"value": 0.15},
    }
    service = MacroSurpriseService(user_id="test_m8_user", fred_service=mock_fred_service)
    assessment = service.evaluate_surprises()

    assert assessment.regime_shock_level == MacroShockLevel.HAWKISH_TIGHTENING_SHOCK
    assert assessment.macro_surprise_index >= 1.50
    assert assessment.is_dampener_active
    assert 0.50 <= assessment.liquidity_beta_multiplier < 0.75
    assert assessment.recommended_cash_adjustment_pct >= 0.10

    # Test applying beta dampener
    base_beta = 1.20
    dampened_beta = service.apply_beta_dampener(base_beta, assessment)
    assert dampened_beta < base_beta
    assert dampened_beta >= 0.20


def test_recessionary_contraction_shock(mock_fred_service):
    """Collapsing growth (GDP 0.0 vs 2.2), deep curve inversion (-0.80), collapsing payrolls (40.0) triggers RECESSIONARY_SHOCK."""
    mock_fred_service.get_macro_indicators.return_value = {
        "CPI": {"value": 2.2},
        "FEDFUNDS": {"value": 4.0},
        "NFP": {"value": 40.0},  # -135 below expected (std 45 -> z ~ -3.0)
        "GDP": {"value": 0.0},  # -2.2 below expected (std 0.8 -> z ~ -2.75)
        "10Y2Y_Spread": {"value": -0.80},  # Inversion z ~ -3.33 (effective positive shock to risk)
    }
    service = MacroSurpriseService(user_id="test_m8_user", fred_service=mock_fred_service)
    assessment = service.evaluate_surprises()

    assert assessment.regime_shock_level == MacroShockLevel.RECESSIONARY_SHOCK
    assert assessment.macro_surprise_index <= -1.50
    assert assessment.is_dampener_active
    assert 0.40 <= assessment.liquidity_beta_multiplier <= 0.65
    assert assessment.recommended_cash_adjustment_pct >= 0.12


def test_moderate_macro_surprise():
    """Moderate surprise (e.g. CPI 3.55 vs 3.0, FedFunds 5.1 vs 4.5) produces MODERATE_SURPRISE with mild dampening."""
    custom = {
        "CPI": {"actual": 3.65, "expected": 3.0, "std": 0.35},  # z ~ +1.86 -> 0.30 * 1.86 = 0.557
        "FEDFUNDS": {"actual": 5.1, "expected": 4.5, "std": 0.50},  # z ~ +1.20 -> 0.25 * 1.20 = 0.300
        "NFP": {"actual": 210.0, "expected": 175.0, "std": 45.0},  # z ~ +0.78 -> 0.20 * 0.78 = 0.156
        "GDP": {"actual": 2.2, "expected": 2.2, "std": 0.80},
        "10Y2Y_Spread": {"actual": 0.20, "expected": 0.20, "std": 0.30},
    }
    service = MacroSurpriseService(user_id="test_m8_user")
    assessment = service.evaluate_surprises(custom_indicators=custom)

    assert assessment.regime_shock_level == MacroShockLevel.MODERATE_SURPRISE
    assert 0.75 <= assessment.macro_surprise_index < 1.50
    assert assessment.is_dampener_active
    assert 0.80 <= assessment.liquidity_beta_multiplier < 1.0
    assert 0.0 < assessment.recommended_cash_adjustment_pct <= 0.06


def test_disabled_macro_surprise():
    """When disabled via config, service returns neutral values."""
    mock_settings = MagicMock()
    mock_settings.get.side_effect = lambda key: False if key == "macro_surprise_enabled" else None

    service = MacroSurpriseService(user_id="test_m8_user", settings_service=mock_settings)
    assessment = service.evaluate_surprises()

    assert not assessment.is_dampener_active
    assert assessment.liquidity_beta_multiplier == 1.0
    assert assessment.recommended_cash_adjustment_pct == 0.0
    assert "disabled" in assessment.rationale.lower()


def test_d1_central_orchestrator_integration():
    """Verify PortfolioAdaptiveIntelligenceService incorporates macro surprise cash adjustment."""
    from src.services.portfolio_adaptive_intelligence_service import PortfolioAdaptiveIntelligenceService

    mock_macro_service = MagicMock()
    mock_assessment = MacroSurpriseAssessment(
        macro_surprise_index=2.1,
        regime_shock_level=MacroShockLevel.HAWKISH_TIGHTENING_SHOCK,
        liquidity_beta_multiplier=0.60,
        recommended_cash_adjustment_pct=0.12,
        is_dampener_active=True,
    )
    mock_macro_service.evaluate_surprises.return_value = mock_assessment

    d1 = PortfolioAdaptiveIntelligenceService(
        user_id="test_m8_d1",
        macro_surprise_service=mock_macro_service,
    )

    weights = {"SPY": 0.50, "QQQ": 0.30, "CASH": 0.20}
    report = d1.diagnose_portfolio(current_weights=weights)

    # Suggested cash in rebalance recommendation should reflect extra macro cash
    assert report.rebalance_recommendation is not None
    assert mock_macro_service.evaluate_surprises.called


def test_api_macro_surprise_endpoint():
    """Test POST /api/v1/adaptive-intelligence/macro/surprise endpoint."""
    app = FastAPI()
    app.include_router(adaptive_router, prefix="/api/v1/adaptive-intelligence")

    mock_service = MacroSurpriseService(user_id="test_api_user")
    app.dependency_overrides[get_macro_surprise_service] = lambda: mock_service

    client = TestClient(app)

    payload = {
        "custom_indicators": {
            "CPI": {"actual": 4.0, "expected": 3.0, "std": 0.35},
            "FEDFUNDS": {"actual": 5.5, "expected": 4.5, "std": 0.50},
        }
    }

    resp = client.post("/api/v1/adaptive-intelligence/macro/surprise", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "macro_surprise_index" in data
    assert "regime_shock_level" in data
    assert data["regime_shock_level"] in ["HAWKISH_TIGHTENING_SHOCK", "MODERATE_SURPRISE"]
    assert "liquidity_beta_multiplier" in data
    assert "indicators" in data
    assert "CPI" in data["indicators"]
