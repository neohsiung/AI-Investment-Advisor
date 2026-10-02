"""
Unit tests for Candidate Pool Lifecycle Evolution and Dynamic Elimination/Retention (汰弱留強).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.universe_lifecycle_service import UniverseLifecycleService, MacroRegime
from src.services.quality_gate_service import QualityAssessment


@pytest.fixture
def mock_lifecycle_deps():
    repo = MagicMock()
    market = MagicMock()
    quality_gate = MagicMock()
    settings = MagicMock()

    settings.get_setting.side_effect = lambda k, default=None: {
        "universe_auto_refresh_enabled": True,
        "universe_min_quality_score": 6.5,
        "universe_eviction_threshold": 4.0,
        "universe_max_active_tickers": 8,
        "universe_max_candidate_tickers": 5,  # test with 5 for brevity
        "pyramid_screener_enabled": False,     # test without pyramid dependency
    }.get(k, default)

    return repo, market, quality_gate, settings


@pytest.mark.asyncio
async def test_evolve_candidate_pool_prunes_weak_and_retains_strong(mock_lifecycle_deps):
    repo, market, quality_gate, settings = mock_lifecycle_deps

    # 2 active tickers: A1, A2
    repo.get_all.side_effect = lambda uid, status: {
        "active": [{"ticker": "A1", "status": "active"}, {"ticker": "A2", "status": "active"}],
        "candidate": [
            {"ticker": "OLD1", "status": "candidate"},
            {"ticker": "OLD2", "status": "candidate"},
            {"ticker": "WEAK", "status": "candidate"},
        ],
    }.get(status, [])

    repo.upsert.return_value = True
    repo.remove.return_value = True
    repo.add_log.return_value = True

    market.get_financials.return_value = {
        "shortName": "Test Corp",
        "sector": "Technology",
        "industry": "Software",
    }
    market.get_etf_holdings.return_value = []

    def make_assessment(ticker, score, hard_gates=True):
        return QualityAssessment(
            ticker=ticker,
            passed=score >= 6.5,
            overall_score=score,
            hard_gates_passed=hard_gates,
            hard_gate_details={},
            fundamental_score=score,
            technical_score=score,
            liquidity_score=score,
            reasons=[],
            metrics={},
        )

    # Candidate contender scores:
    # Top 5 should be: C1(9.5), C2(9.0), OLD1(8.5), C3(8.0), OLD2(7.5)
    # Excluded:
    # A1(9.9 - already active)
    # WEAK(3.0 - scored low, pushed outside top 5)
    # PENNY(6.0 - failed hard gate)
    eval_map = {
        "C1": make_assessment("C1", 9.5),
        "C2": make_assessment("C2", 9.0),
        "OLD1": make_assessment("OLD1", 8.5),
        "C3": make_assessment("C3", 8.0),
        "OLD2": make_assessment("OLD2", 7.5),
        "WEAK": make_assessment("WEAK", 3.0),
        "PENNY": make_assessment("PENNY", 6.0, hard_gates=False),
        "A1": make_assessment("A1", 9.9),
    }

    quality_gate.evaluate_ticker = AsyncMock(
        side_effect=lambda t: eval_map.get(t, make_assessment(t, 5.0))
    )

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )

        res = await service.evolve_candidate_pool(
            max_candidates=5,
            candidate_pool=["C1", "C2", "C3", "PENNY", "WEAK"]
        )

        assert res["success"] is True
        assert res["candidate_count"] == 5
        assert len(res["top_candidates"]) == 5

        # Verify winners are top 5
        winner_tickers = [c["ticker"] for c in res["top_candidates"]]
        assert winner_tickers == ["C1", "C2", "OLD1", "C3", "OLD2"]

        # WEAK was in DB candidates, but fell outside top 5 -> pruned
        assert "WEAK" in res["pruned"]
        repo.remove.assert_called_with("test-user", "WEAK", reason="Pruned from candidate pool: ranked outside top 5")

        # PENNY broke hard gates -> not in winners
        assert "PENNY" not in winner_tickers


@pytest.mark.asyncio
async def test_run_lifecycle_cycle_active_pool_full_evolves_candidates(mock_lifecycle_deps):
    repo, market, quality_gate, settings = mock_lifecycle_deps

    # 8 active tickers in DB (full capacity)
    active_tickers = [f"ACT_{i}" for i in range(8)]
    repo.get_all.side_effect = lambda uid, status: {
        "active": [{"ticker": t, "status": "active"} for t in active_tickers],
        "candidate": [{"ticker": f"CAND_{i}", "status": "candidate"} for i in range(3)],
    }.get(status, [])

    repo.upsert.return_value = True
    repo.remove.return_value = True
    repo.add_log.return_value = True

    market.get_financials.return_value = {"shortName": "Corp", "sector": "Tech"}
    market.get_etf_holdings.return_value = []

    def make_assessment(ticker, score):
        return QualityAssessment(
            ticker=ticker,
            passed=score >= 6.5,
            overall_score=score,
            hard_gates_passed=True,
            hard_gate_details={},
            fundamental_score=score,
            technical_score=score,
            liquidity_score=score,
            reasons=[],
            metrics={},
        )

    # Active tickers all score 7.0 (> 4.0 eviction threshold) -> none evicted
    quality_gate.evaluate_ticker = AsyncMock(
        side_effect=lambda t: make_assessment(t, 7.0)
    )

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )

        service.detect_macro_regime = AsyncMock(
            return_value=MacroRegime(
                regime="BULL_GROWTH",
                vix=16.0,
                yield_curve_inverted=False,
                spy_above_200sma=True,
                quality_score_adjustment=0.0,
                summary="Bull growth",
            )
        )

        res = await service.run_lifecycle_cycle(force=True)

        assert res["success"] is True
        # Active pool remains full (8/8), no evictions, no admissions
        assert len(res["evicted"]) == 0
        assert len(res["admitted"]) == 0
        assert res["active_count"] == 8

        # Candidate evolution succeeded
        assert "candidate_evolution" in res
        assert res["candidate_evolution"]["success"] is True


@pytest.mark.asyncio
async def test_pinned_active_ticker_never_evicted(mock_lifecycle_deps):
    """Pinned active tickers must never be evicted even if quality score degrades below eviction threshold."""
    repo, market, quality_gate, settings = mock_lifecycle_deps

    repo.get_all.return_value = [
        {"ticker": "PINNED_LOW", "status": "active", "is_pinned": True},
        {"ticker": "UNPINNED_LOW", "status": "active", "is_pinned": False},
        {"ticker": "UNPINNED_OK", "status": "active", "is_pinned": False},
    ]
    repo.remove.return_value = True
    repo.add_log.return_value = True

    def make_assessment(ticker, score):
        return QualityAssessment(
            ticker=ticker,
            passed=score >= 6.5,
            overall_score=score,
            hard_gates_passed=True,
            hard_gate_details={},
            fundamental_score=score,
            technical_score=score,
            liquidity_score=score,
            reasons=[],
            metrics={},
        )

    # PINNED_LOW has degraded score 2.5 (< 4.0), UNPINNED_LOW has score 3.0 (< 4.0), UNPINNED_OK has 7.5
    eval_map = {
        "PINNED_LOW": make_assessment("PINNED_LOW", 2.5),
        "UNPINNED_LOW": make_assessment("UNPINNED_LOW", 3.0),
        "UNPINNED_OK": make_assessment("UNPINNED_OK", 7.5),
    }
    quality_gate.evaluate_ticker = AsyncMock(side_effect=lambda t: eval_map[t])

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )

        evicted = await service.review_and_evict_active_tickers(eviction_threshold=4.0)

        # UNPINNED_LOW should be evicted
        evicted_tickers = [e["ticker"] for e in evicted]
        assert "UNPINNED_LOW" in evicted_tickers

        # PINNED_LOW must NOT be evicted because is_pinned=True!
        assert "PINNED_LOW" not in evicted_tickers
        assert "UNPINNED_OK" not in evicted_tickers
        repo.remove.assert_called_once()
        assert repo.remove.call_args[0][1] == "UNPINNED_LOW"


@pytest.mark.asyncio
async def test_pinned_candidate_never_pruned(mock_lifecycle_deps):
    """Pinned candidate tickers must never be pruned even if they rank outside Top N."""
    repo, market, quality_gate, settings = mock_lifecycle_deps

    repo.get_all.side_effect = lambda uid, status: {
        "active": [],
        "candidate": [
            {"ticker": "PINNED_WEAK", "status": "candidate", "is_pinned": True},
            {"ticker": "UNPINNED_WEAK", "status": "candidate", "is_pinned": False},
        ],
    }.get(status, [])
    repo.upsert.return_value = True
    repo.remove.return_value = True
    repo.add_log.return_value = True
    market.get_financials.return_value = {"shortName": "Test"}
    market.get_etf_holdings.return_value = []

    def make_assessment(ticker, score):
        return QualityAssessment(
            ticker=ticker,
            passed=score >= 6.5,
            overall_score=score,
            hard_gates_passed=True,
            hard_gate_details={},
            fundamental_score=score,
            technical_score=score,
            liquidity_score=score,
            reasons=[],
            metrics={},
        )

    # 3 elite contenders score high (9.0, 8.5, 8.0)
    # PINNED_WEAK (2.0) and UNPINNED_WEAK (2.5) both fall outside Top 3
    eval_map = {
        "ELITE1": make_assessment("ELITE1", 9.0),
        "ELITE2": make_assessment("ELITE2", 8.5),
        "ELITE3": make_assessment("ELITE3", 8.0),
        "PINNED_WEAK": make_assessment("PINNED_WEAK", 2.0),
        "UNPINNED_WEAK": make_assessment("UNPINNED_WEAK", 2.5),
    }
    quality_gate.evaluate_ticker = AsyncMock(side_effect=lambda t: eval_map.get(t, make_assessment(t, 5.0)))

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )

        res = await service.evolve_candidate_pool(
            max_candidates=3,
            candidate_pool=["ELITE1", "ELITE2", "ELITE3"]
        )

        assert res["success"] is True
        # UNPINNED_WEAK should be pruned
        assert "UNPINNED_WEAK" in res["pruned"]
        # PINNED_WEAK must NOT be pruned!
        assert "PINNED_WEAK" not in res["pruned"]


@pytest.mark.asyncio
async def test_evolve_active_pool_rotates_unpinned_when_outclassed(mock_lifecycle_deps):
    """Competitive rotation: unpinned active with score 5.0 is outclassed by candidate with score 8.8 (hurdle 1.5)."""
    repo, market, quality_gate, settings = mock_lifecycle_deps

    repo.get_all.side_effect = lambda uid, status: {
        "active": [
            {"ticker": "WEAK_ACT", "status": "active", "is_pinned": False},
            {"ticker": "STRONG_ACT", "status": "active", "is_pinned": False},
        ],
        "candidate": [
            {"ticker": "SUPER_CAND", "status": "candidate", "is_pinned": False},
        ],
    }.get(status, [])
    repo.upsert.return_value = True
    repo.add_log.return_value = True
    market.get_financials.return_value = {"shortName": "Super Corp", "sector": "Tech"}

    def make_assessment(ticker, score):
        return QualityAssessment(
            ticker=ticker,
            passed=score >= 6.5,
            overall_score=score,
            hard_gates_passed=True,
            hard_gate_details={},
            fundamental_score=score,
            technical_score=score,
            liquidity_score=score,
            reasons=[],
            metrics={},
        )

    # WEAK_ACT: 5.0, STRONG_ACT: 8.0, SUPER_CAND: 8.8
    # Difference: 8.8 - 5.0 = 3.8 >= hurdle (1.5) -> rotation triggered!
    eval_map = {
        "WEAK_ACT": make_assessment("WEAK_ACT", 5.0),
        "STRONG_ACT": make_assessment("STRONG_ACT", 8.0),
        "SUPER_CAND": make_assessment("SUPER_CAND", 8.8),
    }
    quality_gate.evaluate_ticker = AsyncMock(side_effect=lambda t: eval_map.get(t, make_assessment(t, 5.0)))

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )

        res = await service.evolve_active_pool(max_active=2, rotation_hurdle=1.5, max_rotations=1)

        assert res["success"] is True
        assert res["rotation_count"] == 1
        rotation = res["rotations"][0]
        assert rotation["demoted_ticker"] == "WEAK_ACT"
        assert rotation["promoted_ticker"] == "SUPER_CAND"
        assert rotation["score_delta"] == 3.8

        # Verify upsert was called to demote WEAK_ACT to candidate and promote SUPER_CAND to active
        repo.upsert.assert_any_call("test-user", "WEAK_ACT", status="candidate")
        repo.upsert.assert_any_call(
            "test-user", "SUPER_CAND",
            company_name="Super Corp",
            sector="Tech",
            industry="",
            status="active"
        )


@pytest.mark.asyncio
async def test_evolve_active_pool_respects_pinned_immunity(mock_lifecycle_deps):
    """When active ticker is pinned (is_pinned=True), it is immune to rotation even if candidate score is much higher."""
    repo, market, quality_gate, settings = mock_lifecycle_deps

    repo.get_all.side_effect = lambda uid, status: {
        "active": [
            {"ticker": "PINNED_ACT", "status": "active", "is_pinned": True},
        ],
        "candidate": [
            {"ticker": "SUPER_CAND", "status": "candidate", "is_pinned": False},
        ],
    }.get(status, [])
    repo.upsert.return_value = True

    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        service = UniverseLifecycleService(
            user_id="test-user",
            repo=repo,
            market=market,
            quality_gate=quality_gate,
        )

        res = await service.evolve_active_pool(max_active=1, rotation_hurdle=1.5, max_rotations=1)

        assert res["success"] is True
        assert res["rotation_count"] == 0
        assert res["pinned_active_count"] == 1
        assert res["unpinned_active_count"] == 0
        # No rotations occurred because all active are pinned
        assert len(res["rotations"]) == 0

