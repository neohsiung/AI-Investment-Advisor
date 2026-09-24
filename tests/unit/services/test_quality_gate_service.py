"""
Unit tests for QualityGateService (src/services/quality_gate_service.py).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.services.quality_gate_service import QualityGateService, QualityAssessment


@pytest.fixture
def mock_market():
    market = MagicMock()
    market.get_financials.return_value = {
        "marketCap": 2_500_000_000_000,
        "currentPrice": 180.0,
        "debtToEquity": 0.8,
        "returnOnEquity": 0.35,
        "operatingMargins": 0.30,
        "revenueGrowth": 0.12,
        "forwardPE": 28.0,
        "averageVolume": 50_000_000,
        "shortName": "Apple Inc.",
        "sector": "Technology",
    }
    market.get_current_prices = AsyncMock(return_value={"AAPL": 180.0})
    market.get_technical_indicators.return_value = {
        "rsi": 55.0,
        "macd": "bullish",
        "sma": {
            "sma_50": 175.0,
            "sma_200": 160.0,
        },
        "volume": {
            "avg_20": 50_000_000,
            "current": 48_000_000,
        },
    }
    return market


@pytest.fixture
def quality_service(mock_market):
    with patch("src.services.quality_gate_service.SettingsService") as mock_settings_cls:
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda k: {
            "universe_min_quality_score": 6.5,
            "universe_min_market_cap_billions": 2.0,
            "universe_min_daily_volume_millions": 5.0,
        }.get(k, None)
        mock_settings_cls.return_value = mock_settings

        svc = QualityGateService(user_id="test-user", market_data_service=mock_market)
        yield svc


@pytest.mark.asyncio
async def test_evaluate_ticker_healthy_stock(quality_service):
    assessment = await quality_service.evaluate_ticker("AAPL")
    assert assessment.passed is True
    assert assessment.hard_gates_passed is True
    assert assessment.overall_score >= 6.5
    assert assessment.fundamental_score > 7.0
    assert assessment.technical_score > 7.0
    assert assessment.liquidity_score > 7.0
    assert assessment._insufficient_data is False


@pytest.mark.asyncio
async def test_evaluate_ticker_penny_stock(quality_service, mock_market):
    mock_market.get_financials.return_value = {
        "marketCap": 100_000_000,
        "currentPrice": 2.50,  # Below $5
        "debtToEquity": 1.2,
        "returnOnEquity": 0.05,
    }
    mock_market.get_current_prices = AsyncMock(return_value={"PENNY": 2.50})
    mock_market.get_technical_indicators.return_value = {
        "rsi": 40.0,
        "macd": "bearish",
        "sma": {"sma_50": 3.0, "sma_200": 3.5},
        "volume": {"avg_20": 100_000},
    }

    assessment = await quality_service.evaluate_ticker("PENNY")
    assert assessment.passed is False
    assert assessment.hard_gates_passed is False
    assert any("penny stock" in r.lower() for r in assessment.reasons)


@pytest.mark.asyncio
async def test_evaluate_ticker_low_market_cap(quality_service, mock_market):
    mock_market.get_financials.return_value = {
        "marketCap": 500_000_000,  # $0.5B < $2.0B threshold
        "currentPrice": 25.0,
        "debtToEquity": 0.5,
        "returnOnEquity": 0.10,
    }
    mock_market.get_current_prices = AsyncMock(return_value={"MICRO": 25.0})
    mock_market.get_technical_indicators.return_value = {
        "rsi": 50.0,
        "macd": "bullish",
        "sma": {"sma_50": 24.0, "sma_200": 22.0},
        "volume": {"avg_20": 1_000_000},
    }

    assessment = await quality_service.evaluate_ticker("MICRO")
    assert assessment.passed is False
    assert assessment.hard_gates_passed is False
    assert any("market cap" in r.lower() for r in assessment.reasons)


@pytest.mark.asyncio
async def test_evaluate_ticker_insufficient_data(quality_service, mock_market):
    mock_market.get_financials.return_value = {}
    mock_market.get_current_prices = AsyncMock(return_value={"UNKNOWN": 0.0})
    mock_market.get_technical_indicators.return_value = {"_insufficient_data": True}

    assessment = await quality_service.evaluate_ticker("UNKNOWN")
    assert assessment.passed is False
    assert assessment._insufficient_data is True
    assert assessment.overall_score == 0.0


@pytest.mark.asyncio
async def test_evaluate_ticker_exception_safety(quality_service, mock_market):
    mock_market.get_financials.side_effect = RuntimeError("Provider down")

    assessment = await quality_service.evaluate_ticker("CRASH")
    assert assessment.passed is False
    assert assessment.overall_score == 0.0
    assert assessment._fallback_reason is not None
    assert "Provider down" in assessment._fallback_reason
