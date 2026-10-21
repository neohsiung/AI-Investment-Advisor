"""G6/G9 on real Postgres: the daily engine run, apply mode, CUSUM rollback with cooldown, and degrade.
G6/G9 在真實 Postgres：每日引擎、apply 模式、CUSUM 回滾與冷卻、降級。

dry_run uses the REAL evaluate_key (empty evidence tables); the apply-mode tests replace evaluate_key with synthetic
band series so the DB writes of the engine are what is under test.
dry_run 用真實 evaluate_key（證據表為空）；apply 模式測試以合成序列取代，檢驗的是引擎的資料庫寫入。
"""
from datetime import timedelta

import pytest
from sqlalchemy import text

from src.services import parameter_engine as pe
from src.services.param_policy import get_param
from tests.charter_synth import flat_closes, make_evaluator, stream

from .factories import USER_ID, set_charter_state

pytestmark = pytest.mark.charter_e2e

KEY = "batch_deploy_min_confidence"
KEY2 = "rotation_min_score_delta"
KEY3 = "rotation_min_holding_days"
GOOD = stream(0.012, 0.006, 140, 11)
BAD = stream(-0.03, 0.005, 40, 5)


def _closes(closes_provider):
    closes_provider.set("SPY", flat_closes(700))
    return closes_provider


def _scalar(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def test_dry_run_day_writes_verdicts_for_every_adaptive_key_and_no_values(pg_engine, frozen_clock, closes_provider):
    verdicts = pe.run_once(USER_ID, pg_engine, frozen_clock.now(), closes_provider=_closes(closes_provider))
    assert len(verdicts) == 3 and not any(v.applied for v in verdicts)
    assert _scalar(pg_engine, "SELECT count(*) FROM charter_events WHERE kind = 'verdict'") == 3
    assert _scalar(pg_engine, "SELECT count(*) FROM parameter_changes") == 3
    assert _scalar(pg_engine, "SELECT count(*) FROM parameter_changes WHERE applied_at IS NOT NULL") == 0
    assert _scalar(pg_engine, "SELECT count(*) FROM parameter_values") == 0


def test_apply_mode_genuine_effect_writes_engine_version(pg_engine, frozen_clock, closes_provider, monkeypatch,
                                                         notify_sink):
    set_charter_state(pg_engine, "apply")
    monkeypatch.setattr(pe, "evaluate_key", make_evaluator({KEY: GOOD}))
    pe.run_once(USER_ID, pg_engine, frozen_clock.now(), notify=notify_sink, closes_provider=_closes(closes_provider))
    with pg_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT version, source, value_json, change_id FROM parameter_values WHERE key = :k"), {"k": KEY}).one()
    assert (row.version, row.source, float(row.value_json)) == (1, "engine", 5.0) and row.change_id is not None
    assert get_param(KEY, engine=pg_engine).value == 5.0
    assert _scalar(pg_engine, "SELECT count(*) FROM charter_events WHERE kind = 'apply'") == 1
    assert [m for m, _ in notify_sink.messages] == ["apply"]


def _loosen_then_break(pg_engine, clock, closes, monkeypatch, key, *, break_after_days=7):
    """Apply a loosening of `key`, then feed a collapsing band and run again."""
    monkeypatch.setattr(pe, "evaluate_key", make_evaluator({key: GOOD}))
    pe.run_once(USER_ID, pg_engine, clock.now(), closes_provider=closes)
    clock.advance(days=break_after_days)
    cur = get_param(key, engine=pg_engine).value
    grid = {5.5: 5.0, 2.0: 1.5, 5: 3.0}
    monkeypatch.setattr(pe, "evaluate_key", make_evaluator({key: {grid[2.0 if key == KEY2 else 5.5 if key == KEY else 5]: BAD, "*": GOOD}}))
    pe.run_once(USER_ID, pg_engine, clock.now(), closes_provider=closes)
    return cur


def test_cusum_after_loosening_rolls_back_and_cools_down(pg_engine, frozen_clock, closes_provider, monkeypatch):
    set_charter_state(pg_engine, "apply")
    closes = _closes(closes_provider)
    cur = _loosen_then_break(pg_engine, frozen_clock, closes, monkeypatch, KEY)
    assert cur == 5.0                                                        # it was loosened first
    assert get_param(KEY, engine=pg_engine).value == 5.5                     # then rolled back
    assert _scalar(pg_engine, "SELECT source FROM parameter_values WHERE key = :k ORDER BY version DESC LIMIT 1",
                   k=KEY) == "rollback"
    assert _scalar(pg_engine, "SELECT count(*) FROM charter_events WHERE kind = 'rollback'") == 1
    # two-quarter cooldown: strong evidence 100 days later still does not loosen KEY again
    frozen_clock.advance(days=100)
    monkeypatch.setattr(pe, "evaluate_key", make_evaluator({KEY: GOOD}))
    vs = pe.run_once(USER_ID, pg_engine, frozen_clock.now(), closes_provider=closes)
    assert not [v for v in vs if v.key == KEY][0].applied
    assert get_param(KEY, engine=pg_engine).value == 5.5


def test_two_rollbacks_in_last_four_degrade_to_tighten_only(pg_engine, frozen_clock, closes_provider, monkeypatch):
    set_charter_state(pg_engine, "apply")
    closes = _closes(closes_provider)
    _loosen_then_break(pg_engine, frozen_clock, closes, monkeypatch, KEY)
    assert _scalar(pg_engine, "SELECT mode FROM charter_state WHERE id = 1") == "apply"
    frozen_clock.advance(days=100)                                           # next calendar quarter: quota is free again
    _loosen_then_break(pg_engine, frozen_clock, closes, monkeypatch, KEY2)
    assert _scalar(pg_engine, "SELECT mode FROM charter_state WHERE id = 1") == "tighten_only"
    assert _scalar(pg_engine, "SELECT count(*) FROM charter_events WHERE kind = 'degrade'") == 1
    assert _scalar(pg_engine, "SELECT count(*) FROM parameter_changes WHERE rolled_back_at IS NOT NULL") == 2


def test_task_registered_and_beat_entry():
    from src.infrastructure.celery_app import app
    app.loader.import_default_modules()
    assert "src.workflow.charter_tasks.run_parameter_engine" in app.tasks
    assert app.conf.beat_schedule["charter-parameter-engine"]["task"] == "src.workflow.charter_tasks.run_parameter_engine"
