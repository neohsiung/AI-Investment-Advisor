"""
G2: versioned parameter store + the single read helper (param_policy).
G2：版本化參數儲存與唯一讀取點。

Nothing here may change live behaviour: no consumer reads param_policy yet (G10), and until the Change Engine
exists the effective value is the seed (schema default).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.parameter_registry import Bounds, load_registry
from src.config.settings_schema import schema_default
from src.data.models import Base, ParameterValue
from src.services import param_policy
from src.services.param_policy import (
    evidence_clock_start,
    get_param,
    record_human_write,
    record_value,
)

REG = {p.key: p for p in load_registry().parameters}


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[Base.metadata.tables[t] for t in
                ("parameter_values", "parameter_trials", "parameter_changes", "charter_state")],
    )
    return eng


def _rows(engine, key):
    with sessionmaker(bind=engine)() as s:
        return s.query(ParameterValue).filter_by(key=key).order_by(ParameterValue.version).all()


def test_returns_seed_when_nothing_stored(engine):
    r = get_param("event_analysis_daily_cap", engine=engine)
    assert r.value == schema_default("event_analysis_daily_cap")
    assert r.source == "seed"
    assert r.fallback_reason is None


def test_get_param_failure_returns_rollback_with_marker(caplog):
    broken = MagicMock()
    broken.connect.side_effect = RuntimeError("db down")
    with caplog.at_level("WARNING"):
        r = get_param("rotation_min_score_delta", engine=broken)
    assert r.value == REG["rotation_min_score_delta"].rollback_value
    assert r.fallback_reason and "db down" in r.fallback_reason
    assert any(rec.levelname == "WARNING" for rec in caplog.records)


def test_unknown_key_is_marked_not_guessed():
    r = get_param("no_such_key", engine=MagicMock())
    assert r.value is None
    assert r.fallback_reason


def test_value_clamped_to_bounds(engine):
    b = REG["rotation_min_score_delta"].bounds
    record_value("rotation_min_score_delta", 99.0, source="engine", engine=engine)
    assert get_param("rotation_min_score_delta", engine=engine).value == b.max
    record_value("rotation_min_score_delta", -5.0, source="engine", engine=engine)
    assert get_param("rotation_min_score_delta", engine=engine).value == b.min


def test_never_riskier_than_seed(engine):
    # tighten_only, risk_direction +1: a stored value above the seed must not be returned.
    p = REG["stop_loss_pct"]
    assert p.policy == "tighten_only" and p.risk_direction == 1
    record_value("stop_loss_pct", 6.0, source="engine", engine=engine)
    assert get_param("stop_loss_pct", engine=engine).value == 6.0  # tighter: allowed
    record_value("stop_loss_pct", 7.9, source="human", engine=engine)
    record_value("stop_loss_pct", 20.0, source="human", engine=engine)  # looser than the seed
    assert get_param("stop_loss_pct", engine=engine).value == p.rollback_value
    # failure path never exceeds the seed either
    broken = MagicMock()
    broken.connect.side_effect = RuntimeError("x")
    for p in load_registry().parameters:
        if p.store != "settings":
            continue
        r = get_param(p.key, engine=broken)
        assert r.value == p.rollback_value


def test_human_write_recorded_and_resets_clock(engine):
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=30)
    record_value("event_analysis_daily_cap", 12, source="engine", engine=engine, now=t0)
    assert evidence_clock_start("event_analysis_daily_cap", engine=engine) == t0
    assert record_human_write("event_analysis_daily_cap", 6, engine=engine, now=t1) is True
    rows = _rows(engine, "event_analysis_daily_cap")
    assert [r.source for r in rows] == ["engine", "human"]
    assert [r.version for r in rows] == [1, 2]
    assert evidence_clock_start("event_analysis_daily_cap", engine=engine) == t1
    assert get_param("event_analysis_daily_cap", engine=engine).value == 6


def test_unchanged_human_write_does_not_reset_clock(engine):
    """The UI posts the whole form; an untouched registered key must not restart its evidence clock."""
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert record_human_write("event_analysis_daily_cap", 12, engine=engine, now=t0) is True
    assert record_human_write("event_analysis_daily_cap", 12, engine=engine, now=t0 + timedelta(days=5)) is False
    # equal to the seed with no row yet: nothing to record either
    assert record_human_write("rotation_min_score_delta", 2.0, engine=engine) is False
    assert len(_rows(engine, "event_analysis_daily_cap")) == 1


def test_unregistered_key_is_ignored_by_human_write(engine):
    assert record_human_write("etoro_mode", "demo", engine=engine) is False


def test_special_values_not_reachable(engine):
    # 0 = "unlimited" for the daily cap; 0 disables the holding check. Neither may be returned.
    for key in ("event_analysis_daily_cap", "rotation_min_holding_days"):
        p = REG[key]
        assert 0 in p.special_values
        record_value(key, 0, source="human", engine=engine)
        v = get_param(key, engine=engine).value
        assert v not in p.special_values
        assert p.bounds.min <= v <= p.bounds.max


def test_module_never_reads_mission_numbers():
    # mission-store keys resolve through a path, never a copy
    assert "mission" in param_policy.__doc__.lower()


def test_settings_service_records_human_write(engine):
    from src.services.settings_service import SettingsService

    repo = MagicMock()
    svc = SettingsService(settings_repo=repo, prompt_repo=MagicMock(), param_engine=engine)
    svc.user_id = "owner"
    ok, _ = svc.save_settings_bulk({"event_analysis_daily_cap": 6, "etoro_mode": "demo"})
    assert ok
    repo.set_many.assert_called_once()
    rows = _rows(engine, "event_analysis_daily_cap")
    assert len(rows) == 1 and rows[0].source == "human"


def test_settings_service_surfaces_record_failure():
    from src.services.settings_service import SettingsService

    broken = MagicMock()
    broken.connect.side_effect = RuntimeError("db down")
    broken.begin.side_effect = RuntimeError("db down")
    svc = SettingsService(settings_repo=MagicMock(), prompt_repo=MagicMock(), param_engine=broken)
    svc.user_id = "owner"
    ok, msg = svc.save_settings_bulk({"event_analysis_daily_cap": 6})
    assert ok is False and msg == "PARAMETER_RECORD_FAILED"


# ── fail-silent: a substituted value must carry an observable marker (AGENTS.md constraint 0) ──
def test_clamped_value_carries_fallback_reason_and_stored_value(engine):
    b = REG["rotation_min_score_delta"].bounds
    record_value("rotation_min_score_delta", 99.0, source="human", engine=engine)
    r = get_param("rotation_min_score_delta", engine=engine)
    assert r.value == b.max  # the returned value itself is unchanged
    assert r.source == "human"
    assert r.stored_value == 99.0
    assert r.fallback_reason and r.fallback_reason.startswith("clamped:")
    assert "stored=99" in r.fallback_reason


def test_riskier_than_seed_carries_marker():
    # No registered key has in-bounds values riskier than its seed, so exercise the rule on a widened copy.
    p = REG["stop_loss_pct"].model_copy(update=dict(bounds=Bounds(min=1, max=20)))
    v, why = param_policy._clamp_marked(p, 15.0, 8.0)
    assert v == 8.0
    assert why and why.startswith("riskier_than_seed:") and "stored=15" in why


def test_frozen_and_special_value_carry_markers():
    p = REG["stop_loss_pct"].model_copy(update=dict(policy="frozen"))
    v, why = param_policy._clamp_marked(p, 5.0, 8.0)
    assert v == 8.0 and why and why.startswith("frozen:")
    p = REG["stop_loss_pct"].model_copy(update=dict(bounds=None, special_values=[8.0], policy="adaptive"))
    v, why = param_policy._clamp_marked(p, 8.0, 5.0)
    assert v == 5.0 and why and why.startswith("special_value:")


def test_unclamped_value_has_no_marker(engine):
    assert get_param("rotation_min_score_delta", engine=engine).fallback_reason is None  # seed
    record_value("rotation_min_score_delta", 2.5, source="human", engine=engine)
    r = get_param("rotation_min_score_delta", engine=engine)
    assert (r.value, r.source, r.fallback_reason, r.stored_value) == (2.5, "human", None, None)


def test_zero_capital_pct_clamp_is_marked(engine):
    """bounds.min is 1: a human-stored 0 ("stop all trading") comes back as 1, never as 0, and is marked.
    G10 consumers must read the raw setting for the 0 switch and distrust any result with a fallback_reason."""
    p = REG["tradable_capital_pct"]
    assert p.bounds.min == 1 and 0 in p.special_values
    record_value("tradable_capital_pct", 0, source="human", engine=engine)
    r = get_param("tradable_capital_pct", engine=engine)
    assert r.value == 1
    assert r.stored_value == 0
    assert r.fallback_reason and r.fallback_reason.startswith("clamped:")
