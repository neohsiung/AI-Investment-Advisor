"""E0 harness self-check: the charter E2E harness must itself be trustworthy before any milestone relies on it.
E0 自檢：章程 E2E harness 本身必須可信，後續里程碑才能倚賴它。"""
import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from tests.invariants.test_charter_clock_contract import CHARTER_MODULES, violations_in_source

from .factories import resolve_pg_url, seed_band_obs, settle, validate_pg_url

pytestmark = pytest.mark.charter_e2e


@pytest.mark.parametrize("url", [
    "postgresql+psycopg2://postgres:postgres@db.example.com:5432/portfolio",    # remote host
    "postgresql+psycopg2://postgres:postgres@localhost:5432/advisor_prod",      # production db name
    "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/postgres",          # not an allowed name
    "postgresql+psycopg2://postgres:postgres@advisor_prod_db:5432/charter_e2e",  # container hostname
])
def test_harness_refuses_non_local_db(url):
    with pytest.raises(pytest.exit.Exception):
        validate_pg_url(url)


@pytest.mark.parametrize("url", [
    "postgresql+psycopg2://postgres:postgres@localhost:55433/portfolio",
    "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/charter_e2e",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/charter_e2e_x",
])
def test_harness_accepts_local_throwaway_db(url):
    assert validate_pg_url(url) == url


def test_alembic_head_reached(pg_engine):
    with pg_engine.connect() as c:
        row = c.execute(text("SELECT mode FROM charter_state WHERE id = 1")).fetchone()
        n_head = c.execute(text("SELECT count(*) FROM alembic_version")).scalar()
    assert row is not None and row[0] == "dry_run"
    assert n_head >= 1


def test_tables_truncated_between_tests(pg_engine):
    with pg_engine.connect() as c:
        for t in ("parameter_values", "parameter_changes", "parameter_trials", "threshold_band_observations",
                  "rotation_pair_observations", "decision_outcomes"):
            assert c.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0, t  # noqa: S608 fixed names


def test_factory_roundtrip_band_obs_settled(pg_engine):
    seed_band_obs(pg_engine, "batch_deploy_min_confidence", date(2026, 9, 1), [("AAA", 5.2, 5.5)])
    with pg_engine.connect() as c:
        obs = c.execute(text("SELECT score, threshold_value, obs_date FROM threshold_band_observations")).fetchall()
        outs = c.execute(text("SELECT horizon_days, resolved_at FROM decision_outcomes ORDER BY horizon_days")).fetchall()
    assert [(float(o[0]), float(o[1]), o[2]) for o in obs] == [(5.2, 5.5, date(2026, 9, 1))]
    assert [o[0] for o in outs] == [5, 63] and all(o[1] is None for o in outs)
    settle(pg_engine, source="threshold_band", horizon_days=5, alpha_pct=1.5, realized_return_pct=2.0,
           resolved_at=datetime(2026, 9, 6, tzinfo=timezone.utc), decided_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    with pg_engine.connect() as c:
        r = c.execute(text("SELECT alpha_pct, realized_return_pct, resolved_at FROM decision_outcomes "
                           "WHERE horizon_days = 5")).fetchone()
        still_open = c.execute(text("SELECT count(*) FROM decision_outcomes WHERE horizon_days = 63 "
                                    "AND resolved_at IS NULL")).scalar()
    assert float(r[0]) == 1.5 and float(r[1]) == 2.0 and r[2] is not None and still_open == 1


def test_frozen_clock_advances(frozen_clock):
    t0 = datetime.now(timezone.utc)
    frozen_clock.advance(days=3)
    assert (datetime.now(timezone.utc) - t0).days == 3


def test_not_skipped_in_ci():
    """Under CI (or CHARTER_E2E_REQUIRE_PG) the harness must find a database; skipping would hide a dead gate."""
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS") or os.getenv("CHARTER_E2E_REQUIRE_PG"):
        assert resolve_pg_url() is not None, "no Postgres reachable for charter_e2e although the gate requires one"


def test_clock_contract_scans_new_modules():
    assert CHARTER_MODULES[:2] == ["src/services/marginal_band_evaluator.py", "src/services/param_policy.py"]
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    for rel in CHARTER_MODULES:
        assert os.path.exists(os.path.join(repo, rel)), rel
    bad = ("from sqlalchemy import func\n"
           "def f(engine):\n    engine.execute(text('UPDATE t SET a = NOW()'))\n    return func.now()\n"
           "def g():\n    return datetime.now()\n")
    ok = "def g(now=None):\n    return now or datetime.now()\n"
    assert len(violations_in_source(bad, "bad.py")) == 3
    assert violations_in_source(ok, "ok.py") == []
