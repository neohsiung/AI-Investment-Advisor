"""
Research freshness + data-outage guards (2026-10 audit):
- fundamentals merged across providers; missing fundamentals never become a fake 4.0 score
- candidate pool is not wiped when most evaluations fail
- research refresh writes fresh rows and skips (never fabricates) data-less tickers
- optimizer uses the newest research and ignores stale rows
研究分數新鮮度與資料中斷防護測試。
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.quality_gate_service import QualityAssessment, QualityGateService
from src.services.universe_lifecycle_service import UniverseLifecycleService


def _assessment(ticker, score=7.0, insufficient=False, fundamentals=True, hard=True):
    return QualityAssessment(
        ticker=ticker, passed=score >= 6.5, overall_score=score, hard_gates_passed=hard,
        hard_gate_details={}, fundamental_score=score, technical_score=score, liquidity_score=score,
        reasons=["r"], metrics={}, _insufficient_data=insufficient, fundamentals_available=fundamentals,
    )


# ── market data: merge fundamentals ──────────────────────────────────────────
def test_get_financials_merges_providers_until_fundamentals_present():
    from src.services.market_data_service import MarketDataService

    svc = MarketDataService.__new__(MarketDataService)
    svc.logger = MagicMock()
    ref = MagicMock(); ref.fetch_info.return_value = {"market_cap": 5e12, "sector": "3674"}
    yf = MagicMock(); yf.fetch_info.return_value = {"market_cap": 4e12, "returnOnEquity": 0.3, "debtToEquity": 40.0,
                                                      "operatingMargins": 0.4, "sector": "Technology"}
    svc._chain = lambda cap: [ref, yf]
    svc._is_provider_enabled = lambda p: True
    svc._get_provider_name = lambda p: "p"
    out = svc.get_financials("NVDA")
    assert out["market_cap"] == 5e12          # first provider wins shared keys
    assert out["sector"] == "3674"
    assert out["returnOnEquity"] == 0.3       # later provider fills the gap


def test_get_financials_empty_when_no_market_cap():
    from src.services.market_data_service import MarketDataService

    svc = MarketDataService.__new__(MarketDataService)
    svc.logger = MagicMock()
    p = MagicMock(); p.fetch_info.return_value = {"sector": "x"}
    svc._chain = lambda cap: [p]
    svc._is_provider_enabled = lambda p: True
    svc._get_provider_name = lambda p: "p"
    assert svc.get_financials("X") == {}


# ── quality gate: no fake fundamentals ───────────────────────────────────────
@pytest.mark.asyncio
async def test_quality_gate_marks_missing_fundamentals():
    market = MagicMock()
    market.get_financials.return_value = {"market_cap": 3e12, "currentPrice": 100.0}
    market.get_technical_indicators.return_value = {
        "rsi": 55.0, "macd": "bullish", "sma": {"sma_50": 95.0, "sma_200": 90.0},
        "volume": {"avg_20": 50_000_000},
    }
    with patch("src.services.quality_gate_service.SettingsService") as sc:
        sc.return_value.get_setting.side_effect = lambda k, d=None: None
        svc = QualityGateService(user_id="u", market_data_service=market)
        a = await svc.evaluate_ticker("ZZZ")
    assert a.fundamentals_available is False
    assert a._fallback_reason == "fundamentals_unavailable"
    # composite must not include the defaulted fundamental score
    expected = round((0.35 * a.technical_score + 0.20 * a.liquidity_score) / 0.55, 2)
    assert a.overall_score == expected


# ── lifecycle: outage guard + refresh ────────────────────────────────────────
def _lifecycle(repo, quality_gate):
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "universe_max_candidate_tickers": 5, "pyramid_screener_enabled": False,
    }.get(k, default)
    market = MagicMock()
    market.get_financials.return_value = {"shortName": "T", "sector": "Tech", "industry": "I"}
    market.get_etf_holdings.return_value = []
    with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
        return UniverseLifecycleService(user_id="u", repo=repo, market=market, quality_gate=quality_gate)


@pytest.mark.asyncio
async def test_candidate_pool_not_pruned_during_data_outage():
    repo = MagicMock()
    repo.get_all.side_effect = lambda uid, status: {
        "active": [],
        "candidate": [{"ticker": f"OLD{i}", "status": "candidate"} for i in range(4)],
    }.get(status, [])
    repo.upsert.return_value = True
    qg = MagicMock()
    # every evaluation fails -> zero valid assessments
    qg.evaluate_ticker = AsyncMock(side_effect=RuntimeError("provider down"))
    svc = _lifecycle(repo, qg)
    res = await svc.evolve_candidate_pool(max_candidates=5, candidate_pool=["N1", "N2"])
    assert res["prune_skipped_data_outage"] is True
    assert res["pruned_count"] == 0
    repo.remove.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_research_scores_writes_fresh_rows_and_skips_no_data():
    repo = MagicMock()
    repo.get_all.side_effect = lambda uid, status: {
        "active": [{"ticker": "AAA"}, {"ticker": "BBB"}],
        "candidate": [{"ticker": "CCC"}],
    }.get(status, [])
    repo.add_research.return_value = True
    qg = MagicMock()
    qg.evaluate_ticker = AsyncMock(side_effect=lambda t: {
        "AAA": _assessment("AAA", 7.2),
        "BBB": _assessment("BBB", 0.0, insufficient=True),
        "CCC": _assessment("CCC", 6.0, fundamentals=False),
    }[t])
    svc = _lifecycle(repo, qg)
    res = await svc.refresh_research_scores()
    assert [r["ticker"] for r in res["refreshed"]] == ["AAA", "CCC"]
    assert res["skipped"] == [{"ticker": "BBB", "reason": "insufficient_data"}]
    first = repo.add_research.call_args_list[0]
    assert first.args[1] == "AAA" and first.args[4] == 0.72
    assert first.kwargs["expected_return"] is None
    assert repo.add_research.call_count == 2


# ── optimizer: newest research wins, stale ignored ───────────────────────────
def _optimizer_scores(research_rows, max_age=14):
    from src.services.ticker_universe_service import TickerUniverseService

    svc = TickerUniverseService.__new__(TickerUniverseService)
    svc.user_id = "u"
    svc.repo = MagicMock()
    svc.repo.get_all.return_value = [{"ticker": "AAA", "volatility_60d": 0.2, "beta_60d": 1.0, "sector": "T"}]
    svc.repo.get_research.return_value = research_rows
    svc._settings = MagicMock()
    svc._settings.get_setting.side_effect = lambda k, d=None: {
        "universe_research_max_age_days": max_age, "alloc_min_position": 0.03, "alloc_max_position": 0.2,
        "alloc_sector_cap": 0.4, "alloc_target_sum": 0.9,
    }.get(k, d)
    svc.calculate_ticker_returns = lambda *a, **k: [0.001] * 60
    svc.repo.clear_targets = MagicMock()
    svc.repo.add_log = MagicMock()
    captured = {}
    svc.repo.upsert_target.side_effect = lambda uid, t, **kw: captured.update({t: kw})
    svc.optimize_allocations()
    return captured


def test_optimizer_uses_newest_research_not_max_of_history():
    now = datetime.now(timezone.utc)
    rows = [
        {"confidence_score": 0.55, "expected_return": None, "created_at": now - timedelta(days=1)},
        {"confidence_score": 0.90, "expected_return": 0.15, "created_at": now - timedelta(days=30)},
    ]
    out = _optimizer_scores(rows)
    assert out["AAA"]["confidence_score"] == 0.55


def test_optimizer_treats_stale_research_as_unresearched():
    old = datetime.now(timezone.utc) - timedelta(days=40)
    out = _optimizer_scores([{"confidence_score": 0.90, "expected_return": 0.15, "created_at": old}])
    assert out["AAA"]["confidence_score"] == 0.5


@pytest.mark.asyncio
async def test_evaluation_crash_is_marked_insufficient_and_never_evicts():
    market = MagicMock()
    market.get_financials.side_effect = RuntimeError("settings schema unreadable")
    with patch("src.services.quality_gate_service.SettingsService") as sc:
        sc.return_value.get_setting.side_effect = lambda k, d=None: None
        qg = QualityGateService(user_id="u", market_data_service=market)
        a = await qg.evaluate_ticker("AAPL")
    assert a._insufficient_data is True and a.overall_score == 0.0

    repo = MagicMock()
    repo.get_all.side_effect = lambda uid, status: {"active": [{"ticker": "AAPL", "is_pinned": False}]}.get(status, [])
    qg_mock = MagicMock()
    qg_mock.evaluate_ticker = AsyncMock(return_value=a)
    svc = _lifecycle(repo, qg_mock)
    evicted = await svc.review_and_evict_active_tickers()
    assert evicted == []
    repo.remove.assert_not_called()
