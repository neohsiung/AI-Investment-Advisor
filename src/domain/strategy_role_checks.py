"""Role predicates for the services that used to test strategy names by substring (friction, trend hysteresis,
unified risk gateway). One place decides which way an UNKNOWN name leans, and logs it.
原本以子字串判斷策略名的服務（摩擦、趨勢遲滯、統一風控閘門）改呼叫這裡；未知名稱偏向哪一邊只在此決定並記錄。

Direction for a name that ``strategy_names`` does not know (always the stricter one):
  * routine rebalance (friction hurdle applies)  -> True
  * emergency stop / deploy / deadband exemption / hysteresis routine sell -> False (no exemption)
Empty, None and the ledger label are known "unnamed" forms and never warn.
"""
import logging

from src.domain import strategy_names as sn

logger = logging.getLogger(__name__)


def unknown_strategy(name) -> bool:
    return not sn.is_known(name)


def _warn_unknown(name, check: str) -> None:
    logger.warning(
        "[StrategyRoles] _unknown_strategy=True name=%r check=%s: not in strategy_names.universe(); "
        "treated on the stricter side. Register the name or fix the producer. / 未登記的策略名，已採較嚴方向。",
        name, check,
    )


def is_emergency_stop(name) -> bool:
    if unknown_strategy(name):
        _warn_unknown(name, "emergency_stop")
    return sn.has_role(name, sn.EMERGENCY_STOP_EXEMPT)


def is_routine_rebalance(name) -> bool:
    if unknown_strategy(name):
        _warn_unknown(name, "routine_rebalance")
    return sn.has_role(name, sn.FRICTION_ROUTINE_REBALANCE, unknown=True)


def is_deploy(name) -> bool:
    if unknown_strategy(name):
        _warn_unknown(name, "deploy")
    return sn.has_role(name, sn.FRICTION_DEPLOY)


def is_deadband_exempt(name) -> bool:
    """Empty name is exempt (kept from the old ``not strat`` branch); an unknown name is not."""
    if not str(name or ""):
        return True
    if unknown_strategy(name):
        _warn_unknown(name, "deadband_exempt")
    return sn.has_role(name, sn.TREND_DEADBAND_EXEMPT)


def is_hysteresis_routine_sell(name) -> bool:
    if unknown_strategy(name):
        _warn_unknown(name, "hysteresis_routine_sell")
    return sn.has_role(name, sn.HYSTERESIS_ROUTINE_SELL)
