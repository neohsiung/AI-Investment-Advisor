"""G10: the 7 read sites of the 6 registered keys read through param_policy.get_param.
G10：6 個登錄鍵的 7 個讀取點改經 param_policy.get_param 讀取。

Seed == today's default, so with an empty store nothing changes (characterization); a value the engine records
(source 'engine') is the one each reader then uses; a fallback warns and keeps the conservative value get_param
returned; the special value 0 (unlimited / check off) is still honoured from the raw setting.
"""
import pytest
from sqlalchemy import create_engine

from src.config.parameter_registry import load_registry
from src.config.settings_schema import schema_default
from src.data.models import Base
from src.services import param_policy
from src.services.param_policy import ParamResult, record_value
from tests import g10_readers as g

REG = {p.key: p for p in load_registry().parameters}
IDS = [s.name for s in g.SITES]


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in
                                          ("parameter_values", "parameter_trials", "parameter_changes",
                                           "charter_state")])
    return eng


@pytest.fixture()
def wired(monkeypatch, engine):
    g.wire(monkeypatch, lambda key, engine_=None, **kw: param_policy.get_param(key, engine=engine))
    return monkeypatch


def test_seven_sites_cover_six_keys():
    assert len(g.SITES) == 7 and len({s.key for s in g.SITES}) == 6
    assert all(s.key in REG and s.engine_value != schema_default(s.key) for s in g.SITES)


@pytest.mark.parametrize("site", g.SITES, ids=IDS)
def test_site_reads_same_value_as_before_when_store_empty(wired, site):
    assert float(site.drive(wired)) == float(schema_default(site.key))


@pytest.mark.parametrize("site", g.SITES, ids=IDS)
def test_site_uses_engine_value_when_stored(wired, engine, site):
    record_value(site.key, site.engine_value, "engine", engine=engine)
    assert float(site.drive(wired)) == float(site.engine_value)


@pytest.mark.parametrize("site", g.SITES, ids=IDS)
def test_site_warns_and_stays_conservative_on_fallback(monkeypatch, site):
    rollback = REG[site.key].rollback_value
    res = ParamResult(site.key, rollback, "rollback", "read_failed: db down")
    g.wire(monkeypatch, lambda key, *a, **kw: res)
    assert float(site.drive(monkeypatch)) == float(rollback)
    assert g.warned(site.module), "a non-empty fallback_reason must be logged as WARNING"


def test_event_cap_zero_stays_unlimited(wired, engine):
    record_value("event_analysis_daily_cap", 12, "engine", engine=engine)
    g._event_cap.raw = 0
    try:
        assert g._event_cap(wired) == 0          # never trips: unlimited, the engine value is not applied
    finally:
        g._event_cap.raw = 8


def test_rotation_min_holding_zero_stays_off(wired, engine):
    record_value("rotation_min_holding_days", 7, "engine", engine=engine)
    g._sentinel.raw_hold = 0
    try:
        assert g._rotation_hold(wired) == 0.0     # check disabled stays disabled
    finally:
        g._sentinel.raw_hold = 5


def test_engine_value_reaches_all_seven_readers(wired, engine):
    for key in {s.key for s in g.SITES}:
        value = next(s.engine_value for s in g.SITES if s.key == key)
        record_value(key, value, "engine", engine=engine)
    seen = {s.name: float(s.drive(wired)) for s in g.SITES}
    assert seen == {s.name: float(s.engine_value) for s in g.SITES}
