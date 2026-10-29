"""G8: the weekly charter digest and immediate charter notices (sqlite; the real ORM tables).
G8：章程週報與即時章程通知（sqlite＋真實 ORM 表）。

Evidence is synthetic (evaluate_key is replaced) and the watchdog is injected, so the output is deterministic.
證據為合成（替換 evaluate_key），看門狗以注入方式提供，輸出可決定。
"""
import math
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.parameter_registry import load_registry
from src.data.models import Base, CharterEvent, CharterState
from src.services import charter_digest_service as cds
from tests.charter_synth import NOW, make_evaluator, stream

REG = {p.key: p for p in load_registry().parameters}
ADAPTIVE = [p.key for p in load_registry().parameters if p.policy == "adaptive"]
USER = "u1"
KEY = "batch_deploy_min_confidence"
SHORT = stream(0.01, 0.005, 20, 3)              # 20 decisions: below any min_n in the registry
TABLES = ("parameter_values", "parameter_changes", "parameter_trials", "strategy_trials", "charter_state",
          "charter_events", "threshold_band_observations", "rotation_pair_observations", "decision_outcomes")


def _watchdog_ok(today):
    return {"overall": "OK", "criteria": [{"id": "K1", "name": "cost", "status": "ok", "value": 1.0,
                                           "threshold": 5.0, "unit": "%", "note": ""}], "breaches": []}


def _watchdog_down(today):
    raise RuntimeError("NAV unavailable")


@pytest.fixture(autouse=True)
def _no_evidence(monkeypatch):
    """Default: no band evidence. A test that needs series replaces evaluate_key itself. / 預設無證據。"""
    monkeypatch.setattr(cds, "evaluate_key", make_evaluator({}))


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in TABLES])
    return eng


def _rows(eng, model):
    with sessionmaker(bind=eng)() as s:
        return s.query(model).order_by(model.id).all()


def test_digest_lists_each_param_n_and_days_to_min_n(engine, monkeypatch):
    monkeypatch.setattr(cds, "evaluate_key", make_evaluator({KEY: SHORT}))
    d = cds.build_digest(engine, USER, NOW, watchdog=_watchdog_ok)
    by_key = {row["key"]: row for row in d["params"] if row["policy"] == "adaptive"}
    assert set(by_key) == set(ADAPTIVE)                       # every adaptive parameter is listed
    row = by_key[KEY]
    assert row["n_63d"] == 20 and row["min_n"] == REG[KEY].evidence.min_n
    # rate = decisions settled in the last 30 days / 30; the fake evaluator returns the same 20 for that window
    expected = math.ceil((row["min_n"] - 20) / (20 / cds.RATE_WINDOW_DAYS))
    assert row["days_to_min_n"] == expected
    assert f"{row['n_63d']}" in cds.render_digest(d) and KEY in cds.render_digest(d)


def test_days_to_min_n_unknown_without_settlement_rate(engine, monkeypatch):
    monkeypatch.setattr(cds, "evaluate_key", make_evaluator({}))      # no evidence at all
    d = cds.build_digest(engine, USER, NOW, watchdog=_watchdog_ok)
    row = next(r for r in d["params"] if r["key"] == KEY)
    assert row["days_to_min_n"] == cds.UNKNOWN
    assert row["days_reason"] == "no_settlement_rate"
    assert "unknown" in cds.render_digest(d)


def test_realtime_only_on_apply_rollback_halt(engine):
    sent = []
    notify = lambda title, content: sent.append(title)
    for kind in ("apply", "rollback", "freeze", "resume", "degrade", "enable", "drill"):
        cds.notify_event(engine, USER, kind, KEY, {"from": 5.5, "to": 5.0}, NOW, notify=notify)
    assert len(sent) == 7
    assert len([r for r in _rows(engine, CharterEvent)]) == 7
    for kind in ("verdict", "digest"):
        with pytest.raises(ValueError):
            cds.notify_event(engine, USER, kind, KEY, {}, NOW, notify=notify)
    assert len(sent) == 7 and len(_rows(engine, CharterEvent)) == 7   # nothing written or sent for the rest


def test_weekly_digest_skips_second_write_in_same_week(engine):
    sent = []
    notify = lambda title, content: sent.append(content)
    first = cds.write_weekly_digest(engine, USER, NOW, notify=notify, watchdog=_watchdog_ok)
    second = cds.write_weekly_digest(engine, USER, NOW + timedelta(hours=2), notify=notify, watchdog=_watchdog_ok)
    assert first["written"] and not second["written"]
    assert [r.kind for r in _rows(engine, CharterEvent)] == ["digest"]
    assert len(sent) == 1


def test_notify_failure_is_logged_and_digest_row_still_written(engine, caplog):
    def boom(title, content):
        raise ConnectionError("telegram down")
    with caplog.at_level("WARNING"):
        res = cds.write_weekly_digest(engine, USER, NOW, notify=boom, watchdog=_watchdog_ok)
    assert res["written"] and "telegram down" in res["error"]
    row = _rows(engine, CharterEvent)[0]
    assert row.kind == "digest" and "telegram down" in row.payload_json["error"]
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_watchdog_unavailable_is_stated_not_hidden(engine):
    text = cds.render_digest(cds.build_digest(engine, USER, NOW, watchdog=_watchdog_down))
    assert "看門狗不可用" in text and "NAV unavailable" in text


def test_charter_state_missing_is_stated(engine):
    d = cds.build_digest(engine, USER, NOW, watchdog=_watchdog_ok)
    assert d["charter_state"] == {"missing": True}
    with sessionmaker(bind=engine)() as s:
        s.merge(CharterState(id=1, mode="apply", reason="t", since=NOW - timedelta(days=3), human_stop=False))
        s.commit()
    assert cds.build_digest(engine, USER, NOW, watchdog=_watchdog_ok)["charter_state"]["mode"] == "apply"


def _digest(mode="apply", human_stop=False, kinds=()):
    state = (
        {"missing": True}
        if mode is None
        else {"mode": mode, "since": "2026-10-01", "reason": "", "human_stop": human_stop}
    )
    return {"charter_state": state, "events_7d": [{"kind": k, "key": KEY, "at": "2026-10-20T00:00:00"} for k in kinds]}


@pytest.mark.parametrize("d,symbol", [
    (_digest(), "📋"),
    (_digest(kinds=("apply", "rollback")), "📋"),
    (_digest(mode="frozen"), "🧊"),
    (_digest(human_stop=True), "🧊"),
    (_digest(kinds=("freeze", "resume")), "🧊"),
    (_digest(kinds=("freeze", "degrade")), "🛑"),
    (_digest(mode="frozen", kinds=("degrade",)), "🛑"),
    (_digest(mode=None), "📋"),
])
def test_digest_title_symbol_follows_the_week(d, symbol):
    assert cds.digest_title(d) == f"{symbol} 章程週報 / Charter weekly digest"


def test_weekly_digest_is_sent_with_the_state_symbol(engine):
    titles = []
    cds.write_weekly_digest(engine, USER, NOW, notify=lambda title, content: titles.append(title), watchdog=_watchdog_ok)
    expected = cds.digest_title(cds.build_digest(engine, USER, NOW, watchdog=_watchdog_ok))
    assert titles == [expected]
