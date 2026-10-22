"""L8 (G11): the enablement checker, one criterion at a time (sqlite + the real ORM tables).
L8：啟用檢查器，逐條件驗證。ADR-003 (6): this ADR; dry_run >= 90 days from the earliest verdict; zero-effect false
loosening <= alpha (measured); a halt drill passed; 8 consecutive weekly digests; no K breach in 30 days.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.parameter_registry import load_registry
from src.data.models import Base, CharterEvent, CharterState
from src.services import enablement_checker as ec

pytestmark = pytest.mark.real_charter_gate                      # the drill exercises the real halt gate

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)        # a Monday
TABLES = ("charter_state", "charter_events", "parameter_trials", "strategy_trials")
ADAPTIVE = [p.key for p in load_registry().parameters if p.policy == "adaptive"]


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in TABLES])
    with sessionmaker(bind=eng)() as s:
        s.add(CharterState(id=1, mode="dry_run", reason="seed", since=NOW - timedelta(days=1), human_stop=False))
        s.commit()
    return eng


def _add(eng, kind, when, key=None, payload=None):
    with sessionmaker(bind=eng)() as s:
        s.add(CharterEvent(user_id="u1", kind=kind, key=key, payload_json=payload or {}, created_at=when))
        s.commit()


def _verdicts(eng, when, keys=None):
    for k in (ADAPTIVE if keys is None else keys):
        _add(eng, "verdict", when, k, {"verdict": "hold"})


def _saturdays(n):
    last = datetime(2026, 10, 17, 10, 35, tzinfo=timezone.utc)
    return [last - timedelta(days=7 * i) for i in range(n)]


def _seed_ok(eng):
    _verdicts(eng, NOW - timedelta(days=91))
    _add(eng, "drill", NOW - timedelta(days=3), payload={"ok": True})
    for d in _saturdays(8):
        _add(eng, "digest", d)


def _missing(eng, now=NOW):
    ok, missing = ec.check(eng, now)
    return ok, {m["criterion"]: m for m in missing}


def _mode(eng):
    with sessionmaker(bind=eng)() as s:
        r = s.query(CharterState).one()
        return r.mode, r.human_stop


def _set_state(eng, **kw):
    with sessionmaker(bind=eng)() as s:
        r = s.query(CharterState).one()
        for k, v in kw.items():
            setattr(r, k, v)
        s.commit()


def test_empty_history_is_not_enabled_and_names_every_gap(engine):
    ok, m = _missing(engine)
    assert ok is False
    assert set(m) == {"dry_run_90d", "drill", "8_digests"}          # adr, simulation and no-freeze hold on an empty db
    assert all(x["status"] in ("not_ok", "not_measurable") and "value" in x for x in m.values())


def test_all_six_hold(engine):
    _seed_ok(engine)
    ok, missing = ec.check(engine, NOW)
    assert ok is True and missing == []


def test_adr_missing_is_not_ok(engine, monkeypatch):
    _seed_ok(engine)
    monkeypatch.setattr(ec, "load_mission", lambda: SimpleNamespace(adr=[SimpleNamespace(id="ADR-001")]))
    _, m = _missing(engine)
    assert set(m) == {"adr"} and m["adr"]["status"] == "not_ok"


def test_adr_unreadable_is_not_measurable(engine, monkeypatch):
    _seed_ok(engine)

    def boom():
        raise RuntimeError("mission.yaml broken")
    monkeypatch.setattr(ec, "load_mission", boom)
    ok, m = _missing(engine)
    assert ok is False and m["adr"]["status"] == "not_measurable"


def test_dry_run_counts_from_the_earliest_verdict(engine):
    _verdicts(engine, NOW - timedelta(days=89))
    _, m = _missing(engine)
    assert m["dry_run_90d"]["status"] == "not_ok" and m["dry_run_90d"]["value"]["days"] == 89
    _add(engine, "verdict", NOW - timedelta(days=120), ADAPTIVE[0], {"verdict": "hold"})     # earlier row moves the start
    _, m = _missing(engine)
    assert "dry_run_90d" not in m


def test_dry_run_ignores_charter_state_since(engine):
    _set_state(engine, since=NOW - timedelta(days=400))
    _, m = _missing(engine)
    assert m["dry_run_90d"]["status"] == "not_ok" and m["dry_run_90d"]["value"]["days"] is None


def test_dry_run_requires_a_verdict_for_every_adaptive_parameter(engine):
    _verdicts(engine, NOW - timedelta(days=100), keys=ADAPTIVE[:-1])
    _, m = _missing(engine)
    assert m["dry_run_90d"]["value"]["keys_without_verdict"] == [ADAPTIVE[-1]]


def test_error_verdict_rows_without_key_do_not_start_the_clock(engine):
    _add(engine, "verdict", NOW - timedelta(days=200), None, {"error": "engine failed"})
    _verdicts(engine, NOW - timedelta(days=10))
    _, m = _missing(engine)
    assert m["dry_run_90d"]["value"]["days"] == 10


def test_zero_effect_rate_is_measured_and_within_alpha():
    rate = ec.zero_effect_false_loosening_rate(alpha=0.05, n_runs=300)
    assert 0.0 <= rate <= 0.05


def test_zero_effect_rate_detects_a_broken_boundary():
    # claiming a sigma 20x too small voids the guarantee; the measurement must show it (it is not assumed)
    rate = ec.zero_effect_false_loosening_rate(alpha=0.05, n_runs=300, claimed_sigma=0.001)
    assert rate > 0.05


def test_zero_effect_above_alpha_is_not_ok(engine, monkeypatch):
    _seed_ok(engine)
    monkeypatch.setattr(ec, "zero_effect_false_loosening_rate", lambda *a, **k: 0.2)
    _, m = _missing(engine)
    assert set(m) == {"zero_effect_sim"} and m["zero_effect_sim"]["value"]["rate"] == 0.2


def test_zero_effect_unreadable_trial_count_is_not_measurable(engine):
    _seed_ok(engine)
    Base.metadata.tables["parameter_trials"].drop(engine)
    ok, m = _missing(engine)
    assert ok is False and m["zero_effect_sim"]["status"] == "not_measurable"


def test_drill_must_have_passed(engine):
    _verdicts(engine, NOW - timedelta(days=91))
    for d in _saturdays(8):
        _add(engine, "digest", d)
    _add(engine, "drill", NOW - timedelta(days=5), payload={"ok": False})
    _, m = _missing(engine)
    assert set(m) == {"drill"}
    _add(engine, "drill", NOW - timedelta(days=4), payload={"ok": True})
    assert _missing(engine)[0] is True


def test_seven_digests_are_not_enough(engine):
    _verdicts(engine, NOW - timedelta(days=91))
    _add(engine, "drill", NOW - timedelta(days=3), payload={"ok": True})
    for d in _saturdays(7):
        _add(engine, "digest", d)
    _, m = _missing(engine)
    assert m["8_digests"]["value"]["consecutive_weeks"] == 7


def test_digest_gap_breaks_the_run(engine):
    _verdicts(engine, NOW - timedelta(days=91))
    _add(engine, "drill", NOW - timedelta(days=3), payload={"ok": True})
    days = _saturdays(10)
    for d in days:
        if d != days[3]:
            _add(engine, "digest", d)
    _, m = _missing(engine)
    assert m["8_digests"]["value"]["consecutive_weeks"] == 3


def test_two_digests_in_one_week_count_once(engine):
    _verdicts(engine, NOW - timedelta(days=91))
    _add(engine, "drill", NOW - timedelta(days=3), payload={"ok": True})
    for d in _saturdays(7):
        _add(engine, "digest", d)
    _add(engine, "digest", _saturdays(1)[0] + timedelta(hours=2))
    _, m = _missing(engine)
    assert m["8_digests"]["value"]["consecutive_weeks"] == 7


def test_stale_digest_run_does_not_count(engine):
    _seed_ok(engine)
    _, m = _missing(engine, NOW + timedelta(days=14))                 # the run ended two ISO weeks ago
    assert m["8_digests"]["status"] == "not_ok"


def test_recent_k_breach_freeze_blocks_but_old_or_human_one_does_not(engine):
    _seed_ok(engine)
    _add(engine, "freeze", NOW - timedelta(days=31), payload={"breach_ids": ["K1"]})
    _add(engine, "freeze", NOW - timedelta(days=2), payload={"source": "human", "reason": "stop"})
    assert _missing(engine)[0] is True
    _add(engine, "freeze", NOW - timedelta(days=29), payload={"breach_ids": ["K3"]})
    _, m = _missing(engine)
    assert set(m) == {"no_freeze_30d"} and m["no_freeze_30d"]["value"]["freezes"] == 1


def test_unreadable_history_is_not_measurable_and_not_satisfied(engine):
    _seed_ok(engine)
    Base.metadata.tables["charter_events"].drop(engine)
    ok, m = _missing(engine)
    assert ok is False
    assert {m[c]["status"] for c in ("dry_run_90d", "drill", "8_digests", "no_freeze_30d")} == {"not_measurable"}


def test_enable_switches_once_and_emits_once(engine):
    _seed_ok(engine)
    sent = []
    emit = lambda kind, key, payload: sent.append((kind, payload))
    first = ec.enable(engine, NOW, emit)
    second = ec.enable(engine, NOW + timedelta(days=1), emit)
    assert first["enabled"] is True and second["enabled"] is False
    assert _mode(engine) == ("apply", False)
    assert [k for k, _ in sent] == ["enable"]


@pytest.mark.parametrize("mode,stop", [("apply", False), ("tighten_only", False), ("frozen", False),
                                       ("human_stop", True), ("dry_run", True)])
def test_enable_only_from_dry_run_without_human_stop(engine, mode, stop):
    _seed_ok(engine)
    _set_state(engine, mode=mode, human_stop=stop)
    sent = []
    res = ec.enable(engine, NOW, lambda *a: sent.append(a))
    assert res["enabled"] is False and sent == [] and _mode(engine) == (mode, stop)


def test_enable_refuses_when_a_criterion_is_missing(engine):
    sent = []
    res = ec.enable(engine, NOW, lambda *a: sent.append(a))
    assert res["enabled"] is False and {m["criterion"] for m in res["missing"]} == {"dry_run_90d", "drill", "8_digests"}
    assert sent == [] and _mode(engine) == ("dry_run", False)


def test_enable_with_unreadable_state_fails_closed(engine):
    _seed_ok(engine)
    Base.metadata.tables["charter_state"].drop(engine)
    sent = []
    res = ec.enable(engine, NOW, lambda *a: sent.append(a))
    assert res["enabled"] is False and sent == []


def test_enable_race_lost_does_not_emit(engine, monkeypatch):
    _seed_ok(engine)
    real = ec.read_state

    def stale(eng):
        st = real(eng)
        _set_state(eng, human_stop=True)             # a human stop lands between the read and the conditional UPDATE
        return st
    monkeypatch.setattr(ec, "read_state", stale)
    sent = []
    res = ec.enable(engine, NOW, lambda *a: sent.append(a))
    assert res["enabled"] is False and sent == [] and _mode(engine)[1] is True


def test_drill_passes_and_restores_state(engine):
    _set_state(engine, mode="tighten_only", reason="before drill")
    seen = []
    res = ec.drill(engine, NOW, lambda kind, key, payload: seen.append((kind, payload, _mode(engine))))
    assert res["ok"] is True
    assert seen == [("drill", {"ok": True, "buy_refused": True, "stop_loss_allowed": True, "error": None},
                     ("tighten_only", False))]
    with sessionmaker(bind=engine)() as s:
        r = s.query(CharterState).one()
        assert (r.mode, r.reason) == ("tighten_only", "before drill")


def test_drill_restores_state_on_exception(engine, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gate exploded")
    monkeypatch.setattr(ec.charter_state_service, "order_allowed", boom)
    seen = []
    res = ec.drill(engine, NOW, lambda kind, key, payload: seen.append(payload))
    assert res["ok"] is False and "gate exploded" in res["error"]
    assert _mode(engine) == ("dry_run", False) and seen[0]["ok"] is False


def test_drill_fails_when_buy_is_not_refused(engine, monkeypatch):
    monkeypatch.setattr(ec.charter_state_service, "order_allowed", lambda *a, **k: (True, "ok"))
    res = ec.drill(engine, NOW, lambda *a: None)
    assert res["ok"] is False and res["buy_refused"] is False
    assert _mode(engine) == ("dry_run", False)


def test_drill_does_not_touch_an_already_blocking_state(engine):
    _set_state(engine, mode="human_stop", human_stop=True, reason="human stop: x")
    seen = []
    res = ec.drill(engine, NOW, lambda kind, key, payload: seen.append(payload))
    assert res["ok"] is False and seen[0]["ok"] is False
    with sessionmaker(bind=engine)() as s:
        r = s.query(CharterState).one()
        assert (r.mode, r.human_stop, r.reason) == ("human_stop", True, "human stop: x")


def test_drill_endpoint_is_a_post_route_behind_the_same_auth_dependency():
    from src.api.v1.dependencies import get_current_user_id
    from src.api.v1.endpoints import mission
    route = next(r for r in mission.router.routes if r.path == "/charter/drill")
    assert route.methods == {"POST"}
    assert any(d.call is get_current_user_id for d in route.dependant.dependencies)


def test_digest_lists_the_missing_criteria(engine):
    from src.services import charter_digest_service as cds
    en = cds._enablement(engine, NOW)
    assert en["ok"] is False and {m["criterion"] for m in en["missing"]} == {"dry_run_90d", "drill", "8_digests"}


def test_digest_enablement_failure_is_kept_not_hidden(engine, monkeypatch):
    from src.services import charter_digest_service as cds

    def boom(*a):
        raise RuntimeError("x")
    monkeypatch.setattr(cds.enablement_checker, "check", boom)
    assert cds._enablement(engine, NOW) == {"error": "x"}


def test_crashed_drill_resumes_to_prior_mode_not_dry_run(engine, monkeypatch):
    """The process dies after the drill froze the state (``finally`` never ran). The next watchdog pass with no breach
    must put back the mode the drill started from. / 演練凍結後程序死掉：看門狗解除時要回到演練前的模式。"""
    from src.services import charter_state_service as css
    _set_state(engine, mode="apply")
    monkeypatch.setattr(ec, "_restore", lambda *a, **k: None)          # simulate the crash: no restore
    ec.drill(engine, NOW)
    assert _mode(engine) == ("frozen", False)
    assert css.apply_watchdog({"breaches": []}, NOW + timedelta(hours=1), engine) == "resume"
    assert _mode(engine) == ("apply", False)
