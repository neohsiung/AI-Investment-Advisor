"""G1: threshold band recorder — every signal near a threshold, passed or rejected, with the score and the
threshold in force. Recording only; never touches a decision or an order.
G1：門檻帶紀錄器——每個靠近門檻的訊號（通過或被拒）都記下分數與當時門檻；只記錄，不影響決策或下單。"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.services import threshold_band_recorder as tbr

DDL = [
    """CREATE TABLE threshold_band_observations (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, threshold_key TEXT NOT NULL,
        source_service TEXT NOT NULL, ticker TEXT NOT NULL, direction TEXT NOT NULL,
        obs_date DATE NOT NULL, score NUMERIC, threshold_value NUMERIC NOT NULL, margin NUMERIC,
        passed BOOLEAN, in_band BOOLEAN NOT NULL, price NUMERIC, data_marker TEXT, context TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, threshold_key, source_service, ticker, direction, obs_date))""",
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


def _price(value):
    async def lookup(ticker):
        return value
    return lookup


# ── pure helper ───────────────────────────────────────────────────────────────

def test_observation_passed_and_rejected_carry_margin_and_threshold():
    ok = tbr.build_observation(ticker="a", direction="buy", score=6.0, threshold=5.5)
    no = tbr.build_observation(ticker="B", direction="BUY", score=5.0, threshold=5.5)
    assert (ok.ticker, ok.direction, ok.passed, ok.margin, ok.threshold) == ("A", "BUY", True, 0.5, 5.5)
    assert (no.passed, no.margin, no.in_band) == (False, -0.5, True)


def test_score_equal_to_threshold_passes_like_the_deciders_do():
    assert tbr.build_observation(ticker="A", direction="BUY", score=5.5, threshold=5.5).passed is True


@pytest.mark.parametrize("bad", [None, "x", float("nan"), float("inf")])
def test_missing_or_garbage_score_is_marked_never_defaulted(bad):
    o = tbr.build_observation(ticker="A", direction="BUY", score=bad, threshold=5.5)
    assert o.score is None and o.passed is None and o.margin is None
    assert o.data_marker == tbr.MARKER_NO_SCORE


def test_far_from_threshold_is_outside_the_band():
    far = tbr.build_observation(ticker="A", direction="BUY", score=9.9, threshold=5.5)
    near = tbr.build_observation(ticker="A", direction="BUY", score=5.5 + tbr.BAND_HALFWIDTH, threshold=5.5)
    assert far.in_band is False and near.in_band is True


# ── writer ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_passing_signal_also_gets_counterfactual_row(engine):
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=6.0, threshold=5.5)]
    stats = await tbr.record_band_observations(engine, "u1", "batch_deploy_min_confidence", "batch_deploy",
                                               obs, _price(50.0))
    (o,) = _rows(engine, "threshold_band_observations")
    assert bool(o["passed"]) is True and float(o["score"]) == 6.0 and float(o["threshold_value"]) == 5.5
    assert o["threshold_key"] == "batch_deploy_min_confidence" and o["data_marker"] is None
    cf = _rows(engine, "decision_outcomes")
    assert sorted(r["horizon_days"] for r in cf) == [5, 63]
    for r in cf:
        assert bool(r["is_counterfactual"]) is True and r["agent_name"] == tbr.COUNTERFACTUAL_AGENT
        assert (r["signal"], r["ticker"], float(r["price_at_decision"])) == ("BUY", "AAA", 50.0)
        assert r["proposal_id"] == o["id"] and r["source"] == tbr.OUTCOME_SOURCE
    assert (stats.recorded, stats.missing_price) == (1, 0)


@pytest.mark.anyio
async def test_rejected_signal_also_recorded_with_its_threshold(engine):
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=5.0, threshold=5.5)]
    await tbr.record_band_observations(engine, "u1", "batch_deploy_min_confidence", "batch_deploy",
                                       obs, _price(50.0))
    (o,) = _rows(engine, "threshold_band_observations")
    assert bool(o["passed"]) is False and float(o["margin"]) == -0.5
    assert len(_rows(engine, "decision_outcomes")) == 2


@pytest.mark.anyio
async def test_missing_price_row_is_marked_and_counted(engine):
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=6.0, threshold=5.5),
           tbr.build_observation(ticker="BBB", direction="BUY", score=5.2, threshold=5.5)]
    with patch.object(tbr, "logger") as log:
        stats = await tbr.record_band_observations(engine, "u1", "k", "batch_deploy", obs, _price(None))
    rows = _rows(engine, "threshold_band_observations")
    assert len(rows) == 2 and all(r["data_marker"] == tbr.MARKER_NO_PRICE and r["price"] is None for r in rows)
    assert _rows(engine, "decision_outcomes") == []
    assert (stats.recorded, stats.missing_price) == (2, 2)
    assert log.warning.called


@pytest.mark.anyio
async def test_price_lookup_error_is_marked_not_defaulted(engine):
    async def boom(ticker):
        raise RuntimeError("feed down")

    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=6.0, threshold=5.5)]
    stats = await tbr.record_band_observations(engine, "u1", "k", "batch_deploy", obs, boom)
    (o,) = _rows(engine, "threshold_band_observations")
    assert o["data_marker"] == tbr.MARKER_NO_PRICE and stats.missing_price == 1


@pytest.mark.anyio
async def test_missing_score_row_is_marked_counted_and_has_no_outcome(engine):
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=None, threshold=5.5)]
    stats = await tbr.record_band_observations(engine, "u1", "k", "batch_deploy", obs, _price(50.0))
    (o,) = _rows(engine, "threshold_band_observations")
    assert o["data_marker"] == tbr.MARKER_NO_SCORE and o["score"] is None and o["passed"] is None
    assert _rows(engine, "decision_outcomes") == [] and stats.missing_score == 1


@pytest.mark.anyio
async def test_out_of_band_observation_is_not_recorded(engine):
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=9.9, threshold=5.5)]
    stats = await tbr.record_band_observations(engine, "u1", "k", "batch_deploy", obs, _price(50.0))
    assert _rows(engine, "threshold_band_observations") == [] and stats.recorded == 0


@pytest.mark.anyio
async def test_same_day_repeat_is_idempotent_no_duplicate_outcomes(engine):
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=6.0, threshold=5.5)]
    for _ in range(2):
        await tbr.record_band_observations(engine, "u1", "k", "batch_deploy", obs, _price(50.0))
    assert len(_rows(engine, "threshold_band_observations")) == 1
    assert len(_rows(engine, "decision_outcomes")) == 2


@pytest.mark.anyio
async def test_context_is_stored_as_json(engine):
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=6.0, threshold=5.5, context={"gap": 12.5})]
    await tbr.record_band_observations(engine, "u1", "k", "batch_deploy", obs, _price(50.0))
    (o,) = _rows(engine, "threshold_band_observations")
    assert json.loads(o["context"]) == {"gap": 12.5}


@pytest.mark.anyio
async def test_unwritable_db_raises_instead_of_pretending(engine):
    with engine.begin() as c:
        c.execute(text("DROP TABLE threshold_band_observations"))
    obs = [tbr.build_observation(ticker="AAA", direction="BUY", score=6.0, threshold=5.5)]
    with pytest.raises(Exception):
        await tbr.record_band_observations(engine, "u1", "k", "batch_deploy", obs, _price(50.0))


def test_recorder_never_changes_decision():
    """rank_candidates returns identical output with and without an observer. / 有無觀察者輸出相同。"""
    from src.services.batch_cash_deployment_service import BatchCashDeploymentService as B
    targets = [{"ticker": "A", "target_weight": 0.1, "confidence_score": 0.60},
               {"ticker": "B", "target_weight": 0.1, "confidence_score": 0.50},
               {"ticker": "C", "target_weight": 0.2, "confidence_score": 0.80}]
    args = (targets, {"A", "B", "C"}, {}, 1000.0, 100.0, 3, 5.5)
    seen = []
    plain = B.rank_candidates(*args)
    observed = B.rank_candidates(*args, observer=lambda sym, conf, passed: seen.append((sym, conf, passed)))
    assert plain == observed
    assert sorted(seen) == [("A", 6.0, True), ("B", 5.0, False), ("C", 8.0, True)]
