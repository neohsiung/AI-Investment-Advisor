"""G6/G9: the charter change engine (dry_run default, apply only when charter_state says so).
G6/G9：章程變更引擎（預設 dry_run；只有 charter_state 允許才套用）。

Evidence is synthetic (evaluate_key is replaced); the database is sqlite with the real ORM tables.
證據為合成（替換 evaluate_key）；資料庫為 sqlite 加真實 ORM 表。
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config.parameter_registry import load_registry
from src.data.models import (Base, CharterEvent, CharterState, ParameterChange, ParameterTrial, ParameterValue,
                             StrategyTrial)
from src.evaluation.regime import RegimeCheck
from src.evaluation.sequential import confidence_sequence_any_time_loosen, loosening_alpha
from src.services import parameter_engine as pe
from src.services.param_policy import get_param, record_value
from tests.charter_synth import NOW, band_series, closes_provider, make_evaluator, series_dict, stream

REG = {p.key: p for p in load_registry().parameters}
USER = "u1"
KEY = "batch_deploy_min_confidence"            # first adaptive key with a recorder, risk_direction -1 (5.5 -> 5.0 loosens)
GOOD = stream(0.012, 0.006, 140, 11)           # strong, steady edge: passes all five conditions at 140 decisions
BAD = stream(-0.02, 0.006, 140, 12)
TABLES = ("parameter_values", "parameter_changes", "parameter_trials", "strategy_trials", "charter_state",
          "charter_events")


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in TABLES])
    return eng


def _mode(eng, mode="dry_run", human_stop=False):
    with sessionmaker(bind=eng)() as s:
        s.merge(CharterState(id=1, mode=mode, reason="t", since=NOW - timedelta(days=100), human_stop=human_stop))
        s.commit()


def _rows(eng, model, **flt):
    with sessionmaker(bind=eng)() as s:
        return s.query(model).filter_by(**flt).order_by(model.id).all()


def _run(eng, per_key=None, default=None, now=NOW, notify=None, monkeypatch=None):
    monkeypatch.setattr(pe, "evaluate_key", make_evaluator(per_key or {}, default))
    return pe.run_once(USER, eng, now, notify=notify, closes_provider=closes_provider())


def _by_key(verdicts):
    return {v.key: v for v in verdicts}


# ── grid ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_grid_neighbours_direction_minus_one():
    assert pe.grid_neighbours(REG[KEY], 5.5) == (5.0, 6.0)


def test_grid_neighbours_direction_plus_one():
    assert pe.grid_neighbours(REG["event_analysis_daily_cap"], 8) == (12.0, 6.0)


def test_grid_neighbours_at_edge_returns_none():
    assert pe.grid_neighbours(REG[KEY], 5.0) == (None, 5.5)
    assert pe.grid_neighbours(REG[KEY], 7.0) == (6.5, None)


def test_off_grid_current_is_hold_with_marker(engine, monkeypatch):
    _mode(engine)
    record_value(KEY, 5.7, "human", engine=engine, now=NOW - timedelta(days=200))
    v = _by_key(_run(engine, default=GOOD, monkeypatch=monkeypatch))[KEY]
    assert v.direction == "hold" and any("off_grid" in r for r in v.reasons)


# ── five conditions ──────────────────────────────────────────────────────────────────────────────────────────────
def _conds(x, x2=None, regime=RegimeCheck(True, True, {"up_lovol": 40}), n_cum=40):
    s = series_dict(KEY, x, x2=x2)
    return pe.loosening_conditions(s, loosening_alpha(n_cum), 30, regime)


def test_loosen_requires_all_five_conditions():
    assert _conds(GOOD)["all"] is True
    assert _conds(GOOD, x2=BAD)["all"] is False                        # 2x cost negative
    assert _conds(GOOD[:60])["all"] is False                           # 63d x2 windows not available yet
    assert _conds(GOOD, regime=RegimeCheck(True, False, {}))["all"] is False


def test_regime_not_measurable_blocks_loosen():
    c = _conds(GOOD, regime=RegimeCheck(False, False, {}))
    assert c["regime"] == "not_measurable" and c["all"] is False


def test_unavailable_series_never_loosens():
    s = series_dict(KEY, GOOD)
    s[(63, 1.0)] = band_series(KEY, [], horizon=63, mult=1.0)
    s[(63, 1.0)] = s[(63, 1.0)].__class__(**{**s[(63, 1.0)].__dict__, "unavailable_reason": "no_recorder_for_key"})
    assert pe.loosening_conditions(s, 0.001, 30, RegimeCheck(True, True, {})) == {"unavailable": "no_recorder_for_key"}


# ── dry_run ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_dry_run_records_verdict_but_never_writes_parameter_values(engine, monkeypatch):
    _mode(engine, "dry_run")
    vs = _run(engine, default=GOOD, monkeypatch=monkeypatch)
    assert len(vs) == 6 and not any(v.applied for v in vs)
    assert _rows(engine, ParameterValue) == []
    changes = _rows(engine, ParameterChange)
    assert len(changes) == 6 and all(c.applied_at is None for c in changes)
    assert len(_rows(engine, CharterEvent, kind="verdict")) == 6
    assert _by_key(vs)[KEY].direction == "loosen"                      # recorded as a loosen verdict, just not applied


def test_dry_run_registers_trials_and_consumes_quota(engine, monkeypatch):
    _mode(engine)
    _run(engine, default=GOOD, monkeypatch=monkeypatch)
    trials = _rows(engine, ParameterTrial)
    assert len(trials) == 6 and trials[-1].n_cum == 6


def test_register_trial_idempotent(engine):
    with sessionmaker(bind=engine)() as s:
        pe.register_trial(s, KEY, 5.0, NOW)
        pe.register_trial(s, KEY, 5.0, NOW)
        s.commit()
        assert s.query(ParameterTrial).count() == 1


def test_n_cum_includes_strategy_trials(engine):
    with sessionmaker(bind=engine)() as s:
        s.add(StrategyTrial(params_hash="h1", family="f", params_json="{}", first_eval_at=NOW, last_eval_at=NOW,
                            n_evals=1, status="rejected"))
        pe.register_trial(s, KEY, 5.0, NOW)
        s.commit()
        assert pe.n_cum(s) == 2


# ── apply / tighten ──────────────────────────────────────────────────────────────────────────────────────────────
def test_apply_mode_writes_engine_value_and_change_row(engine, monkeypatch):
    _mode(engine, "apply")
    sent = []
    vs = _run(engine, per_key={KEY: GOOD}, notify=lambda m, **k: sent.append(m), monkeypatch=monkeypatch)
    v = _by_key(vs)[KEY]
    assert v.applied and v.direction == "loosen"
    assert get_param(KEY, engine=engine).value == 5.0
    ch = [c for c in _rows(engine, ParameterChange, key=KEY)][0]
    assert ch.applied_at is not None and ch.direction == "loosen"
    assert _rows(engine, ParameterValue, key=KEY)[0].change_id == ch.id
    assert sent == ["apply"] and len(_rows(engine, CharterEvent, kind="apply")) == 1


def test_human_stop_blocks_apply_even_in_apply_mode(engine, monkeypatch):
    _mode(engine, "apply", human_stop=True)
    vs = _run(engine, default=GOOD, monkeypatch=monkeypatch)
    assert not any(v.applied for v in vs) and _rows(engine, ParameterValue) == []


def test_tighten_applies_in_tighten_only_but_loosen_does_not(engine, monkeypatch):
    _mode(engine, "tighten_only")
    vs = _run(engine, per_key={KEY: BAD, "rotation_min_score_delta": GOOD}, monkeypatch=monkeypatch)
    by = _by_key(vs)
    assert by[KEY].direction == "tighten" and by[KEY].applied
    assert get_param(KEY, engine=engine).value == 6.0
    assert by["rotation_min_score_delta"].direction == "loosen" and not by["rotation_min_score_delta"].applied


def test_off_apply_modes_record_tighten_without_applying(engine, monkeypatch):
    _mode(engine, "dry_run")
    v = _by_key(_run(engine, per_key={KEY: BAD}, monkeypatch=monkeypatch))[KEY]
    assert v.direction == "tighten" and not v.applied and _rows(engine, ParameterValue) == []


def test_tighten_trigger_cusum_and_negative_evidence():
    assert pe.tighten_trigger(band_series(KEY, [], horizon=63, mult=1.0)) == (False, "no_data")
    fire, why = pe.tighten_trigger(band_series(KEY, BAD, horizon=63, mult=1.0))
    assert fire and why
    assert pe.tighten_trigger(band_series(KEY, GOOD, horizon=63, mult=1.0)) == (False, "ok")


# ── budgets ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_one_loosening_in_flight_blocks_second(engine, monkeypatch):
    _mode(engine, "apply")
    vs = _run(engine, default=GOOD, monkeypatch=monkeypatch)
    assert sum(v.applied for v in vs) == 1
    blocked = [v for v in vs if v.direction == "hold" and v.conditions.get("gate", {}).get("none_in_flight") is False]
    assert blocked


def test_quarter_quota(engine):
    with sessionmaker(bind=engine)() as s:
        at = NOW - timedelta(days=10)                                   # this quarter, rolled back: no longer in flight
        s.add(ParameterChange(key="rotation_min_score_delta", from_value_json=2.0, to_value_json=1.5,
                              direction="loosen", verdict="loosen", applied_at=at, rolled_back_at=at + timedelta(days=2),
                              created_at=at, window_series_json={}))
        s.commit()
        gate = pe.budget_gate(s, REG[KEY], NOW, engine)
        assert gate["none_in_flight"] is True and gate["quarter_quota_ok"] is False
        assert pe.budget_gate(s, REG[KEY], datetime(2027, 1, 5, tzinfo=timezone.utc), engine)["quarter_quota_ok"] is True


def test_trial_budget_counts_strategy_trials(engine):
    with sessionmaker(bind=engine)() as s:
        for i in range(40):
            s.add(StrategyTrial(params_hash=f"h{i}", family="f", params_json="{}", first_eval_at=NOW, last_eval_at=NOW,
                                n_evals=1, status="rejected"))
        s.commit()
        gate = pe.budget_gate(s, REG[KEY], NOW, engine)
    assert gate["trial_budget_ok"] is False


def test_cooldown_from_evidence_clock(engine):
    record_value(KEY, 5.5, "human", engine=engine, now=NOW - timedelta(days=10))
    with sessionmaker(bind=engine)() as s:
        assert pe.budget_gate(s, REG[KEY], NOW, engine)["cooldown_ok"] is False
        assert pe.budget_gate(s, REG[KEY], NOW + timedelta(days=60), engine)["cooldown_ok"] is True


# ── G9 rollback / degrade ────────────────────────────────────────────────────────────────────────────────────────
def _apply_one(engine, monkeypatch, now=NOW):
    _mode(engine, "apply")
    _run(engine, per_key={KEY: GOOD}, now=now, monkeypatch=monkeypatch)
    return _rows(engine, ParameterChange, key=KEY)[0]


def test_rollback_on_cusum_alarm_writes_rollback_version(engine, monkeypatch):
    _apply_one(engine, monkeypatch)
    sent = []
    later = NOW + timedelta(days=7)
    vs = _run(engine, per_key={KEY: {5.0: stream(-0.03, 0.005, 40, 5), "*": GOOD}}, now=later, notify=lambda m, **k: sent.append(m),
              monkeypatch=monkeypatch)
    ch = _rows(engine, ParameterChange, key=KEY)[0]
    assert ch.rolled_back_at is not None
    assert get_param(KEY, engine=engine).value == 5.5
    assert _rows(engine, ParameterValue, key=KEY)[-1].source == "rollback"
    assert "rollback" in sent and len(_rows(engine, CharterEvent, kind="rollback")) == 1
    assert vs is not None


def test_no_rollback_when_monitor_series_is_healthy(engine, monkeypatch):
    _apply_one(engine, monkeypatch)
    _run(engine, per_key={KEY: GOOD}, now=NOW + timedelta(days=7), monkeypatch=monkeypatch)
    assert _rows(engine, ParameterChange, key=KEY)[0].rolled_back_at is None


def test_rollback_cooldown_two_quarters(engine, monkeypatch):
    _apply_one(engine, monkeypatch)
    _run(engine, per_key={KEY: {5.0: stream(-0.03, 0.005, 40, 5), "*": GOOD}}, now=NOW + timedelta(days=7), monkeypatch=monkeypatch)
    with sessionmaker(bind=engine)() as s:
        assert pe.budget_gate(s, REG[KEY], NOW + timedelta(days=100), engine)["no_rollback_cooldown"] is False
        assert pe.budget_gate(s, REG[KEY], NOW + timedelta(days=200), engine)["no_rollback_cooldown"] is True


def test_two_rollbacks_in_last_four_degrade_to_tighten_only(engine, monkeypatch):
    _mode(engine, "apply")
    with sessionmaker(bind=engine)() as s:
        for i, rolled in enumerate((True, False, True, False)):
            at = NOW - timedelta(days=400 - 100 * i)
            s.add(ParameterChange(key=KEY, from_value_json=5.5, to_value_json=5.0, direction="loosen", verdict="loosen",
                                  applied_at=at, rolled_back_at=at + timedelta(days=5) if rolled else None,
                                  created_at=at, window_series_json={}))
        s.commit()
    sent = []
    with sessionmaker(bind=engine)() as s:
        assert pe.maybe_degrade(s, NOW, lambda m, **k: sent.append(m)) is True
        s.commit()
    st = _rows(engine, CharterState)[0]
    assert st.mode == "tighten_only" and "2 of last 4" in st.reason
    assert sent == ["degrade"] and len(_rows(engine, CharterEvent, kind="degrade")) == 1


def test_one_rollback_in_last_four_does_not_degrade(engine):
    _mode(engine, "apply")
    with sessionmaker(bind=engine)() as s:
        for i in range(4):
            at = NOW - timedelta(days=400 - 100 * i)
            s.add(ParameterChange(key=KEY, from_value_json=5.5, to_value_json=5.0, direction="loosen", verdict="loosen",
                                  applied_at=at, rolled_back_at=at if i == 0 else None, created_at=at,
                                  window_series_json={}))
        s.commit()
        assert pe.maybe_degrade(s, NOW, lambda *a, **k: None) is False


# ── failure rules ────────────────────────────────────────────────────────────────────────────────────────────────
def test_db_failure_raises(monkeypatch):
    eng = create_engine("sqlite:///:memory:")           # no tables at all
    monkeypatch.setattr(pe, "evaluate_key", make_evaluator({}, GOOD))
    with pytest.raises(Exception):
        pe.run_once(USER, eng, NOW, closes_provider=closes_provider())


def test_missing_charter_state_row_never_applies(engine, monkeypatch):
    vs = _run(engine, default=GOOD, monkeypatch=monkeypatch)             # no charter_state row
    assert not any(v.applied for v in vs) and _rows(engine, ParameterValue) == []


def test_closes_failure_blocks_loosening(engine, monkeypatch):
    _mode(engine, "apply")
    monkeypatch.setattr(pe, "evaluate_key", make_evaluator({KEY: GOOD}))
    def boom(ticker, days=None):
        raise RuntimeError("no market data")
    vs = pe.run_once(USER, engine, NOW, closes_provider=boom)
    v = _by_key(vs)[KEY]
    assert not v.applied and v.conditions["regime"] == "not_measurable"


# ── zero-effect simulation ───────────────────────────────────────────────────────────────────────────────────────
def test_zero_effect_false_loosen_rate_within_alpha():
    rng = np.random.default_rng(20261019)
    alpha = loosening_alpha(40)
    hits = sum(confidence_sequence_any_time_loosen(rng.normal(0, 0.02, 252), alpha, 0.025) for _ in range(2000))
    assert hits / 2000 <= alpha * 1.5
