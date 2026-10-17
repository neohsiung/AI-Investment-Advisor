"""WP4: gate_policy may only TIGHTEN. / 自適應閘門只能收緊，不能放寬。"""
import math

import pytest

from src.services.gate_policy import GatePolicy, compute_gate_policy


def _summary(**over):
    s = {
        "approved_ceiling": {"trust": 1.0, "score_delta_floor": 0.5, "mode": "enforce"},
        "n": 5, "mean": 0.01, "se": 0.01,
        "k_breach": False, "validator_error_count": 0, "exec_failed_7d": 0,
    }
    s.update(over)
    return s


def test_healthy_returns_ceiling_exactly():
    p = compute_gate_policy(_summary())
    assert (p.trust, p.score_delta, p.effective_mode) == (1.0, 0.5, "enforce")
    assert p._insufficient_data is False


@pytest.mark.parametrize("ceiling_trust,expected", [(1.0, 0.5), (0.5, 0.0), (0.0, 0.0)])
def test_negative_evidence_drops_trust_one_level(ceiling_trust, expected):
    p = compute_gate_policy(_summary(
        approved_ceiling={"trust": ceiling_trust, "score_delta_floor": 0.0, "mode": "enforce"},
        n=10, mean=-0.05, se=0.01))
    assert p.trust == expected


def test_negative_evidence_needs_n_10():
    p = compute_gate_policy(_summary(n=9, mean=-0.5, se=0.01))
    assert p.trust == 1.0


def test_mean_plus_se_nonnegative_no_drop():
    p = compute_gate_policy(_summary(n=50, mean=-0.01, se=0.01))
    assert p.trust == 1.0


def test_negative_evidence_never_lowers_delta():
    p = compute_gate_policy(_summary(n=50, mean=-1.0, se=0.01))
    assert p.score_delta >= 0.5


@pytest.mark.parametrize("over", [
    {"k_breach": True}, {"validator_error_count": 1}, {"exec_failed_7d": 2}, {"exec_failed_7d": 5},
])
def test_flags_force_observe(over):
    assert compute_gate_policy(_summary(**over)).effective_mode == "observe"


def test_exec_failed_one_is_not_enough():
    assert compute_gate_policy(_summary(exec_failed_7d=1)).effective_mode == "enforce"


def test_mode_never_above_ceiling():
    p = compute_gate_policy(_summary(approved_ceiling={"trust": 1.0, "score_delta_floor": 0.0, "mode": "observe"}))
    assert p.effective_mode == "observe"


@pytest.mark.parametrize("trust", [0.0, 0.3, 0.5, 0.7, 1.0, 5.0, -1.0])
@pytest.mark.parametrize("floor", [0.0, 0.5, 1.5, 2.0, 9.0])
@pytest.mark.parametrize("mode", ["observe", "enforce"])
@pytest.mark.parametrize("ev", [
    {}, {"n": 20, "mean": -1.0, "se": 0.1}, {"k_breach": True}, {"exec_failed_7d": 3},
])
def test_only_tightens_property(trust, floor, mode, ev):
    p = compute_gate_policy(_summary(approved_ceiling={"trust": trust, "score_delta_floor": floor, "mode": mode}, **ev))
    assert p.trust in (0.0, 0.5, 1.0)
    assert p.trust <= max(0.0, min(1.0, trust))
    assert 0.0 <= p.score_delta <= 2.0
    assert p.score_delta >= min(floor, 2.0)
    assert p.effective_mode in ("observe", "enforce")
    if mode == "observe":
        assert p.effective_mode == "observe"


@pytest.mark.parametrize("bad", [
    {"n": None}, {"n": float("nan")}, {"mean": float("nan")}, {"se": None}, {"se": float("inf")},
    {"k_breach": None}, {"validator_error_count": None}, {"exec_failed_7d": float("nan")},
    {"approved_ceiling": None}, {"approved_ceiling": {"trust": 1.0}},
])
def test_missing_or_nan_is_most_conservative(bad):
    p = compute_gate_policy(_summary(**bad))
    assert (p.trust, p.score_delta, p.effective_mode) == (0.0, 2.0, "observe")
    assert p._insufficient_data is True


def test_empty_summary_and_non_dict():
    for s in ({}, None, "x"):
        p = compute_gate_policy(s)
        assert (p.trust, p.score_delta, p.effective_mode, p._insufficient_data) == (0.0, 2.0, "observe", True)


def test_result_is_frozen():
    p = compute_gate_policy(_summary())
    with pytest.raises(Exception):
        p.trust = 1.0  # type: ignore[misc]
    assert isinstance(p, GatePolicy)
    assert not math.isnan(p.score_delta)
