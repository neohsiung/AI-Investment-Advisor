"""
Unit tests for A7: Council Cross-Market Contagion & Inter-Asset Transmission Engine.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.cross_market_contagion_service import (
    CrossMarketContagionService,
    ContagionRegime,
    RiskLevel,
    TransmissionChannel,
    ContagionAssessmentResult,
)
from src.api.v1.endpoints.council import (
    router as council_router,
    get_contagion_service,
)


@pytest.fixture
def contagion_service():
    return CrossMarketContagionService(user_id="test-user")


def test_default_contagion_assessment_tech(contagion_service):
    """Verifies baseline contagion assessment for Technology sector."""
    result: ContagionAssessmentResult = contagion_service.assess_contagion(
        symbol="NVDA",
        sector="Technology",
    )
    assert result.symbol == "NVDA"
    assert result.sector == "Technology"
    assert 0.0 <= result.overall_contagion_risk_score <= 1.0
    assert result.contagion_regime in (
        ContagionRegime.BENIGN,
        ContagionRegime.DIVERGENT,
        ContagionRegime.ACUTE_SPILLOVER,
        ContagionRegime.SYSTEMIC_CONTAGION,
    )
    assert len(result.channel_impacts) == 4
    channels = {impact.channel for impact in result.channel_impacts}
    assert channels == {
        TransmissionChannel.RATES_YIELD_CURVE,
        TransmissionChannel.FX_LIQUIDITY,
        TransmissionChannel.COMMODITIES_ENERGY,
        TransmissionChannel.CREDIT_VOLATILITY,
    }
    # Check rates channel negative sensitivity for Tech
    rates_impact = next(i for i in result.channel_impacts if i.channel == TransmissionChannel.RATES_YIELD_CURVE)
    assert rates_impact.sensitivity_factor < 0.0
    assert rates_impact.estimated_price_impact_pct < 0.0
    assert len(result.recommended_hedging_overlays) > 0
    assert "A7 Contagion Engine" in result.markdown_contagion_card


def test_energy_sector_sensitivity(contagion_service):
    """Verifies that Energy sector benefits positively from oil shock."""
    result = contagion_service.assess_contagion(
        symbol="XOM",
        sector="Energy",
        macro_signals={"BRENT": 10.0},
    )
    energy_impact = next(i for i in result.channel_impacts if i.channel == TransmissionChannel.COMMODITIES_ENERGY)
    assert energy_impact.sensitivity_factor > 0.0
    assert energy_impact.estimated_price_impact_pct > 0.0


def test_financials_sector_sensitivity(contagion_service):
    """Verifies Financials sensitivity to rates curve and credit spreads."""
    result = contagion_service.assess_contagion(
        symbol="JPM",
        sector="Financials",
    )
    rates_impact = next(i for i in result.channel_impacts if i.channel == TransmissionChannel.RATES_YIELD_CURVE)
    assert rates_impact.sensitivity_factor > 0.0  # Beneficiary of steepening yields


def test_custom_shocks_and_alert(contagion_service):
    """Verifies severe custom shock triggers contagion alert and systemic regime."""
    result = contagion_service.assess_contagion(
        symbol="TSLA",
        sector="Consumer Discretionary",
        custom_shocks={
            "US10Y": 15.0,
            "DXY": 6.0,
            "BRENT": 20.0,
            "VIX": 50.0,
        },
    )
    assert result.overall_contagion_risk_score >= 0.65
    assert result.is_contagion_alert is True
    assert result.contagion_regime in (ContagionRegime.ACUTE_SPILLOVER, ContagionRegime.SYSTEMIC_CONTAGION)
    assert any("🚨" in h or "防" in h or "對沖" in h for h in result.recommended_hedging_overlays)


def test_service_disabled_by_settings():
    """Verifies graceful deactivation when disabled in settings."""
    mock_settings = MagicMock()
    mock_settings.get.side_effect = lambda k, **kw: False if k == "council_contagion_enabled" else None

    service = CrossMarketContagionService(settings_service=mock_settings)
    assert service.is_enabled() is False

    result = service.assess_contagion(symbol="AAPL")
    assert result.overall_contagion_risk_score == 0.0
    assert result.contagion_regime == ContagionRegime.BENIGN
    assert result.is_contagion_alert is False
    assert "已停用" in result.markdown_contagion_card


def test_dynamic_threshold_override():
    """Verifies custom risk threshold triggers alert appropriately."""
    mock_settings = MagicMock()
    mock_settings.get.side_effect = lambda k, **kw: 0.20 if k == "council_contagion_risk_threshold" else True

    service = CrossMarketContagionService(settings_service=mock_settings)
    assert service.get_risk_threshold() == 0.20

    result = service.assess_contagion(symbol="MSFT")
    # Even moderate risk will exceed low threshold of 0.20
    assert result.is_contagion_alert is True


def test_api_endpoint_assess_contagion():
    """Verifies POST /api/v1/council/contagion/assess HTTP endpoint integration."""
    app = FastAPI()
    app.include_router(council_router, prefix="/api/v1/council")

    mock_service = CrossMarketContagionService(user_id="test_api_user")
    app.dependency_overrides[get_contagion_service] = lambda: mock_service

    client = TestClient(app)
    response = client.post(
        "/api/v1/council/contagion/assess",
        json={
            "symbol": "NVDA",
            "sector": "Semiconductors",
            "macro_signals": {"US10Y": 5.0, "DXY": 2.0},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "NVDA"
    assert data["sector"] == "Semiconductors"
    assert "overall_contagion_risk_score" in data
    assert "contagion_regime" in data
    assert len(data["channel_impacts"]) == 4
    assert len(data["recommended_hedging_overlays"]) > 0
    assert "A7 Contagion Engine" in data["markdown_contagion_card"]
