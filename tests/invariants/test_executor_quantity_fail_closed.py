"""
`quantity = 1.0` in automated_trading_service.py was a silent fallback ("sell 1 share" / "$1 buy")
when the order size could not be resolved. The executor must fail closed instead
(return status=error, reason=quantity_unresolved). Do not reintroduce it.
automated_trading_service.py 不得再有 `quantity = 1.0`：無法解析數量時必須 fail-closed。
"""
import ast

from tests.invariants.helpers import SRC


def test_executor_has_no_quantity_one_fallback():
    path = SRC / "services" / "automated_trading_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Constant) and n.value.value == 1.0
        and any(isinstance(t, ast.Name) and t.id == "quantity" for t in n.targets)
    ]
    assert not hits, (
        f"silent `quantity = 1.0` fallback present at line(s) {hits} of {path.name}; "
        "return {'status': 'error', 'reason': 'quantity_unresolved'} instead (WP5c-a)."
    )
