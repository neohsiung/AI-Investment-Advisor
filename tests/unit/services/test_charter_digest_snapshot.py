"""G8 golden snapshots of the rendered digest. A diff here is a visible change to the operator's weekly report.
Rewrite only with UPDATE_SNAPSHOTS=1 (the new golden file then shows up in the PR diff).
G8 渲染結果的黃金檔。這裡的差異就是操作者週報的可見變更；只有 UPDATE_SNAPSHOTS=1 才會改寫。
"""
import os
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.models import Base, CharterEvent, CharterState, ParameterChange, ParameterTrial
from src.services import charter_digest_service as cds
from tests.charter_synth import NOW, make_evaluator, stream

KEY = "batch_deploy_min_confidence"
TABLES = ("parameter_values", "parameter_changes", "parameter_trials", "strategy_trials", "charter_state",
          "charter_events", "threshold_band_observations", "rotation_pair_observations", "decision_outcomes")


def _watchdog_down(today):
    raise RuntimeError("NAV unavailable")

SNAP = Path(__file__).parent / "snapshots"
GOOD = stream(0.012, 0.006, 140, 11)


def _watchdog_full(today):
    return {"overall": "PARTIAL", "breaches": ["K3"], "criteria": [
        {"id": "K1", "name": "cost ratio", "status": "ok", "value": 0.4, "threshold": 5.0, "unit": "%", "note": ""},
        {"id": "K3", "name": "drawdown", "status": "breach", "value": 22.0, "threshold": 20.0, "unit": "%",
         "note": "trailing 63d"},
        {"id": "K5", "name": "alpha", "status": "unknown", "value": None, "threshold": 0.0, "unit": "%",
         "note": "history shorter than 252 days"}]}


def _engine_full():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in TABLES])
    with sessionmaker(bind=eng)() as s:
        s.add(CharterState(id=1, mode="apply", reason="charter_e2e", since=NOW - timedelta(days=40), human_stop=False))
        ch = ParameterChange(key=KEY, from_value_json=5.5, to_value_json=None, direction="loosen", verdict="hold",
                             applied_at=None, created_at=NOW - timedelta(days=1), window_series_json={})
        s.add(ch)
        s.add(CharterEvent(user_id="u1", kind="verdict", key=KEY, created_at=NOW - timedelta(days=1),
                           payload_json={"verdict": "hold", "direction": "loosen", "reasons": ["at_grid_edge"]}))
        s.add(CharterEvent(user_id="u1", kind="rollback", key=KEY, created_at=NOW - timedelta(days=2),
                           payload_json={"restored": 5.5}))
        s.add(ParameterTrial(key=KEY, grid_value=5.0, n_cum=3, registered_at=NOW - timedelta(days=2)))
        s.commit()
    return eng


def _check(name: str, text: str):
    path = SNAP / name
    if os.getenv("UPDATE_SNAPSHOTS") == "1":
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"missing golden file {name}; run with UPDATE_SNAPSHOTS=1"
    assert text == path.read_text(encoding="utf-8"), f"digest changed vs {name}; review and UPDATE_SNAPSHOTS=1"


def test_snapshot_empty(monkeypatch):
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in TABLES])
    monkeypatch.setattr(cds, "evaluate_key", make_evaluator({}))
    _check("charter_digest_empty.txt", cds.render_digest(cds.build_digest(eng, "u1", NOW, watchdog=_watchdog_down)))


def test_snapshot_full(monkeypatch):
    monkeypatch.setattr(cds, "evaluate_key", make_evaluator({KEY: GOOD}))
    eng = _engine_full()
    _check("charter_digest_full.txt", cds.render_digest(cds.build_digest(eng, "u1", NOW, watchdog=_watchdog_full)))
