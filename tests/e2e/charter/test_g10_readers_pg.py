"""G10 on real Postgres: a value recorded as source 'engine' is the one each of the 7 readers then uses.
G10 在真實 Postgres：以 source='engine' 記錄的值，7 個讀取點都讀得到。"""
import pytest

from src.services import param_policy
from src.services.param_policy import record_value
from tests import g10_readers as g

pytestmark = pytest.mark.charter_e2e


def test_record_value_then_each_reader_sees_it(pg_engine, frozen_clock, monkeypatch):
    g.wire(monkeypatch, lambda key, *a, **kw: param_policy.get_param(key, engine=pg_engine))
    before = {s.name: float(s.drive(monkeypatch)) for s in g.SITES}
    for key in {s.key for s in g.SITES}:
        value = next(s.engine_value for s in g.SITES if s.key == key)
        record_value(key, value, "engine", engine=pg_engine, now=frozen_clock.now())
    after = {s.name: float(s.drive(monkeypatch)) for s in g.SITES}
    assert after == {s.name: float(s.engine_value) for s in g.SITES}
    assert all(before[n] != after[n] for n in before)
