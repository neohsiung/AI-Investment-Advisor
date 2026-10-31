"""workflow_service must not turn an unreadable order quantity into a plausible one ($100, or '5%' -> 5.0).
workflow_service 不得把讀不到的數量變成看似合理的數字。"""
import ast
import inspect

from src.services import workflow_service as mod


def test_no_quantity_fallback_literal_in_workflow_service():
    tree = ast.parse(inspect.getsource(mod))
    offenders = []
    for n in ast.walk(tree):
        assigns_qty_val = isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "qty_val" for t in n.targets)
        if assigns_qty_val and isinstance(n.value, ast.Constant) and isinstance(n.value.value, (int, float)):
            offenders.append(n.lineno)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "float":
            seg = ast.unparse(n)
            if ".replace('%'" in seg or '.replace("%"' in seg:
                offenders.append(n.lineno)
    assert offenders == [], f"quantity fallback / percent stripping at lines {offenders}"


def test_unparseable_quantity_skips_the_order_and_is_marked(caplog):
    import logging

    from src.agents.action_extractor import quantity_or_skip as skip_unreadable_quantity
    with caplog.at_level(logging.WARNING):
        assert skip_unreadable_quantity({"ticker": "AAPL", "action": "BUY", "quantity": "5%"}, "T") is None
        assert skip_unreadable_quantity({"ticker": "AAPL", "action": "BUY", "quantity": None}, "T") is None
        assert skip_unreadable_quantity({"ticker": "AAPL", "action": "BUY", "quantity": "12"}, "T") == 12.0
    assert sum("quantity_unparseable" in r.getMessage() for r in caplog.records) == 2
