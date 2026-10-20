"""G7: charter halt gate and watchdog transitions (sqlite + the real ORM table).
G7：章程停機閘門與看門狗狀態轉移。"""
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.models import Base, CharterState
from src.services import charter_state_service as css

pytestmark = pytest.mark.real_charter_gate

NOW = datetime(2026, 10, 20, 6, 10, tzinfo=timezone.utc)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables["charter_state"]])
    return eng


def _seed(eng, mode="apply", human_stop=False, **kw):
    with sessionmaker(bind=eng)() as s:
        s.merge(CharterState(id=1, mode=mode, reason="seed", since=NOW - timedelta(days=9), human_stop=human_stop, **kw))
        s.commit()


def _row(eng):
    with sessionmaker(bind=eng)() as s:
        r = s.query(CharterState).one()
        return {c: getattr(r, c) for c in ("mode", "human_stop", "reason", "since", "clears_on", "breach_ids",
                                           "resume_mode", "updated_at")}


def _result(*breaches, status=None, clears_on=None):
    ids = ("K1", "K2", "K3", "K4", "K5", "K6", "K7")
    st = dict.fromkeys(ids, "ok")
    st.update({k: "breach" for k in breaches})
    st.update(status or {})
    return {"breaches": list(breaches),
            "criteria": [{"id": k, "status": st[k], "clears_on": (clears_on or {}).get(k)} for k in ids]}


class Sink:
    def __init__(self):
        self.calls = []

    def __call__(self, kind, key, payload):
        self.calls.append((kind, key, payload))


# ── gate ─────────────────────────────────────────────────────────────────────
def test_sell_always_allowed_when_frozen(engine):
    _seed(engine, "frozen")
    for action in ("SELL", "sell", "CLOSE"):
        assert css.order_allowed(action, "momentum", NOW, engine) == (True, "exempt: not a buy")


@pytest.mark.parametrize("strategy", ["stop_loss", "benchmark_parking"])
def test_safety_control_buy_allowed_when_frozen(engine, strategy):
    _seed(engine, "frozen")
    assert css.order_allowed("BUY", strategy, NOW, engine) == (True, "exempt: safety control")


@pytest.mark.parametrize("action", ["BUY", "STRONG_BUY", "ADD", "ACCUMULATE"])
def test_nonsafety_buy_blocked_when_frozen(engine, action):
    _seed(engine, "frozen")
    ok, why = css.order_allowed(action, "batch_cash_deployment", NOW, engine)
    assert ok is False and "frozen" in why


def test_human_stop_flag_blocks_even_if_mode_looks_normal(engine):
    _seed(engine, "apply", human_stop=True)
    assert css.trading_allowed(engine, NOW)[0] is False


def test_normal_modes_allow(engine):
    for mode in ("dry_run", "apply", "tighten_only"):
        _seed(engine, mode)
        assert css.trading_allowed(engine, NOW) == (True, "ok")


def test_unreadable_state_blocks_buy_with_warning(caplog):
    broken = create_engine("sqlite:///:memory:")           # no charter_state table
    with caplog.at_level(logging.WARNING):
        ok, why = css.order_allowed("BUY", "batch_cash_deployment", NOW, broken)
    assert ok is False and "unreadable" in why
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_missing_row_blocks_buy(engine):
    assert css.trading_allowed(engine, NOW)[0] is False


def test_unreadable_state_never_blocks_sell_or_safety():
    broken = create_engine("sqlite:///:memory:")
    assert css.order_allowed("SELL", "momentum", NOW, broken)[0] is True
    assert css.order_allowed("BUY", "stop_loss", NOW, broken)[0] is True


# ── watchdog transitions ─────────────────────────────────────────────────────
@pytest.mark.parametrize("k", ["K1", "K3", "K4"])
def test_halting_k_breach_freezes_and_keeps_resume_mode(engine, k):
    _seed(engine, "apply")
    assert css.apply_watchdog(_result(k), NOW, engine, Sink()) == "freeze"
    r = _row(engine)
    assert (r["mode"], r["resume_mode"], r["breach_ids"]) == ("frozen", "apply", [k])
    assert r["since"].replace(tzinfo=timezone.utc) == NOW and r["updated_at"].replace(tzinfo=timezone.utc) == NOW


def test_k3_breach_freezes_and_keeps_resume_mode(engine):
    _seed(engine, "tighten_only")
    css.apply_watchdog(_result("K3"), NOW, engine)
    assert (_row(engine)["mode"], _row(engine)["resume_mode"]) == ("frozen", "tighten_only")


def test_freeze_stores_latest_structured_clears_on(engine):
    _seed(engine, "apply")
    css.apply_watchdog(_result("K3", "K4", clears_on={"K3": "2026-11-03", "K4": "2026-11-20"}), NOW, engine)
    assert _row(engine)["clears_on"].isoformat() == "2026-11-20"


def test_unknown_clears_on_stays_null(engine):
    _seed(engine, "apply")
    css.apply_watchdog(_result("K3", "K4", clears_on={"K3": "2026-11-03", "K4": None}), NOW, engine)
    assert _row(engine)["clears_on"] is None


@pytest.mark.parametrize("k", ["K2", "K5", "K6", "K7"])
def test_k2_or_k5_k6_k7_breach_does_not_freeze(engine, k):
    _seed(engine, "apply")
    assert css.apply_watchdog(_result(k), NOW, engine) is None
    assert _row(engine)["mode"] == "apply"


def test_not_measurable_does_not_freeze(engine):
    _seed(engine, "apply")
    assert css.apply_watchdog(_result(status={"K1": "not_measurable", "K3": "not_measurable"}), NOW, engine) is None


def test_clear_resumes_to_previous_mode(engine):
    _seed(engine, "tighten_only")
    css.apply_watchdog(_result("K1"), NOW, engine)
    assert css.apply_watchdog(_result(), NOW + timedelta(days=3), engine) == "resume"
    r = _row(engine)
    assert (r["mode"], r["resume_mode"], r["breach_ids"], r["clears_on"]) == ("tighten_only", None, None, None)


def test_resume_when_the_causing_k_is_only_not_measurable(engine):
    """Not measurable is not a breach: the freeze lifts (ADR-003; a freeze nobody can lift would be worse). / 不可量測不是違規。"""
    _seed(engine, "apply")
    css.apply_watchdog(_result("K3"), NOW, engine)
    assert css.apply_watchdog(_result(status={"K3": "not_measurable"}), NOW + timedelta(days=1), engine) == "resume"
    assert _row(engine)["mode"] == "apply"


def test_still_breaching_stays_frozen_without_new_event(engine):
    _seed(engine, "apply")
    sink = Sink()
    css.apply_watchdog(_result("K1"), NOW, engine, sink)
    assert css.apply_watchdog(_result("K1"), NOW + timedelta(days=1), engine, sink) is None
    assert [c[0] for c in sink.calls] == ["freeze"]


def test_freeze_writes_event_and_notifies(engine):
    _seed(engine, "apply")
    sink = Sink()
    css.apply_watchdog(_result("K1"), NOW, engine, sink)
    css.apply_watchdog(_result(), NOW + timedelta(days=1), engine, sink)
    assert [c[0] for c in sink.calls] == ["freeze", "resume"]
    assert sink.calls[0][2]["breach_ids"] == ["K1"] and sink.calls[0][2]["resume_mode"] == "apply"
    assert sink.calls[1][2]["resumed_to"] == "apply"


def test_emit_failure_does_not_undo_the_freeze(engine, caplog):
    _seed(engine, "apply")

    def boom(*a):
        raise RuntimeError("notify down")
    with caplog.at_level(logging.ERROR):
        assert css.apply_watchdog(_result("K1"), NOW, engine, boom) == "freeze"
    assert _row(engine)["mode"] == "frozen" and any(r.levelno >= logging.ERROR for r in caplog.records)


def test_unreadable_state_makes_apply_watchdog_raise():
    with pytest.raises(Exception):
        css.apply_watchdog(_result("K1"), NOW, create_engine("sqlite:///:memory:"))


# ── human stop ───────────────────────────────────────────────────────────────
def test_human_stop_never_auto_resumes(engine):
    _seed(engine, "apply")
    css.human_stop(engine, NOW, "test")
    for day in range(1, 5):
        assert css.apply_watchdog(_result(), NOW + timedelta(days=day), engine) is None
    r = _row(engine)
    assert (r["mode"], r["human_stop"], r["resume_mode"]) == ("human_stop", True, "apply")
    assert css.trading_allowed(engine, NOW)[0] is False


def test_breach_does_not_overwrite_human_stop(engine):
    _seed(engine, "apply")
    css.human_stop(engine, NOW, "test")
    assert css.apply_watchdog(_result("K1"), NOW, engine) is None
    assert _row(engine)["mode"] == "human_stop"


def test_human_stop_during_freeze_keeps_original_resume_mode(engine):
    _seed(engine, "apply")
    css.apply_watchdog(_result("K1"), NOW, engine)
    css.human_stop(engine, NOW, "test")
    assert _row(engine)["resume_mode"] == "apply"


def test_release_clears_only_human_flag(engine):
    _seed(engine, "apply")
    css.human_stop(engine, NOW, "test")
    css.human_release(engine, NOW + timedelta(hours=1))
    r = _row(engine)
    assert (r["mode"], r["human_stop"]) == ("apply", False)
    assert css.trading_allowed(engine, NOW)[0] is True


def test_release_with_breach_still_present_refreezes_on_next_pass(engine):
    _seed(engine, "apply")
    css.human_stop(engine, NOW, "test")
    css.human_release(engine, NOW)
    assert css.apply_watchdog(_result("K3"), NOW + timedelta(days=1), engine) == "freeze"


def test_release_is_a_noop_on_a_watchdog_freeze(engine):
    _seed(engine, "apply")
    css.apply_watchdog(_result("K1"), NOW, engine)
    css.human_release(engine, NOW)
    assert _row(engine)["mode"] == "frozen"
