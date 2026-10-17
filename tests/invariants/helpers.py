"""Shared AST/grep helpers for invariant tests. / 不變量測試共用的 AST/grep 工具。"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def py_files():
    return sorted(SRC.rglob("*.py"))


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def unresolved_src_imports():
    """(file, module) pairs importing a `src.*` module that does not exist on disk."""
    bad = set()
    for p in py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            bad.add((rel(p), "<syntax error>"))
            continue
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 and n.module.startswith("src"):
                mods.append(n.module)
            elif isinstance(n, ast.Import):
                mods += [a.name for a in n.names if a.name.startswith("src")]
            for m in mods:
                f = REPO / Path(*m.split("."))
                if not (f.with_suffix(".py").exists() or f.is_dir()):
                    bad.add((rel(p), m))
    return bad


ORDER_CALL_RE = re.compile(r"\.(execute_order|place_order|place_close|place_trade)\(|(?:etoro|broker)\w*\.close_position\(")


def order_call_files():
    out = {}
    for p in py_files():
        n = len(ORDER_CALL_RE.findall(p.read_text(encoding="utf-8")))
        if n:
            out[rel(p)] = n
    return out


CONF_LITERAL_RE = re.compile(r"""["']confidence["']\s*:\s*\d+(\.\d+)?""")


def hardcoded_confidence_counts(files):
    out = {}
    for f in files:
        t = (REPO / f).read_text(encoding="utf-8")
        n = len(CONF_LITERAL_RE.findall(t))
        if n:
            out[f] = n
    return out


# Matches set_setting(, settings_repo.set(, save_setting( / 涵蓋三種寫入實盤設定的寫法
EVOLUTION_WRITE_RE = re.compile(r"set_setting\(|settings_repo\.set\(|save_setting\(")


def evolution_files_calling_set_setting():
    out = set()
    for p in py_files():
        if re.search(r"evolution|synthesis|canary", str(p)) and EVOLUTION_WRITE_RE.search(p.read_text(encoding="utf-8")):
            out.add(rel(p))
    return out


def executor_call_sites():
    """{file: count} of AST Call nodes whose attribute is `evaluate_and_execute_trade` (docstrings/comments excluded).
    以 AST 計算呼叫 `evaluate_and_execute_trade` 的 Call 節點（不含 docstring/註解）。"""
    out = {}
    for p in py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        n = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "evaluate_and_execute_trade"
        )
        if n:
            out[rel(p)] = n
    return out
