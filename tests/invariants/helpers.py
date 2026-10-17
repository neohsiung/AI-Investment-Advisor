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


def evolution_files_calling_set_setting():
    out = set()
    for p in py_files():
        if re.search(r"evolution|synthesis|canary", str(p)) and "set_setting(" in p.read_text(encoding="utf-8"):
            out.add(rel(p))
    return out
