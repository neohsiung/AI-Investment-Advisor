"""Marginal-band evaluator (G5): settled counterfactual rows -> net return series.
邊際區間評估器：已結算反事實列 -> 淨報酬序列。"""
from datetime import date, datetime

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.services import marginal_band_evaluator as mbe

DDL = [
    """CREATE TABLE threshold_band_observations (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, threshold_key TEXT NOT NULL,
        source_service TEXT NOT NULL, ticker TEXT NOT NULL, direction TEXT NOT NULL,
        obs_date DATE NOT NULL, score NUMERIC, threshold_value NUMERIC NOT NULL, margin NUMERIC,
        passed BOOLEAN, in_band BOOLEAN NOT NULL, price NUMERIC, data_marker TEXT, context TEXT)""",
    """CREATE TABLE rotation_pair_observations (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, obs_date DATE NOT NULL, sell_ticker TEXT NOT NULL,
        buy_ticker TEXT NOT NULL, decision TEXT NOT NULL, holding_score NUMERIC, candidate_score NUMERIC,
        score_delta NUMERIC, holding_age_days NUMERIC, min_score_delta NUMERIC NOT NULL,
        min_holding_days NUMERIC NOT NULL, friction_pct NUMERIC, sell_price NUMERIC, buy_price NUMERIC,
        data_marker TEXT)""",
    """CREATE TABLE decision_outcomes (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, agent_name TEXT NOT NULL, ticker TEXT NOT NULL,
        signal TEXT NOT NULL, horizon_days INTEGER NOT NULL DEFAULT 5, resolved_at TIMESTAMP,
        proposal_id TEXT, source TEXT, is_counterfactual BOOLEAN NOT NULL DEFAULT 0,
        realized_return_pct NUMERIC, benchmark_return_pct NUMERIC, alpha_pct NUMERIC)""",
]
UID = "u1"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with eng.begin() as c:
        for stmt in DDL:
            c.execute(text(stmt))
    return eng


def _band_row(engine, oid, score, thr=5.5, signal="BUY", alpha=1.0, obs=date(2026, 9, 1), h=5,
              key="batch_deploy_min_confidence", resolved=True):
    with engine.begin() as c:
        c.execute(text("INSERT INTO threshold_band_observations (id,user_id,threshold_key,source_service,ticker,"
                       "direction,obs_date,score,threshold_value,in_band) VALUES (:i,:u,:k,'s','AAA','BUY',:d,:s,:t,1)"),
                  dict(i=oid, u=UID, k=key, d=obs, s=score, t=thr))
        c.execute(text("INSERT INTO decision_outcomes (id,user_id,agent_name,ticker,signal,horizon_days,resolved_at,"
                       "proposal_id,source,is_counterfactual,alpha_pct) VALUES (:i,:u,'threshold_band','AAA',:sg,:h,"
                       ":r,:p,'threshold_band',1,:a)"),
                  dict(i=f"o-{oid}-{h}", u=UID, sg=signal, h=h, r=datetime(2026, 9, 10) if resolved else None,
                       p=oid, a=alpha))


def _rot_row(engine, rid, delta=3.0, age=10.0, min_delta=2.0, min_hold=5.0, friction=1.0, obs=date(2026, 9, 1),
             buy_ret=4.0, sell_ret=1.0, buy_resolved=True, sell_resolved=True, h=5):
    with engine.begin() as c:
        c.execute(text("INSERT INTO rotation_pair_observations (id,user_id,obs_date,sell_ticker,buy_ticker,decision,"
                       "score_delta,holding_age_days,min_score_delta,min_holding_days,friction_pct) VALUES "
                       "(:i,:u,:d,'SSS','BBB','swap_approved',:sd,:a,:md,:mh,:f)"),
                  dict(i=rid, u=UID, d=obs, sd=delta, a=age, md=min_delta, mh=min_hold, f=friction))
        for sig, tk, ret, ok in (("BUY", "BBB", buy_ret, buy_resolved), ("SELL", "SSS", sell_ret, sell_resolved)):
            c.execute(text("INSERT INTO decision_outcomes (id,user_id,agent_name,ticker,signal,horizon_days,"
                           "resolved_at,proposal_id,source,is_counterfactual,realized_return_pct) VALUES "
                           "(:i,:u,'rotation_pair',:t,:sg,:h,:r,:p,'rotation_pair',1,:ret)"),
                      dict(i=f"o-{rid}-{sig}-{h}", u=UID, t=tk, sg=sig, h=h,
                           r=datetime(2026, 9, 10) if ok else None, p=rid, ret=ret))


def test_in_marginal_band_half_open():
    assert mbe.in_marginal_band(5.5, 5.0, 5.0) is True
    assert mbe.in_marginal_band(5.5, 5.0, 5.5) is False
    assert mbe.in_marginal_band(5.5, 6.0, 5.7) is True


def test_threshold_band_buy_net_subtracts_round_trip_cost(engine):
    _band_row(engine, "a", score=5.2, alpha=1.0)
    out = mbe.evaluate_key(engine, UID, "batch_deploy_min_confidence", 5.5, 5.0)
    assert out[(5, 1.0)].net_returns == pytest.approx([0.008])   # 1.0% - 2*10bps
    assert out[(5, 2.0)].net_returns == pytest.approx([0.006])
    assert out[(5, 1.0)].n == 1 and out[(63, 1.0)].n == 0


def test_sell_sign_applied_for_event_shadow_rows(engine):
    _band_row(engine, "a", score=5.2, signal="SELL", alpha=-2.0, key="batch_deploy_min_confidence")
    s = mbe.evaluate_key(engine, UID, "batch_deploy_min_confidence", 5.5, 5.0)[(5, 1.0)]
    assert s.net_returns == pytest.approx([0.02 - 0.002])


def test_rotation_pair_requires_both_legs_resolved(engine):
    _rot_row(engine, "r1", sell_resolved=False)
    s = mbe.evaluate_key(engine, UID, "rotation_min_score_delta", 2.0, 1.0)[(5, 1.0)]
    assert s.n == 0


def test_rotation_missing_friction_excluded_and_counted(engine):
    _rot_row(engine, "r1", delta=1.5, friction=None)
    s = mbe.evaluate_key(engine, UID, "rotation_min_score_delta", 2.0, 1.0)[(5, 1.0)]
    assert s.n == 0 and s.excluded_missing_friction == 1


def test_rotation_delta_evidence_filters_young_holdings(engine):
    _rot_row(engine, "young", delta=1.5, age=2.0, min_hold=5.0)
    _rot_row(engine, "old", delta=1.5, age=9.0, min_hold=5.0, obs=date(2026, 9, 2))
    s = mbe.evaluate_key(engine, UID, "rotation_min_score_delta", 2.0, 1.0)[(5, 1.0)]
    assert s.n == 1
    assert s.net_returns == pytest.approx([(4.0 - 1.0 - 1.0) / 100.0])   # buy-sell gross minus friction
    s2 = mbe.evaluate_key(engine, UID, "rotation_min_holding_days", 5.0, 1.0)[(5, 1.0)]
    assert s2.n == 0   # delta 1.5 < min_score_delta 2.0 -> swap would not have happened


def test_since_filters_rows_before_evidence_clock(engine):
    _band_row(engine, "old", score=5.2, obs=date(2026, 8, 1))
    _band_row(engine, "new", score=5.2, obs=date(2026, 9, 5))
    s = mbe.evaluate_key(engine, UID, "batch_deploy_min_confidence", 5.5, 5.0,
                         since=datetime(2026, 9, 1))[(5, 1.0)]
    assert s.n == 1


def test_unknown_key_marked_unavailable_not_empty(engine):
    out = mbe.evaluate_key(engine, UID, "event_analysis_daily_cap", 10.0, 12.0)
    assert out and all(v.unavailable_reason == "no_recorder_for_key" for v in out.values())


def test_daily_zero_filled_skips_weekends_and_averages_same_day():
    # Fri 09-04 (two rows, averaged), Mon 09-07 empty -> 0 (weekend skipped), Tue 09-08
    arr = mbe.daily_zero_filled([(date(2026, 9, 4), 0.02), (date(2026, 9, 4), 0.04), (date(2026, 9, 8), 0.01)])
    assert arr.tolist() == pytest.approx([0.03, 0.0, 0.01])


def test_sigma_upper_has_floor():
    assert mbe.sigma_upper(np.array([0.0, 0.0, 0.0])) == mbe.SIGMA_FLOOR
    assert mbe.sigma_upper(np.array([0.001])) == mbe.SIGMA_FLOOR
