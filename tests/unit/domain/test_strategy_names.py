"""strategy_names: every role is a verbatim copy of the list it replaces (member for member), measured over every
name a decision rule can meet. The oracles below are the OLD rules, copied in on purpose: when a later PR deletes the
old tuple from a service, this file is what still proves nothing changed.
strategy_names：每個角色逐字等於它取代的清單；oracle 刻意抄進舊規則，之後舊清單被刪掉時仍能證明行為不變。"""
import pytest

from src.domain import strategy_names as sn


def _substring(name, keys):
    return any(k in name for k in keys)


def test_normalize_is_the_only_normalisation():
    assert sn.normalize("  Stop_Loss ") == "stop_loss"
    assert sn.normalize("") is None and sn.normalize(None) is None and sn.normalize("   ") is None


@pytest.mark.parametrize("raw,expected", [("stop_loss", True), (" STOP_LOSS", True), ("stop", False), ("", False),
                                          (None, False), ("stop_loss_x", False)])
def test_has_role_is_exact_membership_after_normalising(raw, expected):
    assert sn.has_role(raw, sn.STOP_LOSS_FAMILY) is expected


def test_all_and_legacy_are_disjoint_and_universe_is_their_union_with_proposals():
    assert not (sn.ALL & sn.LEGACY)
    assert sn.universe() == sn.ALL | sn.LEGACY | {f"proposal_{s}" for s in sn.PROPOSAL_SOURCES}
    assert sn.UNNAMED_LEDGER_LABEL.lower() not in sn.universe()


def test_registered_safety_set_is_the_fallback_set_minus_the_self_registered_hedge():
    assert sn.SAFETY_CONTROLS - sn.SAFETY_REGISTERED == {sn.MACRO_VOLATILITY_HEDGE}
    assert len(sn.SAFETY_CONTROLS) == 12 and len(sn.SAFETY_REGISTERED) == 11


# Old rules copied verbatim, evaluated over the whole universe. / 舊規則逐字抄入，對整個名稱全集計算。
OLD_FRICTION_ROUTINE = lambda strat: _substring(strat, ("rebalance", "rotation", "churn", "routine"))        # noqa: E731
OLD_FRICTION_DEPLOY = lambda strat: "deploy" in strat                                                        # noqa: E731
OLD_FRICTION_OPEN = lambda strat: "open" in strat                                                            # noqa: E731
OLD_DEADBAND_EXEMPT = lambda strat: _substring(strat, (                                                      # noqa: E731
    "deploy", "cash", "dip", "staggered", "rebalance", "rotation", "tier", "approval", "manual", "reporting",
    "pruning"))
OLD_EMERGENCY = lambda strat: _substring(strat, (                                                            # noqa: E731
    "stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit", "emergency_liquidation",
    "circuit_breaker"))
OLD_HYSTERESIS_ROUTINE_SELL = lambda strat: _substring(strat, ("routine_rebalance", "routine_sell"))        # noqa: E731


@pytest.mark.parametrize("role_name,oracle", [
    ("FRICTION_ROUTINE_REBALANCE", OLD_FRICTION_ROUTINE),
    ("FRICTION_DEPLOY", OLD_FRICTION_DEPLOY),
    ("TREND_DEADBAND_EXEMPT", OLD_DEADBAND_EXEMPT),
    ("EMERGENCY_STOP_EXEMPT", OLD_EMERGENCY),
    ("HYSTERESIS_ROUTINE_SELL", OLD_HYSTERESIS_ROUTINE_SELL),
])
def test_role_equals_the_old_substring_rule_over_every_known_name(role_name, oracle):
    role = getattr(sn, role_name)
    for name in sorted(sn.universe()):
        assert (name in role) == oracle(name), f"{role_name} disagrees with the old rule on {name!r}"


def test_the_old_open_keyword_matches_no_known_name_so_it_has_no_role():
    assert [n for n in sn.universe() if OLD_FRICTION_OPEN(n)] == []


def test_roles_that_were_exact_tuples_are_reproduced_member_for_member():
    assert sn.CHURN_COOLDOWN_EXEMPT == {"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit",
                                        "emergency_liquidation", "position_exit"}
    assert sn.STOP_LOSS_FAMILY == {"stop_loss", "trailing_stop_loss", "trailing_stop"}
    assert sn.INFERENCE_ROUTINE == {"rebalance", "batch_cash_deployment", "tactical_factor_rotation",
                                    "automated_trading"}
    assert sn.NO_DYNAMIC_SCALING == {"cash_deployment", "rebalance_diversification", "portfolio_rebalance",
                                     "concentration_rebalance"}
    assert sn.AUTO_EXEC_REBALANCE == sn.NO_DYNAMIC_SCALING | {"capital_rotation"}
    assert sn.DAILY_LIMIT_REBALANCE == {"rebalance_diversification", "portfolio_rebalance",
                                        "concentration_rebalance", "tactical_factor_rotation"}
    assert sn.REPLACEMENT_PLAN_EXEMPT == {"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit",
                                          "macro_volatility_hedge"}
    assert sn.SAFETY_CONTROLS == {"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit",
                                  "position_exit", "take_profit", "capital_rotation", "rebalance_diversification",
                                  "cash_deployment", "stagnation_pruning", "macro_volatility_hedge",
                                  "benchmark_parking"}


def test_roles_match_the_lists_still_in_the_services():
    """Until a later PR deletes the old tuples, the services' literal lists must equal the roles (no silent drift)."""
    import ast
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[3]

    # strategy_registry fallback + registration loop
    reg = (repo / "src/services/strategy_registry.py").read_text(encoding="utf-8")
    tree = ast.parse(reg)
    literals = [set(n.value for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str))
                for t in ast.walk(tree) if isinstance(t, (ast.Tuple, ast.List))]
    assert sn.SAFETY_CONTROLS in literals and sn.SAFETY_REGISTERED in literals

    ps = (repo / "src/services/proposal_shadow_service.py").read_text(encoding="utf-8")
    sets = [set(n.value for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str))
            for t in ast.walk(ast.parse(ps)) if isinstance(t, ast.Set)]
    assert sn.REPLACEMENT_PLAN_EXEMPT in sets
