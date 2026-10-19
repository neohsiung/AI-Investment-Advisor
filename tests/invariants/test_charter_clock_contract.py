"""Charter test-clock contract (plan §1 item 6), checked by AST.
New charter functions take `now`/`today`, bind time as `:now`, never call SQL NOW()/func.now() and never rely on
a column server_default. Only the task shells in src/workflow/charter_tasks.py may read the wall clock.
測試時鐘契約：章程函式收 now/today、SQL 只用 :now 綁定、不用 NOW()/func.now()、不靠 server_default；
只有 charter_tasks.py 的任務外殼可讀牆上時鐘。

Each later charter milestone appends its modules to CHARTER_MODULES. / 後續里程碑把新模組加進 CHARTER_MODULES。
"""
import ast
import re
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parents[2]

CHARTER_MODULES = [
    "src/services/marginal_band_evaluator.py",
    "src/services/param_policy.py",
    "src/services/parameter_engine.py",
    "src/evaluation/regime.py",
    "src/workflow/charter_tasks.py",
    "src/services/charter_digest_service.py",
]

_SQL_NOW = re.compile(r"\bnow\s*\(\s*\)", re.IGNORECASE)
_CLOCK_ATTRS = {"now", "utcnow", "today"}
_CLOCK_PARAMS = {"now", "today"}


def _docstring_nodes(tree: ast.AST) -> set:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def violations_in_source(source: str, filename: str) -> List[str]:
    tree = ast.parse(source, filename=filename)
    docs = _docstring_nodes(tree)
    out: List[str] = []

    def visit(node: ast.AST, accepts_clock: bool) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            names = {p.arg for p in a.posonlyargs + a.args + a.kwonlyargs}
            accepts_clock = bool(names & _CLOCK_PARAMS)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                and _SQL_NOW.search(node.value):
            out.append(f"{filename}:{node.lineno}: SQL NOW() in string literal; bind :now instead")
        if isinstance(node, ast.keyword) and node.arg == "server_default":
            out.append(f"{filename}:{getattr(node.value, 'lineno', 0)}: server_default; set the column explicitly")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            f = node.func
            if f.attr == "now" and isinstance(f.value, ast.Name) and f.value.id == "func":
                out.append(f"{filename}:{node.lineno}: func.now(); bind :now instead")
            elif f.attr in _CLOCK_ATTRS and isinstance(f.value, ast.Name) and f.value.id in ("datetime", "date") \
                    and not accepts_clock:
                out.append(f"{filename}:{node.lineno}: {f.value.id}.{f.attr}() in a function without a now/today parameter")
        for child in ast.iter_child_nodes(node):
            visit(child, accepts_clock)

    visit(tree, False)
    return out


def test_charter_modules_obey_clock_contract():
    problems: List[str] = []
    for rel in CHARTER_MODULES:
        path = REPO / rel
        assert path.exists(), f"CHARTER_MODULES lists a missing file: {rel}"
        problems += violations_in_source(path.read_text(encoding="utf-8"), rel)
    assert not problems, "clock contract violated:\n" + "\n".join(problems)
