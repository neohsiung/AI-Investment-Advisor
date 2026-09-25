"""
Unit tests for UniverseLifecycleService (src/services/universe_lifecycle_service.py).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.services.universe_lifecycle_service import UniverseLifecycleService, MacroRegime
from src.services.quality_gate_service import QualityAssessment


@pytest.fixture
def mock_deps():
    repo = MagicMock()
    market = MagicMock()
    quality_gate = MagicMock()
    settings = MagicMock()

    settings.get_setting.side_effect = lambda k: {
        "universe_auto_refresh_enabled": True,
        "universe_min_quality_score": 6.5,
        "universe_eviction_threshold": 4.0,
        "universe_max_active_tickers": 5,
        "universe_min_market_cap_billions": 2.0,
        "universe_min_daily_volume_millions": 5.0,
    }.get(k, None)

    return repo, market, quality_gate, settings


@pytest.mark.asyncio
async def test_detect_macro_regime_bull(mock_deps):
    repo, market, quality_gate, settings = mock_deps
    market.get_current_prices = AsyncMock(return_value={"^VIX": 15.0, "SPY": 500.0})
    market.get_technical_indicators.return_value = {"sma": {"sma_200": 450.0}}
    market.get_yield_curve_inversion.return_value = {"is_inverted": False}

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )
        regime = await service.detect_macro_regime()
        assert regime.regime == "BULL_GROWTH"
        assert regime.quality_score_adjustment == 0.0


@pytest.mark.asyncio
async def test_detect_macro_regime_high_volatility(mock_deps):
    repo, market, quality_gate, settings = mock_deps
    market.get_current_prices = AsyncMock(return_value={"^VIX": 32.0, "SPY": 480.0})
    market.get_technical_indicators.return_value = {"sma": {"sma_200": 490.0}}
    market.get_yield_curve_inversion.return_value = {"is_inverted": False}

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )
        regime = await service.detect_macro_regime()
        assert regime.regime == "HIGH_VOLATILITY"
        assert regime.quality_score_adjustment == 0.5


@pytest.mark.asyncio
async def test_review_and_evict_active_tickers(mock_deps):
    repo, market, quality_gate, settings = mock_deps
    repo.get_all.return_value = [
        {"ticker": "DEGRADED", "status": "active"},
        {"ticker": "HEALTHY", "status": "active"},
    ]
    repo.remove.return_value = True
    repo.add_log.return_value = True

    # DEGRADED scores 3.2 (< 4.0 threshold)
    assessment_degraded = QualityAssessment(
        ticker="DEGRADED",
        passed=False,
        overall_score=3.2,
        hard_gates_passed=True,
        hard_gate_details={},
        fundamental_score=3.0,
        technical_score=3.5,
        liquidity_score=6.0,
        reasons=["Earnings collapse", "Trend broke below 200 SMA"],
        metrics={},
    )

    # HEALTHY scores 8.5
    assessment_healthy = QualityAssessment(
        ticker="HEALTHY",
        passed=True,
        overall_score=8.5,
        hard_gates_passed=True,
        hard_gate_details={},
        fundamental_score=8.5,
        technical_score=8.5,
        liquidity_score=8.5,
        reasons=["Passed all checks"],
        metrics={},
    )

    async def mock_eval(t):
        return assessment_degraded if t == "DEGRADED" else assessment_healthy

    quality_gate.evaluate_ticker = AsyncMock(side_effect=mock_eval)

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )
        evicted = await service.review_and_evict_active_tickers(eviction_threshold=4.0)

        assert len(evicted) == 1
        assert evicted[0]["ticker"] == "DEGRADED"
        assert evicted[0]["score"] == 3.2
        repo.remove.assert_called_once()
        repo.add_log.assert_called_once()


@pytest.mark.asyncio
async def test_screen_and_admit_candidates(mock_deps):
    repo, market, quality_gate, settings = mock_deps
    # Current active has 3 tickers, capacity is 5 -> 2 slots available
    repo.get_all.return_value = [
        {"ticker": "T1", "status": "active"},
        {"ticker": "T2", "status": "active"},
        {"ticker": "T3", "status": "active"},
    ]
    repo.upsert.return_value = True
    repo.add_log.return_value = True

    market.get_financials.return_value = {
        "shortName": "Candidate Corp",
        "sector": "Tech",
        "industry": "Software",
    }
    market.get_etf_holdings.return_value = []

    # 3 candidates: C1 (9.0), C2 (7.5), C3 (5.0 - fails threshold 6.5)
    def make_assessment(ticker, score, passed):
        return QualityAssessment(
            ticker=ticker,
            passed=passed,
            overall_score=score,
            hard_gates_passed=passed,
            hard_gate_details={},
            fundamental_score=score,
            technical_score=score,
            liquidity_score=score,
            reasons=[],
            metrics={},
        )

    eval_map = {
        "C1": make_assessment("C1", 9.0, True),
        "C2": make_assessment("C2", 7.5, True),
        "C3": make_assessment("C3", 5.0, False),
    }

    quality_gate.evaluate_ticker = AsyncMock(side_effect=lambda t: eval_map.get(t, make_assessment(t, 0.0, False)))

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )
        admitted = await service.screen_and_admit_candidates(
            candidate_pool=["C1", "C2", "C3"],
            max_active=5,
            min_quality_score=6.5,
        )

        # Only C1 and C2 should be admitted (C3 failed score threshold)
        assert len(admitted) == 2
        assert admitted[0]["ticker"] == "C1"
        assert admitted[1]["ticker"] == "C2"
        assert repo.upsert.call_count == 2
        assert repo.add_log.call_count == 2


@pytest.mark.asyncio
async def test_run_lifecycle_disabled(mock_deps):
    repo, market, quality_gate, settings = mock_deps
    settings.get_setting.side_effect = lambda k: {
        "universe_auto_refresh_enabled": False,
    }.get(k, None)
    repo.get_all.return_value = []

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )
        res = await service.run_lifecycle_cycle(force=False)
        assert res["success"] is True
        assert "disabled" in res["message"]
