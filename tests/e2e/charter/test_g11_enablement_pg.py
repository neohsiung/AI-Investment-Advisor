"""G11 on real Postgres: the enablement checker switches dry_run -> apply only when all six ADR-003 (6) criteria hold,
exactly once, and never over a human stop or a freeze.
G11 在真實 Postgres：六條件齊備才由 dry_run 切到 apply，只切一次，絕不越過人工停止或凍結。

Heavy modules are imported at the top, before any frozen clock starts; no asyncio timers under the frozen clock.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.config.parameter_registry import load_registry
from src.services import charter_digest_service as cds
from src.services import enablement_checker as ec
from src.services import parameter_engine as pe

from .factories import USER_ID, set_charter_state

pytestmark = pytest.mark.charter_e2e

ADAPTIVE = [p.key for p in load_registry().parameters if p.policy == "adaptive"]
FIRST_SATURDAY = datetime(2026, 10, 17, 10, 35, tzinfo=timezone.utc)      # the clock starts Monday 2026-10-19 12:00


def _event(engine, kind, when, key=None, payload=None):
    pe.record_event(engine, USER_ID, kind, key, payload or {}, when)


def _seed_ok(engine, now, *, first_verdict_days=91, drills=1, digests=8, freeze_days_ago=None):
    for k in ADAPTIVE:
        _event(engine, "verdict", now - timedelta(days=first_verdict_days), k, {"verdict": "hold"})
    for i in range(drills):
        _event(engine, "drill", now - timedelta(days=3 + i), payload={"ok": True})
    for i in range(digests):
        _event(engine, "digest", FIRST_SATURDAY - timedelta(days=7 * i), payload={"text": "digest"})
    if freeze_days_ago is not None:
        _event(engine, "freeze", now - timedelta(days=freeze_days_ago), payload={"breach_ids": ["K1"]})


class _Pipe:
    """The task shell's emitter with the notifier replaced by a recorder: real charter_events row, recorded notice."""

    def __init__(self, engine, now_fn):
        self.engine, self.now_fn, self.titles = engine, now_fn, []

    def __call__(self, kind, key, payload):
        cds.notify_event(self.engine, USER_ID, kind, key, payload, self.now_fn(),
                         notify=lambda title, body: self.titles.append(kind))


def _count(engine, kind):
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM charter_events WHERE kind = :k"), {"k": kind}).scalar()


def _state(engine):
    with engine.connect() as c:
        return dict(c.execute(text("SELECT mode, human_stop, reason, since, resume_mode, clears_on, breach_ids "
                                   "FROM charter_state WHERE id = 1")).mappings().one())


@pytest.mark.parametrize("broken", ["adr", "dry_run_90d", "zero_effect_sim", "drill", "8_digests", "no_freeze_30d"])
def test_enablement_refuses_when_missing(pg_engine, frozen_clock, monkeypatch, broken):
    kw = {"dry_run_90d": {"first_verdict_days": 89}, "drill": {"drills": 0}, "8_digests": {"digests": 7},
          "no_freeze_30d": {"freeze_days_ago": 10}}.get(broken, {})
    _seed_ok(pg_engine, frozen_clock.now(), **kw)
    if broken == "adr":
        monkeypatch.setattr(ec, "load_mission", lambda: SimpleNamespace(adr=[]))
    if broken == "zero_effect_sim":
        monkeypatch.setattr(ec, "zero_effect_false_loosening_rate", lambda *a, **k: 0.5)
    pipe = _Pipe(pg_engine, frozen_clock.now)
    ok, missing = ec.check(pg_engine, frozen_clock.now())
    assert ok is False and [m["criterion"] for m in missing] == [broken]
    res = ec.enable(pg_engine, frozen_clock.now(), pipe)
    assert res["enabled"] is False and _state(pg_engine)["mode"] == "dry_run"
    assert _count(pg_engine, "enable") == 0 and pipe.titles == []


def test_all_six_ok_switches_to_apply_exactly_once(pg_engine, frozen_clock):
    _seed_ok(pg_engine, frozen_clock.now())
    pipe = _Pipe(pg_engine, frozen_clock.now)
    assert ec.check(pg_engine, frozen_clock.now()) == (True, [])
    assert ec.enable(pg_engine, frozen_clock.now(), pipe)["enabled"] is True
    for _ in range(2):
        frozen_clock.advance(days=1)
        assert ec.enable(pg_engine, frozen_clock.now(), pipe)["enabled"] is False
    assert _state(pg_engine)["mode"] == "apply" and _state(pg_engine)["human_stop"] is False
    assert _count(pg_engine, "enable") == 1 and pipe.titles == ["enable"]


def test_dry_run_start_uses_earliest_verdict_not_since(pg_engine, frozen_clock):
    now = frozen_clock.now()
    set_charter_state(pg_engine, "dry_run", since=now - timedelta(days=2))        # as after a freeze -> resume rewrite
    _seed_ok(pg_engine, now, first_verdict_days=95)
    assert ec.check(pg_engine, now) == (True, [])


def test_old_since_does_not_stand_in_for_missing_verdict_history(pg_engine, frozen_clock):
    now = frozen_clock.now()
    set_charter_state(pg_engine, "dry_run", since=now - timedelta(days=400))
    _seed_ok(pg_engine, now, first_verdict_days=30)
    ok, missing = ec.check(pg_engine, now)
    assert ok is False and [m["criterion"] for m in missing] == ["dry_run_90d"]


def test_drill_restores_state_on_exception(pg_engine, frozen_clock, monkeypatch):
    set_charter_state(pg_engine, "tighten_only", reason="before drill", since=frozen_clock.now() - timedelta(days=5))
    before = _state(pg_engine)

    def boom(*a, **k):
        raise RuntimeError("gate exploded")
    monkeypatch.setattr(ec.charter_state_service, "order_allowed", boom)
    res = ec.drill(pg_engine, frozen_clock.now(), _Pipe(pg_engine, frozen_clock.now))
    assert res["ok"] is False
    assert _state(pg_engine) == before
    with pg_engine.connect() as c:
        payload = c.execute(text("SELECT payload_json FROM charter_events WHERE kind = 'drill'")).scalar()
    assert payload["ok"] is False


def test_drill_on_real_gate_passes_and_restores(pg_engine, frozen_clock):
    before = _state(pg_engine)
    res = ec.drill(pg_engine, frozen_clock.now(), _Pipe(pg_engine, frozen_clock.now))
    assert res["ok"] is True and _state(pg_engine) == before
    with pg_engine.connect() as c:
        assert c.execute(text("SELECT payload_json->>'ok' FROM charter_events WHERE kind = 'drill'")).scalar() == "true"


@pytest.mark.parametrize("mode,stop", [("frozen", False), ("human_stop", True), ("dry_run", True),
                                       ("apply", False), ("tighten_only", False)])
def test_enable_never_overrides_human_stop_or_frozen(pg_engine, frozen_clock, mode, stop):
    _seed_ok(pg_engine, frozen_clock.now())
    set_charter_state(pg_engine, mode, reason="held", human_stop=stop)
    before = _state(pg_engine)
    pipe = _Pipe(pg_engine, frozen_clock.now)
    assert ec.enable(pg_engine, frozen_clock.now(), pipe)["enabled"] is False
    assert _state(pg_engine) == before and _count(pg_engine, "enable") == 0 and pipe.titles == []
