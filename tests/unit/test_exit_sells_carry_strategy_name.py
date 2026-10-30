"""Safety exits must carry a charter-whitelisted strategy name (DD-2026-1031 stage 1).

Emergency liquidation and the Alert Hub one-tap close used to call ``evaluate_and_execute_trade`` without a
``strategy_name``; the executor then labelled the order ``AutomatedTrading``, indistinguishable from discretionary
webhook reductions. A frozen-gate that blocks non-exit sells (stage 2) could then not tell them apart.
緊急清倉與 Alert Hub 一鍵平倉必須帶白名單內的策略名，凍結閘門才分得出安全出場與主觀減碼。
"""
import ast
from pathlib import Path

from src.services.strategy_registry import StrategyRegistry

ROOT = Path(__file__).resolve().parents[2]
EXIT_NAMES = {"emergency_exit", "position_exit"}


def _sell_calls(rel_path: str):
    tree = ast.parse((ROOT / rel_path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "evaluate_and_execute_trade":
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            action = kw.get("action")
            if isinstance(action, ast.Constant) and action.value == "SELL":
                yield node.lineno, kw


def _names(rel_path: str, marker: str):
    """strategy_name constants of SELL calls whose rationale text contains ``marker``."""
    out = []
    for lineno, kw in _sell_calls(rel_path):
        if marker not in ast.unparse(kw.get("rationale", ast.Constant(""))):
            continue
        name = kw.get("strategy_name")
        out.append((lineno, name.value if isinstance(name, ast.Constant) else None))
    return out


def test_sentinel_emergency_liquidation_names_its_strategy():
    found = _names("src/services/sentinel_service.py", "Emergency Liquidation")
    assert found, "emergency liquidation SELL call not found"
    assert all(n in EXIT_NAMES for _, n in found), found


def test_alert_hub_manual_close_names_its_strategy():
    found = _names("src/services/actionable_alert_service.py", "manual emergency close")
    assert found, "manual close SELL call not found"
    assert all(n in EXIT_NAMES for _, n in found), found


def test_named_exits_remain_safety_controls():
    # The names chosen above must keep the same safety-control treatment in the executor.
    for name in EXIT_NAMES:
        assert StrategyRegistry.is_safety_control(name), name
