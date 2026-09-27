"""
Unit tests for PyramidScreenerService.
測試兩階段金字塔標的初篩器的各項篩選邏輯與分層把關。
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.services.pyramid_screener_service import (
    PyramidScreenerService,
    Stage1Candidate,
    PyramidScreenResult,
    EXPANDED_UNIVERSE_POOL,
)
from src.services.quality_gate_service import QualityAssessment


@pytest.fixture
def mock_market():
    market = MagicMock()
    # Mock get_current_prices
    market.get_current_prices = AsyncMock(return_value={
        "AAPL": 180.0,
        "NVDA": 120.0,
        "PENNY": 2.0,      # Should be excluded (< $5)
        "ILLIQ": 50.0,     # Low volume
        "CRASH": 40.0,     # Severely below SMA200
        "MSFT": 400.0,
    })

    # Mock get_technical_indicators
    def get_tech(ticker):
        if ticker == "CRASH":
            return {"sma": {"sma_50": 60.0, "sma_200": 80.0}, "rsi": 30.0}
        if ticker == "NVDA":
            return {"sma": {"sma_50": 110.0, "sma_200": 90.0}, "rsi": 60.0}
        if ticker == "AAPL":
            return {"sma": {"sma_50": 170.0, "sma_200": 160.0}, "rsi": 55.0}
        return {"sma": {"sma_50": 50.0, "sma_200": 50.0}, "rsi": 50.0}

    market.get_technical_indicators = MagicMock(side_effect=get_tech)

    # Mock get_financials
    def get_fin(ticker):
        if ticker == "ILLIQ":
            return {"averageDailyVolume10Day": 10_000, "shortName": "Illiquid Inc"}
        return {"averageDailyVolume10Day": 5_000_000, "shortName": f"{ticker} Corp", "sector": "Technology"}

    market.get_financials = MagicMock(side_effect=get_fin)
    return market


@pytest.fixture
def mock_quality_gate():
    gate = MagicMock()

    async def eval_ticker(sym):
        if sym in ("AAPL", "NVDA", "MSFT"):
            return QualityAssessment(
                ticker=sym,
                passed=True,
                overall_score=8.5,
                hard_gates_passed=True,
                hard_gate_details={},
                fundamental_score=8.0,
                technical_score=8.5,
                liquidity_score=9.0,
                reasons=["High quality blue chip"],
                metrics={},
            )
        return QualityAssessment(
            ticker=sym,
            passed=False,
            overall_score=4.0,
            hard_gates_passed=False,
            hard_gate_details={"price_passed": False},
            fundamental_score=4.0,
            technical_score=4.0,
            liquidity_score=4.0,
            reasons=["Failed quality gate"],
            metrics={},
        )

    gate.evaluate_ticker = AsyncMock(side_effect=eval_ticker)
    return gate


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_all = MagicMock(return_value=[{"ticker": "AAPL", "status": "active"}])
    repo.upsert = MagicMock(return_value=True)
    repo.add_log = MagicMock()
    return repo


@pytest.mark.anyio
async def test_stage1_quant_screen_filters(mock_market, mock_quality_gate, mock_repo):
    service = PyramidScreenerService(
        user_id="test_user",
        market_data_service=mock_market,
        quality_gate=mock_quality_gate,
        ticker_repo=mock_repo,
    )

    test_pool = ["AAPL", "NVDA", "PENNY", "ILLIQ", "CRASH", "MSFT"]
    results = await service.run_stage1_quant_screen(candidate_pool=test_pool, top_n=10)

    result_tickers = [c.ticker for c in results]

    # AAPL, NVDA, MSFT should pass
    assert "NVDA" in result_tickers
    assert "AAPL" in result_tickers
    assert "MSFT" in result_tickers

    # PENNY (< $5) should be excluded
    assert "PENNY" not in result_tickers

    # ILLIQ (< $10M volume) should be excluded
    assert "ILLIQ" not in result_tickers

    # CRASH (< 75% of SMA200) should be excluded
    assert "CRASH" not in result_tickers

    # Top ranked should have high quant score
    assert results[0].quant_score > 6.0


@pytest.mark.anyio
async def test_run_full_pyramid_screen_end_to_end(mock_market, mock_quality_gate, mock_repo):
    service = PyramidScreenerService(
        user_id="test_user",
        market_data_service=mock_market,
        quality_gate=mock_quality_gate,
        ticker_repo=mock_repo,
    )

    test_pool = ["AAPL", "NVDA", "MSFT"]
    res = await service.run_full_pyramid_screen(
        candidate_pool=test_pool,
        top_n=5,
        auto_admit=True,
    )

    assert isinstance(res, PyramidScreenResult)
    assert res.stage1_total_scanned == 3
    assert len(res.stage1_candidates) == 3

    # Stage 2 approved candidates
    assert len(res.stage2_approved) == 3

    # AAPL was already active in mock_repo, so only NVDA and MSFT should be admitted
    assert "NVDA" in res.admitted_to_universe
    assert "MSFT" in res.admitted_to_universe
    assert "AAPL" not in res.admitted_to_universe
    assert mock_repo.upsert.call_count == 2
