"""
Parameter registry invariants (G0) — the pre-registered charter surface for self-adjusting thresholds.
參數登錄檔不變量（G0）——自我調整門檻的事先登記面。

config/parameter_registry.yaml says, per threshold, which values the future Change Engine may ever move it
to. Nothing reads it at runtime yet (G2 adds the reader). This test pins the rules the charter relies on:
  * every settings-store key exists in the schema; rollback_value equals the schema default;
  * grid values are sorted, inside bounds, inside the schema's min/max, include rollback_value and never
    contain a special value (a step must never cross into "0 = unlimited / disabled");
  * class D (mechanisms that judge changes) can never be `adaptive`;
  * an `adaptive` parameter carries evidence (metric, horizons, min_n >= 30, counterfactual source);
  * a non-adaptive one explains itself (`untestable_reason`);
  * a mission-store parameter is a PATH into config/mission.yaml, never a copied number.
"""
from pathlib import Path

import pytest
import yaml

from src.config.mission import load_mission
from src.config.parameter_registry import (
    ParameterRegistry,
    load_registry,
    resolve_mission_path,
)

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "config" / "settings_schema.yaml"


def _schema():
    return {e["key"]: e for e in yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))["settings"]}


def _registry() -> ParameterRegistry:
    return load_registry()


def test_registry_loads_and_is_not_empty():
    assert len(_registry().parameters) >= 8


def test_keys_are_unique():
    keys = [p.key for p in _registry().parameters]
    assert len(keys) == len(set(keys))


def test_settings_keys_exist_in_schema_and_rollback_is_schema_default():
    schema = _schema()
    for p in _registry().parameters:
        if p.store != "settings":
            continue
        assert p.key in schema, f"{p.key} missing from settings_schema.yaml"
        assert p.rollback_value == schema[p.key]["default"], (
            f"{p.key}: rollback_value {p.rollback_value} != schema default {schema[p.key]['default']}"
        )


def test_grid_is_sorted_bounded_and_contains_rollback():
    schema = _schema()
    for p in _registry().parameters:
        if p.store != "settings" or not p.grid:
            continue
        assert p.grid == sorted(p.grid), f"{p.key}: grid not ascending"
        assert p.bounds.min <= min(p.grid) and max(p.grid) <= p.bounds.max, f"{p.key}: grid outside bounds"
        entry = schema[p.key]
        if "min" in entry:
            assert min(p.grid) >= entry["min"], f"{p.key}: grid below schema min"
        if "max" in entry:
            assert max(p.grid) <= entry["max"], f"{p.key}: grid above schema max"
        assert p.rollback_value in p.grid, f"{p.key}: rollback_value not on the grid"


def test_grid_never_contains_a_special_value():
    for p in _registry().parameters:
        assert not set(p.special_values) & set(p.grid), f"{p.key}: grid crosses a special value"


def test_class_d_is_never_adaptive():
    for p in _registry().parameters:
        if p.cls == "D":
            assert p.policy in ("tighten_only", "frozen"), f"{p.key}: class D must not self-loosen"


def test_adaptive_parameters_carry_evidence():
    for p in _registry().parameters:
        if p.policy != "adaptive":
            continue
        assert p.grid, f"{p.key}: adaptive needs a grid (bounds the trial count N)"
        ev = p.evidence
        assert ev is not None, f"{p.key}: adaptive needs evidence"
        assert ev.metric and ev.counterfactual_source
        assert set(ev.horizons_days) >= {5, 63}, f"{p.key}: both horizons required"
        assert ev.min_n >= 30, f"{p.key}: min_n below 30"
        assert p.cooldown_days >= 63, f"{p.key}: cooldown shorter than the long horizon"


def test_non_adaptive_parameters_explain_themselves():
    for p in _registry().parameters:
        if p.policy != "adaptive":
            assert p.untestable_reason, f"{p.key}: {p.policy} without untestable_reason"


def test_mission_parameters_are_paths_that_resolve():
    mission = load_mission()
    for p in _registry().parameters:
        if p.store != "mission":
            continue
        assert p.rollback_value is None and not p.grid, f"{p.key}: mission values must not be copied here"
        assert p.mission_path, f"{p.key}: mission store needs mission_path"
        resolve_mission_path(mission, p.mission_path)  # raises if the path is wrong


def test_resolve_mission_path_rejects_unknown_path():
    with pytest.raises(KeyError):
        resolve_mission_path(load_mission(), "promotion.no_such_field")


def test_risk_direction_is_plus_or_minus_one():
    for p in _registry().parameters:
        assert p.risk_direction in (-1, 1)


def test_loader_rejects_extra_fields(tmp_path):
    bad = tmp_path / "r.yaml"
    bad.write_text(
        "version: 1\nparameters:\n"
        "  - {key: x, store: settings, class: A, risk_direction: 1, policy: frozen, untestable_reason: t,"
        " rollback_value: 1, bogus: 1, bounds: {min: 0, max: 2}}\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_registry(str(bad))
