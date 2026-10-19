"""G5 on real Postgres: marginal-band evaluation must equal the sqlite run the unit tests cover.
G5 在真實 Postgres：邊際區間評估結果必須與單元測試的 sqlite 結果一致（驗證 psycopg2 下的參數型別）。"""
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.services import marginal_band_evaluator as mbe

from .factories import USER_ID, seed_band_obs, settle

pytestmark = pytest.mark.charter_e2e

KEY = "batch_deploy_min_confidence"
CURRENT, CHALLENGER = 5.5, 5.0
START = date(2026, 6, 1)
N_DATES, PER_DATE = 8, 5

SQLITE_DDL = [
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


def _alpha(i: int, horizon: int) -> float:
    return round(((i * 7) % 11 - 4) * 0.35 + (0.2 if horizon == 63 else 0.0), 4)


def _seed_postgres(engine):
    """40 in-band rows (8 dates x 5 tickers), each settled at 5 and 63 days. / 40 筆帶內列，各結算 5、63 日。"""
    i = 0
    for d in range(N_DATES):
        obs = START + timedelta(days=d)
        rows = []
        for t in range(PER_DATE):
            rows.append((f"T{d}{t}", round(5.0 + 0.49 * ((i * 3) % 10) / 9, 4), CURRENT))
            i += 1
        stats = seed_band_obs(engine, KEY, obs, rows)
        assert stats.recorded == PER_DATE
    with engine.connect() as c:
        pairs = c.execute(text(
            "SELECT o.id, o.obs_date, o.ticker, d.horizon_days FROM threshold_band_observations o "
            "JOIN decision_outcomes d ON d.proposal_id = o.id ORDER BY o.obs_date, o.ticker, d.horizon_days")).fetchall()
    assert len(pairs) == N_DATES * PER_DATE * 2
    order = {f"T{d}{t}": d * PER_DATE + t for d in range(N_DATES) for t in range(PER_DATE)}
    for oid, obs_date, ticker, h in pairs:
        settle(engine, source="threshold_band", horizon_days=h, proposal_id=oid, alpha_pct=_alpha(order[ticker], h),
               realized_return_pct=_alpha(order[ticker], h) + 0.5,
               resolved_at=datetime.combine(obs_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=h),
               decided_at=datetime.combine(obs_date, datetime.min.time(), tzinfo=timezone.utc))


def _mirror_to_sqlite(pg_engine):
    lite = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with lite.begin() as c:
        for stmt in SQLITE_DDL:
            c.execute(text(stmt))
    with pg_engine.connect() as c:
        obs = c.execute(text("SELECT id, user_id, threshold_key, source_service, ticker, direction, obs_date, score, "
                             "threshold_value, in_band FROM threshold_band_observations")).mappings().all()
        outs = c.execute(text("SELECT id, user_id, agent_name, ticker, signal, horizon_days, resolved_at, proposal_id, "
                              "source, alpha_pct, realized_return_pct FROM decision_outcomes")).mappings().all()
    with lite.begin() as c:
        for r in obs:
            c.execute(text("INSERT INTO threshold_band_observations (id,user_id,threshold_key,source_service,ticker,"
                           "direction,obs_date,score,threshold_value,in_band) VALUES "
                           "(:id,:user_id,:threshold_key,:source_service,:ticker,:direction,:obs_date,:score,"
                           ":threshold_value,:in_band)"), {**r, "score": float(r["score"]),
                                                          "threshold_value": float(r["threshold_value"])})
        for r in outs:
            c.execute(text("INSERT INTO decision_outcomes (id,user_id,agent_name,ticker,signal,horizon_days,resolved_at,"
                           "proposal_id,source,is_counterfactual,alpha_pct,realized_return_pct) VALUES "
                           "(:id,:user_id,:agent_name,:ticker,:signal,:horizon_days,:resolved_at,:proposal_id,:source,1,"
                           ":alpha_pct,:realized_return_pct)"),
                      {**r, "resolved_at": r["resolved_at"].replace(tzinfo=None),
                       "alpha_pct": float(r["alpha_pct"]), "realized_return_pct": float(r["realized_return_pct"])})
    return lite


@pytest.mark.parametrize("since", [None, datetime(2026, 6, 4, tzinfo=timezone.utc)])
def test_evaluate_key_on_postgres_matches_sqlite(pg_engine, since):
    _seed_postgres(pg_engine)
    lite = _mirror_to_sqlite(pg_engine)
    pg = mbe.evaluate_key(pg_engine, USER_ID, KEY, CURRENT, CHALLENGER, since=since)
    ref = mbe.evaluate_key(lite, USER_ID, KEY, CURRENT, CHALLENGER, since=since)
    assert set(pg) == set(ref) and len(pg) >= len(mbe.HORIZONS)
    expected_n = N_DATES * PER_DATE if since is None else (N_DATES - 3) * PER_DATE
    for k in ref:
        assert pg[k].unavailable_reason is None
        assert pg[k].n == ref[k].n == expected_n, k
        np.testing.assert_allclose(pg[k].net_returns, ref[k].net_returns, rtol=0, atol=1e-12)
        np.testing.assert_allclose(pg[k].daily_returns, ref[k].daily_returns, rtol=0, atol=1e-12)
    # net = direction-corrected alpha minus round-trip cost; check the 5d/1x series against the formula
    if since is None:
        want = sorted((_alpha(i, 5) - mbe.round_trip_cost_pct(1.0)) / 100.0 for i in range(N_DATES * PER_DATE))
        assert sorted(pg[(5, 1.0)].net_returns) == pytest.approx(want)


def test_unsettled_rows_are_excluded_on_postgres(pg_engine):
    seed_band_obs(pg_engine, KEY, START, [("AAA", 5.2, CURRENT)])
    out = mbe.evaluate_key(pg_engine, USER_ID, KEY, CURRENT, CHALLENGER)
    assert all(s.n == 0 for s in out.values())
