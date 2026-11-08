"""strategy_role_checks: the role predicates the friction / trend / gateway services now call must give the same
answer as the substring rules they replace, on every name a decision rule can meet. The oracles are the OLD rules,
copied in verbatim; unknown names are the one deliberate difference and are asserted separately.
策略角色判定：摩擦、遲滯、閘門服務改呼叫的判定，須與被取代的子字串規則在所有已知名稱上答案一致；
舊規則逐字抄入當 oracle。
"""
import logging

import pytest

from src.domain import strategy_names as sn
from src.domain import strategy_role_checks as rc


def _sub(strat, keys):
    return any(k in strat for k in keys)


def _old(name):
    return str(name or "").lower()


def old_emergency(name):
    return _sub(_old(name), ("stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit",
                             "emergency_liquidation", "circuit_breaker"))


def old_routine(name):
    return _sub(_old(name), ("rebalance", "rotation", "churn", "routine"))


def old_deploy(name):
    return "deploy" in _old(name)


def old_deadband_exempt(name):
    strat = _old(name)
    return (not strat or strat == "emergency_hedge"  # trend code as merged with P4
            or _sub(strat, ("deploy", "cash", "dip", "staggered", "rebalance", "rotation", "tier", "approval",
                            "manual", "reporting", "pruning")))


def old_hysteresis_routine_sell(name):
    return _sub(_old(name), ("routine_rebalance", "routine_sell"))


# The domain: every known name, the unnamed forms, and the ATS default ledger label (a marker, not a strategy).
DOMAIN = sorted(sn.universe()) + ["", None, sn.UNNAMED_LEDGER_LABEL, "STOP_LOSS", " Emergency_Exit ", "   "]

CASES = [
    (rc.is_emergency_stop, old_emergency),
    (rc.is_routine_rebalance, old_routine),
    (rc.is_deploy, old_deploy),
    (rc.is_deadband_exempt, old_deadband_exempt),
    (rc.is_hysteresis_routine_sell, old_hysteresis_routine_sell),
]


@pytest.mark.parametrize("new,old", CASES, ids=[c[0].__name__ for c in CASES])
def test_predicate_equals_old_rule_on_every_known_name(new, old):
    for name in DOMAIN:
        assert new(name) == old(name), f"{new.__name__} disagrees with the old rule on {name!r}"


def test_emergency_hedge_is_deadband_exempt_through_the_role():
    assert sn.EMERGENCY_HEDGE in sn.TREND_DEADBAND_EXEMPT
    assert rc.is_deadband_exempt("emergency_hedge")


def test_unnamed_forms_are_known_and_not_flagged():
    for name in ("", None, "   ", sn.UNNAMED_LEDGER_LABEL):
        assert rc.unknown_strategy(name) is False
    assert rc.unknown_strategy("momentum_entry") is True
    assert rc.unknown_strategy("emergency_hedge") is False


def test_unnamed_order_is_not_routine_so_its_hurdle_exemption_survives():
    assert rc.is_routine_rebalance("") is False and rc.is_routine_rebalance(None) is False
    assert rc.is_routine_rebalance(sn.UNNAMED_LEDGER_LABEL) is False


@pytest.mark.parametrize("name", ["momentum_entry", "routine_momentum", "stop_loss_v2", "open_probe"])
def test_unknown_name_is_routine_stricter_and_not_a_member_of_any_exemption(name, caplog):
    with caplog.at_level(logging.WARNING):
        assert rc.is_routine_rebalance(name) is True           # hurdle applies (stricter)
        assert rc.is_emergency_stop(name) is False             # no fail-open exemption
        assert rc.is_deploy(name) is False
        assert rc.is_deadband_exempt(name) is False
        assert rc.is_hysteresis_routine_sell(name) is False
    assert any("_unknown_strategy" in r.getMessage() and name in r.getMessage() for r in caplog.records)


def test_known_name_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        rc.is_routine_rebalance("stop_loss")
        rc.is_emergency_stop("")
    assert not caplog.records


def test_has_role_unknown_parameter_is_the_only_new_behaviour():
    assert sn.has_role("momentum_entry", sn.FRICTION_ROUTINE_REBALANCE) is False
    assert sn.has_role("momentum_entry", sn.FRICTION_ROUTINE_REBALANCE, unknown=True) is True
    assert sn.has_role("", sn.FRICTION_ROUTINE_REBALANCE, unknown=True) is False
    assert sn.has_role(None, sn.FRICTION_ROUTINE_REBALANCE, unknown=True) is False
    assert sn.has_role(sn.UNNAMED_LEDGER_LABEL, sn.FRICTION_ROUTINE_REBALANCE, unknown=True) is False
    assert sn.has_role("stop_loss", sn.FRICTION_ROUTINE_REBALANCE, unknown=True) is False
