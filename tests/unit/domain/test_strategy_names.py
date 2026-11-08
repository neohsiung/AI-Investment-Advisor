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
    assert {sn.MACRO_VOLATILITY_HEDGE} == sn.SAFETY_CONTROLS - sn.SAFETY_REGISTERED
    assert len(sn.SAFETY_CONTROLS) == 12 and len(sn.SAFETY_REGISTERED) == 11


# Old rules copied verbatim, evaluated over the whole universe. / 舊規則逐字抄入，對整個名稱全集計算。
OLD_FRICTION_ROUTINE = lambda strat: _substring(strat, ("rebalance", "rotation", "churn", "routine"))        # noqa: E731
OLD_FRICTION_DEPLOY = lambda strat: "deploy" in strat                                                        # noqa: E731
OLD_FRICTION_OPEN = lambda strat: "open" in strat                                                            # noqa: E731
OLD_DEADBAND_EXEMPT = lambda strat: strat == "emergency_hedge" or _substring(strat, (                        # noqa: E731
    "deploy", "cash", "dip", "staggered", "rebalance", "rotation", "tier", "approval", "manual", "reporting",
    "pruning"))  # "emergency_hedge": the trend code's own P4 clause, now a member of the role
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
    expected = {
        "CHURN_COOLDOWN_EXEMPT": {"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit",
                                  "emergency_liquidation", "position_exit"},
        "STOP_LOSS_FAMILY": {"stop_loss", "trailing_stop_loss", "trailing_stop"},
        "INFERENCE_ROUTINE": {"rebalance", "batch_cash_deployment", "tactical_factor_rotation",
                              "automated_trading"},
        "NO_DYNAMIC_SCALING": {"cash_deployment", "rebalance_diversification", "portfolio_rebalance",
                               "concentration_rebalance"},
        "AUTO_EXEC_REBALANCE": {"cash_deployment", "rebalance_diversification", "portfolio_rebalance",
                                "concentration_rebalance", "capital_rotation"},
        "DAILY_LIMIT_REBALANCE": {"rebalance_diversification", "portfolio_rebalance", "concentration_rebalance",
                                  "tactical_factor_rotation"},
        "REPLACEMENT_PLAN_EXEMPT": {"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit",
                                    "macro_volatility_hedge"},
        "SAFETY_CONTROLS": {"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit", "position_exit",
                            "take_profit", "capital_rotation", "rebalance_diversification", "cash_deployment",
                            "stagnation_pruning", "macro_volatility_hedge", "benchmark_parking"},
    }
    for role_name, members in expected.items():
        assert set(getattr(sn, role_name)) == members, role_name


def test_auto_exec_buy_and_exit_labels_equal_the_dict_and_tuple_they_replaced():
    """Oracle copied from automated_trading_service before P6 moved them here. / 搬移前的原始字面值。"""
    assert set(sn.AUTO_EXEC_BUY) == {"pyramiding_scale_in", "macro_volatility_hedge", "tactical_factor_rotation"}
    assert sn.AUTO_EXIT_LABELS == {
        "stop_loss": "停損自動執行",
        "trailing_stop_loss": "移動停損自動執行",
        "trailing_stop": "移動停損自動執行",
        "take_profit": "停利自動執行",
        "capital_rotation": "換庫自動執行",
        "rebalance_diversification": "再平衡自動執行",
        "portfolio_rebalance": "再平衡自動執行",
        "concentration_rebalance": "再平衡自動執行",
        "stagnation_pruning": "停滯修剪自動執行",
        "macro_volatility_hedge": "避險減碼自動執行",
        "tactical_factor_rotation": "波段換倉自動執行",
    }
    # the stop-loss branch indexes the dict directly, so every member must have a label
    assert sn.STOP_LOSS_FAMILY <= sn.AUTO_EXIT_LABELS.keys()
