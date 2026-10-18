"""
Layering ratchet (M-B0): inward-only import direction, file-size ceiling, lazy-import ceiling.
分層棘輪（M-B0）：只准向內依賴、檔案行數上限、函式內延遲 import 上限。

Three measurements over `src/` and `services/`, all AST/line based (no production code is imported):
  1. layering edges — per-file imports that point the wrong way across the layers in LAYER_PREFIXES;
  2. oversize files — files over MAX_LINES lines; they may not grow, and no new one may appear;
  3. lazy imports   — total `import` statements inside function bodies; the total may not rise.

Today's counts live in `layering_baseline.json`. The test fails when a count rises or a new offender
appears, and also when the baseline is looser than reality (so the numbers only ever shrink).
Do NOT edit the JSON by hand to make a test pass — fix the code. After a clean-up, tighten it:

    .venv/bin/python -m tests.invariants.test_layering --update

`--update` refuses to raise any number (it only creates the file when absent, or shrinks it).
今日數字記在 `layering_baseline.json`；數字上升、出現新違規、或基準檔比現況寬鬆都會失敗。
禁止手改 JSON 讓測試通過；清理完成後用上方 `--update` 收緊（它拒絕調高任何數字）。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("layering_baseline.json")
SCAN_ROOTS = ("src", "services")
MAX_LINES = 1500

# Path-to-layer table: longest matching prefix wins. Until the folders are physically split
# (see transformation plan, Track B), this table IS the architecture. Module paths are the dotted
# name with dots turned into slashes, e.g. `src.services.foo` -> `src/services/foo`.
# 路徑對層級對照表：最長前綴優先。資料夾尚未實際拆分前，這張表就是架構定義。
LAYER_PREFIXES: dict[str, str] = {
    # entrypoints — things that receive a request or a tick and call into the application layer
    "services": "entrypoints",
    "src/api": "entrypoints",
    "src/workflow": "entrypoints",
    "src/setup_telegram_webhook": "entrypoints",
    "src/infrastructure/tasks": "entrypoints",  # Celery task bodies
    # application — use cases and orchestration
    "src/services": "application",
    "src/agents": "application",
    "src/evaluation": "application",
    "src/tracking": "application",
    "src/alerts": "application",
    "src/tools": "application",
    "src/plugins": "application",
    "src/prompts": "application",
    # domain — pure models, contracts and ports
    "src/domain": "domain",
    # adapters — persistence and external data
    "src/repositories": "adapters",
    "src/data": "adapters",
    # infrastructure — queues, caches, LLM gateway, telemetry; must hold no business logic
    "src/infrastructure": "infrastructure",
    # shared kernel — settings access and small utilities; importable from anywhere
    "src/config": "shared",
    "src/utils": "shared",
}

# importer layer -> imported layers that are forbidden. Rule id = "<importer>-><imported>".
# Entrypoints may import anything. `application->adapters/infrastructure` is deliberately NOT here yet:
# it is the later DIP milestone (ports in domain), and would only add noise before the ports exist.
# 進口層 -> 禁止被匯入的層。application->adapters 等待 domain.ports 建立後再收緊。
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "domain": ("application", "entrypoints", "adapters", "infrastructure"),
    "application": ("entrypoints",),
    "adapters": ("application", "entrypoints"),
    "infrastructure": ("application", "entrypoints"),
    "shared": ("application", "entrypoints", "adapters", "infrastructure", "domain"),
}


def layer_of(path_key: str) -> str | None:
    best = None
    for prefix, layer in LAYER_PREFIXES.items():
        if path_key == prefix or path_key.startswith(prefix + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, layer)
    return best[1] if best else None


def _source_files() -> list[Path]:
    out = []
    for root in SCAN_ROOTS:
        for p in (REPO / root).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            out.append(p)
    return sorted(out)


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def _module_exists(dotted: str) -> bool:
    f = REPO / Path(*dotted.split("."))
    return f.with_suffix(".py").exists() or f.is_dir()


def _imported_modules(node: ast.AST, importer: Path) -> list[str]:
    """Dotted first-party modules a single import node refers to. / 單一 import 節點指向的專案內模組。"""
    mods: list[str] = []
    if isinstance(node, ast.Import):
        mods = [a.name for a in node.names]
    elif isinstance(node, ast.ImportFrom):
        base = node.module or ""
        if node.level:  # relative import -> absolute, from the importer's package
            pkg = list(importer.relative_to(REPO).with_suffix("").parts[:-1])
            pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
            base = ".".join(pkg + ([node.module] if node.module else []))
        for a in node.names:  # `from src.services import foo` where foo is a submodule
            sub = f"{base}.{a.name}" if base else a.name
            mods.append(sub if _module_exists(sub) else base)
    return [m for m in mods if m.split(".")[0] in SCAN_ROOTS]


def measure() -> dict:
    edges: dict[str, list[str]] = {}
    lines: dict[str, int] = {}
    lazy_total = 0
    for p in _source_files():
        text = p.read_text(encoding="utf-8")
        n_lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        if n_lines > MAX_LINES:
            lines[_rel(p)] = n_lines
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        src_layer = layer_of(_rel(p).removesuffix(".py"))
        forbidden = FORBIDDEN.get(src_layer or "", ())
        found: set[str] = set()
        in_func: set[int] = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    if isinstance(n, (ast.Import, ast.ImportFrom)):
                        in_func.add(id(n))
        for n in ast.walk(tree):
            if not isinstance(n, (ast.Import, ast.ImportFrom)):
                continue
            if id(n) in in_func:
                lazy_total += 1
            for mod in _imported_modules(n, p):
                dst_layer = layer_of(mod.replace(".", "/"))
                if dst_layer in forbidden:
                    found.add(f"{src_layer}->{dst_layer}:{mod}")
        if found:
            edges[_rel(p)] = sorted(found)
    return {
        "max_lines": MAX_LINES,
        "violating_edges": dict(sorted(edges.items())),
        "oversize_files": dict(sorted(lines.items())),
        "lazy_imports_total": lazy_total,
    }


def load_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def regressions(base: dict, now: dict) -> list[str]:
    """Things that got worse. / 變糟的項目。"""
    out = []
    for f, es in now["violating_edges"].items():
        new = sorted(set(es) - set(base["violating_edges"].get(f, [])))
        out += [f"NEW layering edge {f}: {e}" for e in new]
    for f, n in now["oversize_files"].items():
        old = base["oversize_files"].get(f)
        if old is None:
            out.append(f"NEW oversize file {f}: {n} lines (> {MAX_LINES})")
        elif n > old:
            out.append(f"oversize file grew {f}: {old} -> {n} lines")
    if now["lazy_imports_total"] > base["lazy_imports_total"]:
        out.append(f"lazy imports rose: {base['lazy_imports_total']} -> {now['lazy_imports_total']}")
    return out


def stale(base: dict, now: dict) -> list[str]:
    """Baseline entries that are no longer true (fixed) — must be tightened. / 已改善但基準檔未收緊。"""
    out = []
    for f, es in base["violating_edges"].items():
        gone = sorted(set(es) - set(now["violating_edges"].get(f, [])))
        out += [f"fixed layering edge {f}: {e}" for e in gone]
    for f in base["oversize_files"]:
        if f not in now["oversize_files"]:
            out.append(f"no longer oversize: {f}")
    if now["lazy_imports_total"] < base["lazy_imports_total"]:
        out.append(f"lazy imports fell: {base['lazy_imports_total']} -> {now['lazy_imports_total']}")
    return out


def test_layering_does_not_regress():
    bad = regressions(load_baseline(), measure())
    assert not bad, "layering ratchet regressed (fix the code, do not raise the baseline):\n" + "\n".join(bad[:40])


def test_baseline_is_tight():
    gone = stale(load_baseline(), measure())
    assert not gone, "baseline is looser than reality — run `python -m tests.invariants.test_layering --update`:\n" + "\n".join(gone[:40])


def test_layer_table_covers_every_top_level_package():
    """A new top-level package must be assigned a layer, or it silently escapes the ratchet.
    新頂層套件必須歸層，否則會悄悄逃出棘輪。"""
    unmapped = sorted(
        _rel(p) for root in SCAN_ROOTS for p in (REPO / root).rglob("*.py")
        if "__pycache__" not in p.parts and layer_of(_rel(p).removesuffix(".py")) is None
        and p.name != "__init__.py"
    )
    assert not unmapped, f"files with no layer in LAYER_PREFIXES: {unmapped[:10]}"


def test_ratchet_logic_flags_worse_and_stale():
    """The comparator itself is tested on synthetic data so a broken ratchet cannot pass silently.
    用合成資料測比較器本身，避免棘輪壞掉卻靜默通過。"""
    base = {"violating_edges": {"a.py": ["x"]}, "oversize_files": {"b.py": 1600}, "lazy_imports_total": 10}
    worse = {"violating_edges": {"a.py": ["x", "y"], "c.py": ["z"]}, "oversize_files": {"b.py": 1601, "d.py": 1501},
             "lazy_imports_total": 11}
    assert len(regressions(base, worse)) == 5
    better = {"violating_edges": {}, "oversize_files": {}, "lazy_imports_total": 9}
    assert regressions(base, better) == [] and len(stale(base, better)) == 3
    assert regressions(base, base) == [] and stale(base, base) == []


def main(argv: list[str]) -> int:
    if argv != ["--update"]:
        print("usage: python -m tests.invariants.test_layering --update")
        return 2
    now = measure()
    if BASELINE.exists():
        bad = regressions(load_baseline(), now)
        if bad:
            print("REFUSED: --update never raises the baseline. Fix these first:")
            print("\n".join(bad[:40]))
            return 1
    BASELINE.write_text(json.dumps(now, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"baseline written: {sum(len(v) for v in now['violating_edges'].values())} edges, "
          f"{len(now['oversize_files'])} oversize files, {now['lazy_imports_total']} lazy imports")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
