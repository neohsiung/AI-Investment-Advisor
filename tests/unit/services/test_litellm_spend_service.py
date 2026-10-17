"""
Real LLM cost collection from LiteLLM /key/info (2026-10 audit: benchmark estimate was ~7x real).
LiteLLM 真實花費收集測試。
"""
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from src.services.litellm_spend_service import LiteLLMSpendService


@pytest.fixture
def engine():
    e = create_engine("sqlite://")
    with e.begin() as c:
        c.execute(text("CREATE TABLE llm_real_cost_daily (day DATE NOT NULL, key_alias VARCHAR(64) NOT NULL, "
                       "spend_usd NUMERIC NOT NULL DEFAULT 0, source VARCHAR(32) NOT NULL DEFAULT 'x', "
                       "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (day, key_alias))"))
        c.execute(text("CREATE TABLE llm_real_cost_state (key_alias VARCHAR(64) PRIMARY KEY, "
                       "last_spend NUMERIC NOT NULL, last_reset_at VARCHAR(40), updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
    return e


def _svc(engine, spends):
    """spends: iterator of (spend, reset_at) returned by successive /key/info calls."""
    it = iter(spends)

    def get(url, headers=None, timeout=None):
        spend, reset = next(it)
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"info": {"spend": spend, "key_alias": "advisor-prod",
                                        "max_budget": 20.0, "budget_reset_at": reset}}
        return r

    return LiteLLMSpendService(engine=engine, http_get=get, key_provider=lambda: "k")


def _daily(engine):
    with engine.connect() as c:
        return {str(r[0]): float(r[1]) for r in c.execute(text("SELECT day, spend_usd FROM llm_real_cost_daily"))}


def test_first_poll_only_sets_baseline(engine):
    svc = _svc(engine, [(4.4, "R1")])
    out = svc.collect(today=date(2026, 10, 16))
    assert out["note"] == "baseline_created" and out["delta_usd"] == 0.0
    assert _daily(engine) == {}


def test_delta_booked_on_same_period(engine):
    svc = _svc(engine, [(4.0, "R1"), (4.5, "R1"), (4.75, "R1")])
    d = date(2026, 10, 16)
    svc.collect(today=d); svc.collect(today=d); svc.collect(today=d)
    assert _daily(engine) == {"2026-10-16": pytest.approx(0.75)}


def test_period_reset_books_full_new_spend(engine):
    svc = _svc(engine, [(19.0, "R1"), (0.4, "R2")])
    svc.collect(today=date(2026, 10, 18)); out = svc.collect(today=date(2026, 10, 19))
    assert out["note"] == "period_reset"
    assert _daily(engine)["2026-10-19"] == pytest.approx(0.4)


def test_fetch_failure_raises_not_zero(engine):
    def bad(url, headers=None, timeout=None):
        r = MagicMock(); r.status_code = 500; return r
    svc = LiteLLMSpendService(engine=engine, http_get=bad, key_provider=lambda: "k")
    with pytest.raises(RuntimeError):
        svc.collect()


def test_get_spend_requires_coverage_else_none(engine):
    svc = _svc(engine, [])
    today = date(2026, 10, 16)
    with engine.begin() as c:
        for i in range(3):
            c.execute(text("INSERT INTO llm_real_cost_daily (day, key_alias, spend_usd) VALUES (:d, 'advisor-prod', 1.5)"),
                      {"d": today - timedelta(days=i)})
    ok = svc.get_spend(3, today=today)
    assert ok == {"total_cost": 4.5, "days_covered": 3, "window_days": 3, "source": "litellm_billed"}
    assert svc.get_spend(14, today=today) is None   # only 3/14 days booked -> do not trust
