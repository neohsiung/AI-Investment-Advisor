"""ADR-005 / DD-2026-1031: the orders that must still work while the charter is frozen carry a whitelisted strategy_name,
and the names on the whitelist have only the producers we expect (an upper bound: a new producer needs a decision).
ADR-005 / DD-2026-1031：凍結期間仍須能下的單要帶白名單內的策略名；白名單名稱的產生端有上界，新增產生端要有決定。"""
import ast
import re
from pathlib import Path

from src.config.mission import load_mission

REPO = Path(__file__).resolve().parents[2]


def _calls_with_strategy(path: str, needle: str):
    """strategy_name constants of every evaluate_and_execute_trade call in ``path`` whose source mentions ``needle``."""
    src = (REPO / path).read_text(encoding="utf-8")
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "evaluate_and_execute_trade":
            if needle in (ast.get_source_segment(src, n) or ""):
                kw = {k.arg: k.value for k in n.keywords if k.arg}
                v = kw.get("strategy_name")
                out.append(v.value if isinstance(v, ast.Constant) else (ast.unparse(v) if v is not None else None))
    return out


def test_sentinel_hedge_buy_is_named_emergency_hedge():
    assert _calls_with_strategy("src/services/sentinel_service.py", "Auto-Hedging") == ["emergency_hedge"]


def test_dashboard_websocket_order_names_a_sell_position_exit():
    names = _calls_with_strategy("src/services/socket_manager.py", "[MANUAL] Dashboard Terminal Order")
    assert len(names) == 1 and names[0] is not None and "position_exit" in names[0]


def test_only_the_hedge_may_buy_under_a_whitelisted_name():
    """Upper bound: an ``evaluate_and_execute_trade`` call with a literal BUY and a whitelisted literal strategy_name
    must be the Sentinel emergency hedge. A new BUY producer under an exit name would slip through a freeze.
    上界：字面為 BUY 又帶白名單策略名的下單呼叫，只能是 Sentinel 緊急避險；其他就是新的買單產生端。"""
    wl = set(load_mission().frozen_exit_whitelist)
    offenders = []
    for path in list((REPO / "src").rglob("*.py")) + list((REPO / "services").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "evaluate_and_execute_trade":
                kw = {k.arg: k.value for k in n.keywords if k.arg}
                act, strat = kw.get("action"), kw.get("strategy_name")
                if (isinstance(act, ast.Constant) and str(act.value).upper() == "BUY"
                        and isinstance(strat, ast.Constant) and strat.value in wl and strat.value != "emergency_hedge"):
                    offenders.append(f"{path.relative_to(REPO).as_posix()}:{n.lineno} {strat.value}")
    assert offenders == [], f"BUY under an exit-only whitelisted name: {offenders}"


def test_emergency_hedge_has_exactly_one_producer():
    hits = []
    for path in list((REPO / "src").rglob("*.py")) + list((REPO / "services").rglob("*.py")):
        if re.search(r'strategy_name\s*=\s*"emergency_hedge"', path.read_text(encoding="utf-8")):
            hits.append(path.relative_to(REPO).as_posix())
    assert hits == ["src/services/sentinel_service.py"]
