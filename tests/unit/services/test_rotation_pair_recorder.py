"""G1b: rotation pair recorder — one record per rotation decision linking the sell leg and the buy leg, with the
score gap, holding age, thresholds in force and the friction assumption. Recording only.
G1b：換庫配對紀錄器——每次換庫決策一筆，連結賣出腿與買進腿，附分數差、持有天數、當時門檻與摩擦假設；只記錄。"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.services import rotation_pair_recorder as rpr

DDL = [
    """CREATE TABLE rotation_pair_observations (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, obs_date DATE NOT NULL, sell_ticker TEXT NOT NULL,
        buy_ticker TEXT NOT NULL, decision TEXT NOT NULL, holding_score NUMERIC, candidate_score NUMERIC,
        score_delta NUMERIC, holding_age_days NUMERIC, min_score_delta NUMERIC NOT NULL,
        min_holding_days NUMERIC NOT NULL, friction_pct NUMERIC, sell_price NUMERIC, buy_price NUMERIC,
        data_marker TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, sell_ticker, buy_ticker, obs_date, decision))""",
    """CREATE TABLE decision_outcomes (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT, agent_name TEXT NOT NULL,
        ticker TEXT NOT NULL, signal TEXT NOT NULL, price_at_decision NUMERIC NOT NULL,
        decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, horizon_days INTEGER NOT NULL DEFAULT 5,
        resolved_at TIMESTAMP, proposal_id TEXT, strategy_id TEXT, source TEXT,
        is_counterfactual BOOLEAN NOT NULL DEFAULT 0)""",
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with eng.begin() as c:
        for stmt in DDL:
            c.execute(text(stmt))
    return eng


def _rows(engine, table):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(f"SELECT * FROM {table}")).mappings()]


def _prices(**p):
    async def lookup(ticker):
        return p.get(ticker)
    return lookup


def _pair(**over):
    kw = dict(sell_ticker="old", buy_ticker="new", holding_score=5.0, candidate_score=7.6, holding_age_days=9.0,
              min_score_delta=2.0, min_holding_days=5.0, friction_pct=1.0, decision=rpr.DECISION_APPROVED)
    kw.update(over)
    return rpr.build_pair(**kw)


# ── pure ──────────────────────────────────────────────────────────────────────

def test_build_pair_computes_gap_and_normalises_tickers():
    p = _pair()
    assert (p.sell_ticker, p.buy_ticker, p.score_delta, p.data_marker) == ("OLD", "NEW", 2.6, None)


@pytest.mark.parametrize("field,marker", [("holding_score", "score"), ("candidate_score", "score"),
                                          ("holding_age_days", "age"), ("friction_pct", "friction")])
def test_missing_inputs_are_marked_never_defaulted(field, marker):
    p = _pair(**{field: None})
    assert p.data_marker == f"_insufficient_data:{marker}"
    assert getattr(p, field) is None


# ── writer ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_rotation_pair_record_links_both_legs(engine):
    stats = await rpr.record_rotation_pair(engine, "u1", _pair(), _prices(OLD=100.0, NEW=50.0))
    (r,) = _rows(engine, "rotation_pair_observations")
    assert (r["sell_ticker"], r["buy_ticker"], r["decision"]) == ("OLD", "NEW", "swap_approved")
    assert float(r["score_delta"]) == pytest.approx(2.6) and float(r["holding_age_days"]) == 9.0
    assert (float(r["min_score_delta"]), float(r["min_holding_days"]), float(r["friction_pct"])) == (2.0, 5.0, 1.0)
    assert (float(r["sell_price"]), float(r["buy_price"]), r["data_marker"]) == (100.0, 50.0, None)
    legs = _rows(engine, "decision_outcomes")
    assert sorted((x["signal"], x["ticker"], x["horizon_days"]) for x in legs) == [
        ("BUY", "NEW", 5), ("BUY", "NEW", 63), ("SELL", "OLD", 5), ("SELL", "OLD", 63)]
    assert all(x["proposal_id"] == r["id"] and x["source"] == rpr.OUTCOME_SOURCE and bool(x["is_counterfactual"])
               for x in legs)
    assert stats.recorded == 1 and stats.missing_price == 0


@pytest.mark.anyio
async def test_rotation_near_threshold_rejection_also_recorded(engine):
    p = _pair(candidate_score=6.9, decision=rpr.DECISION_REJECTED_DELTA)
    await rpr.record_rotation_pair(engine, "u1", p, _prices(OLD=100.0, NEW=50.0))
    (r,) = _rows(engine, "rotation_pair_observations")
    assert r["decision"] == "swap_rejected_delta" and float(r["score_delta"]) == pytest.approx(1.9)
    assert len(_rows(engine, "decision_outcomes")) == 4


@pytest.mark.anyio
@pytest.mark.parametrize("prices", [{"OLD": 100.0}, {"NEW": 50.0}, {}])
async def test_pair_missing_price_marked(engine, prices):
    with patch.object(rpr, "logger") as log:
        stats = await rpr.record_rotation_pair(engine, "u1", _pair(), _prices(**prices))
    (r,) = _rows(engine, "rotation_pair_observations")
    assert r["data_marker"].startswith("_insufficient_data:price")
    assert _rows(engine, "decision_outcomes") == []
    assert stats.missing_price == 1 and log.warning.called


@pytest.mark.anyio
async def test_price_lookup_error_is_marked(engine):
    async def boom(ticker):
        raise RuntimeError("feed down")
    stats = await rpr.record_rotation_pair(engine, "u1", _pair(), boom)
    (r,) = _rows(engine, "rotation_pair_observations")
    assert r["data_marker"].startswith("_insufficient_data:price") and stats.missing_price == 1


@pytest.mark.anyio
async def test_same_day_repeat_is_idempotent(engine):
    for _ in range(2):
        await rpr.record_rotation_pair(engine, "u1", _pair(), _prices(OLD=100.0, NEW=50.0))
    assert len(_rows(engine, "rotation_pair_observations")) == 1
    assert len(_rows(engine, "decision_outcomes")) == 4


@pytest.mark.anyio
async def test_friction_is_read_from_the_setting_not_hardcoded(engine):
    svc = MagicMock()
    svc.get_setting.side_effect = lambda k, d=None, u=None: {"rotation_roundtrip_friction_pct": 1.7}.get(k, d)
    assert rpr.read_friction_pct(svc) == 1.7
    svc.get_setting.side_effect = lambda k, d=None, u=None: None
    assert rpr.read_friction_pct(svc) is None


@pytest.mark.anyio
async def test_boundary_swallows_with_warning_and_returns_none(engine):
    with engine.begin() as c:
        c.execute(text("DROP TABLE rotation_pair_observations"))
    with patch.object(rpr, "logger") as log:
        out = await rpr.record_pairs_at_boundary("u1", [_pair()], engine=engine, price_lookup=_prices(OLD=1.0, NEW=1.0))
    assert out is None and log.warning.called


@pytest.mark.anyio
async def test_young_holdings_blocked_by_min_holding_are_recorded(engine):
    svc = MagicMock()
    svc.get_setting.side_effect = lambda k, d=None, u=None: {"rotation_roundtrip_friction_pct": 1.0}.get(k, d)
    await rpr.record_young_blocked(
        "u1", svc, {"OLD": 2.0}, "NEW", 7.6, lambda t: 5.0, 2.0, 5.0, engine=engine,
        price_lookup=_prices(OLD=100.0, NEW=50.0))
    (r,) = _rows(engine, "rotation_pair_observations")
    assert r["decision"] == "blocked_min_holding" and float(r["holding_age_days"]) == 2.0
    assert float(r["min_holding_days"]) == 5.0 and float(r["friction_pct"]) == 1.0


# ── sentinel wiring: recording never changes the rotation decision ────────────

SETTINGS = {"capital_rotation_enabled": True, "rotation_min_score_delta": 2.0, "autonomous_exit_enabled": True,
            "rotation_min_holding_days": 5, "batch_deploy_max_order_usd": 100.0}


def _sentinel():
    from src.services.sentinel_service import SentinelService
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None, user_id=None: SETTINGS.get(k, default)
    tx = MagicMock()
    tx.get_position_lots.return_value = []
    buf = MagicMock(); buf.try_acquire = AsyncMock(return_value=True)
    repo = MagicMock(); repo.engine = MagicMock(); repo.get_all_thresholds.return_value = {}
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=buf), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        s = SentinelService(user_id="u_rot", repo=repo, market_service=MagicMock(), transaction_service=tx,
                            settings_service=settings, keyword_service=MagicMock())
    s._acquire_cooldown = AsyncMock(return_value=True)
    return s


async def _rotate(age_days, should_swap, recorder_side_effect=None):
    from src.services.unified_risk_gateway_service import RiskGatewayResult, RiskSeverity
    s = _sentinel()
    s.transaction_service.get_transactions.return_value = pd.DataFrame(
        [{"ticker": "GOOGL", "action": "BUY", "trade_date": datetime.now() - timedelta(days=age_days)}])
    s._research_score = lambda t: {"GOOGL": 5.0, "NVDA": 8.0}.get(t)
    holdings = {"GOOGL": {"shares": 0.3, "current_price": 340.0, "avg_price": 340.0, "weight": 5.0}}
    dec = MagicMock(should_swap=should_swap, raw_delta=3.0 if should_swap else 1.9, net_opportunity_delta=2.0,
                    friction_hurdle=1.0, reason="r")
    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
         patch("src.services.exit_compositor_service.ExitCompositorService.score_exit",
               new=AsyncMock(return_value={"composite_score": 4.3, "breakdown": []})), \
         patch("src.services.opportunity_cost_service.OpportunityCostService.evaluate_swap", return_value=dec), \
         patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService.evaluate_trade_risk",
               new=AsyncMock(return_value=RiskGatewayResult(True, RiskSeverity.NORMAL, None, [], {}, "t"))), \
         patch("src.services.sentinel_service.record_rotation_decision",
               new=AsyncMock(side_effect=recorder_side_effect)) as rec, \
         patch("src.services.sentinel_service.record_young_blocked", new=AsyncMock()) as young:
        trig = await s._check_capital_rotation_opportunities(
            current_allocation=holdings, candidates_override=[{"ticker": "NVDA", "composite_score": 8.0}])
    return trig, rec, young


@pytest.mark.asyncio
async def test_sentinel_records_rejected_and_approved_pairs_without_changing_triggers():
    t_ok, rec_ok, _ = await _rotate(10, True)
    t_no, rec_no, _ = await _rotate(10, False)
    assert len(t_ok) == 1 and t_no == []
    assert rec_ok.await_args.args[-1] == rpr.DECISION_APPROVED
    assert rec_no.await_args.args[-1] == rpr.DECISION_REJECTED_DELTA


@pytest.mark.asyncio
async def test_sentinel_passes_young_holdings_to_recorder_and_still_blocks_them():
    trig, rec, young = await _rotate(1, True)
    assert trig == [] and not rec.await_count
    assert young.await_args.args[2] == {"GOOGL": pytest.approx(1.0, abs=0.1)}
