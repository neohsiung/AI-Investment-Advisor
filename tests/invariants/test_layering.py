"""
Layering ratchet (M-B0): inward-only import direction, file-size ceiling, lazy-import ceiling.
分層棘輪（M-B0）：只准向內依賴、檔案行數上限、函式內延遲 import 上限。

Three measurements over `src/` and `services/`, all AST/line based (no production code is imported):
  1. layering edges — per-file imports that point the wrong way across the layers in LAYER_PREFIXES;
  2. oversize files — files over MAX_LINES lines; they may not grow, and no new one may appear;
  3. lazy imports   — total `import` statements inside function bodies; the total may not rise.

Today's counts live in `layering_baseline.json`. The pytest gate BLOCKS only on regressions: a count that
rises or a new offender. A baseline that is merely looser than reality (someone cleaned up, or another PR
merged first) never blocks, so independent PRs do not fight over the JSON. Tightness is checked out of band:

    .venv/bin/python -m tests.invariants.test_layering --check-tight   # exit 1 + list when baseline is loose
    .venv/bin/python -m tests.invariants.test_layering --update        # tighten (never raises a number)

`scripts/ci_local.sh` prints `--check-tight` as a warning; a scheduled step may enforce it. You do NOT have to
run `--update` in a feature PR. Never edit the JSON by hand to make a test pass — fix the code.
The JSON is one key per line, sorted, with no stored totals (the lazy-import total is the sum of the
per-file counts), so concurrent edits to different files merge without conflict.
今日數字記在 `layering_baseline.json`。pytest 只在「退步」時阻擋：數字上升或出現新違規。基準檔比現況寬鬆
（清理了、或他 PR 先合併）不阻擋，獨立 PR 不再互搶 JSON。緊度另由 `--check-tight` 檢查（ci_local.sh 以
警告顯示，排程步驟可強制）；`--update` 收緊且拒絕調高。JSON 一鍵一行、排序、不存總數（延遲 import 總數
為各檔數字加總），並行修改不同檔案可乾淨合併。禁止手改 JSON 讓測試通過。
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
    lazy: dict[str, int] = {}
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
        lazy_here = 0
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
                lazy_here += 1
            for mod in _imported_modules(n, p):
                dst_layer = layer_of(mod.replace(".", "/"))
                if dst_layer in forbidden:
                    found.add(f"{src_layer}->{dst_layer}:{mod}")
        if lazy_here:
            lazy[_rel(p)] = lazy_here
        if found:
            edges[_rel(p)] = sorted(found)
    return {
        "max_lines": MAX_LINES,
        "violating_edges": dict(sorted(edges.items())),
        "oversize_files": dict(sorted(lines.items())),
        "lazy_imports": dict(sorted(lazy.items())),
    }


def lazy_total(d: dict) -> int:
    """Total function-level imports (the number that may not rise). / 函式內 import 總數（不得上升者）。"""
    return sum(d["lazy_imports"].values())


def dump_baseline(d: dict) -> str:
    """Stable, merge-friendly text: one key per line, sorted, no volatile totals. / 一鍵一行、排序、不含易變總數。"""
    def block(name: str, m: dict) -> str:
        if not m:
            return f'  "{name}": {{}}'
        body = ",\n".join(f"    {json.dumps(k)}: {json.dumps(m[k])}" for k in sorted(m))
        return f'  "{name}": {{\n{body}\n  }}'
    parts = [f'  "max_lines": {d["max_lines"]}'] + [
        block(n, d[n]) for n in ("violating_edges", "oversize_files", "lazy_imports")
    ]
    return "{\n" + ",\n".join(parts) + "\n}\n"


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
    if lazy_total(now) > lazy_total(base):
        out.append(f"lazy imports rose: {lazy_total(base)} -> {lazy_total(now)}")
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
    if lazy_total(now) < lazy_total(base):
        out.append(f"lazy imports fell: {lazy_total(base)} -> {lazy_total(now)}")
    return out


def test_layering_does_not_regress():
    bad = regressions(load_baseline(), measure())
    assert not bad, "layering ratchet regressed (fix the code, do not raise the baseline):\n" + "\n".join(bad[:40])


def test_layer_table_covers_every_top_level_package():
    """A new top-level package must be assigned a layer, or it silently escapes the ratchet.
    新頂層套件必須歸層，否則會悄悄逃出棘輪。"""
    unmapped = sorted(
        _rel(p) for root in SCAN_ROOTS for p in (REPO / root).rglob("*.py")
        if "__pycache__" not in p.parts and layer_of(_rel(p).removesuffix(".py")) is None
        and p.name != "__init__.py"
    )
    assert not unmapped, f"files with no layer in LAYER_PREFIXES: {unmapped[:10]}"


def _b(edges=None, over=None, lazy=None) -> dict:
    return {"max_lines": MAX_LINES, "violating_edges": edges or {}, "oversize_files": over or {},
            "lazy_imports": lazy or {}}


def test_ratchet_logic_flags_worse_and_stale():
    """The comparator itself is tested on synthetic data so a broken ratchet cannot pass silently.
    用合成資料測比較器本身，避免棘輪壞掉卻靜默通過。"""
    base = _b({"a.py": ["x"]}, {"b.py": 1600}, {"m.py": 10})
    worse = _b({"a.py": ["x", "y"], "c.py": ["z"]}, {"b.py": 1601, "d.py": 1501}, {"m.py": 11})
    assert len(regressions(base, worse)) == 5
    better = _b()
    assert regressions(base, better) == [] and len(stale(base, better)) == 3
    assert regressions(base, base) == [] and stale(base, base) == []


def test_baseline_tighter_than_reality_after_merge_does_not_block():
    """Failure mode 1: another PR merged first and removed modules, so this PR's merge result is tighter than the
    baseline it recorded. That is not a regression — the blocking check must pass (tightness is `--check-tight`).
    失敗模式 1：他 PR 先合併刪了模組，合併結果比本 PR 記錄的基準更緊，不是退步，阻擋檢查必須通過。"""
    base = _b({"a.py": ["x", "y"]}, {"b.py": 1600}, {"m.py": 10, "n.py": 5})
    merged = _b({"a.py": ["x"]}, {}, {"m.py": 10})
    assert regressions(base, merged) == []
    assert stale(base, merged)  # still reported, by --check-tight only


def test_rise_still_blocks():
    """The ratchet itself is unchanged: any rise or new offender is a regression, offsetting lazy moves net out.
    棘輪本身不變：任何上升或新增違規都失敗；延遲 import 以總數比較。"""
    base = _b({"a.py": ["x"]}, {"b.py": 1600}, {"m.py": 10})
    assert regressions(base, _b({"a.py": ["x", "y"]}, {"b.py": 1600}, {"m.py": 10}))
    assert regressions(base, _b({"a.py": ["x"]}, {"b.py": 1601}, {"m.py": 10}))
    assert regressions(base, _b({"a.py": ["x"]}, {"b.py": 1600}, {"m.py": 11}))
    assert regressions(base, _b({"a.py": ["x"]}, {"b.py": 1600}, {"m.py": 9, "k.py": 2}))
    assert regressions(base, _b({"a.py": ["x"]}, {"b.py": 1600}, {"m.py": 9, "k.py": 1})) == []


def test_baseline_file_is_merge_friendly():
    """Failure mode 2: a single volatile `lazy_imports_total` line conflicted in every PR touching the baseline.
    The file must be one key per line, sorted, with no stored total, so independent edits merge cleanly.
    失敗模式 2：單一易變的 total 行讓每個 PR 都衝突。檔案須一鍵一行、排序、不存總數。"""
    text = BASELINE.read_text(encoding="utf-8")
    assert "lazy_imports_total" not in text
    data = json.loads(text)
    assert text == dump_baseline(data)
    for key in ("violating_edges", "oversize_files", "lazy_imports"):
        assert list(data[key]) == sorted(data[key])
    assert all(len(line) < 400 for line in text.splitlines())


def test_check_tight_cli_reports_stale_without_pytest_blocking(tmp_path, monkeypatch, capsys):
    """`--check-tight` exits 1 and names the slack when the baseline is looser than reality; exits 0 when tight.
    `--check-tight` 在基準比現況寬鬆時回 1 並列出差距，緊貼時回 0。"""
    import tests.invariants.test_layering as mod
    f = tmp_path / "b.json"
    f.write_text(dump_baseline(_b({"a.py": ["x"]}, {}, {"m.py": 3})), encoding="utf-8")
    monkeypatch.setattr(mod, "BASELINE", f)
    monkeypatch.setattr(mod, "measure", lambda: _b())
    assert mod.main(["--check-tight"]) == 1
    assert "fixed layering edge a.py: x" in capsys.readouterr().out
    monkeypatch.setattr(mod, "measure", lambda: _b({"a.py": ["x"]}, {}, {"m.py": 3}))
    assert mod.main(["--check-tight"]) == 0


def main(argv: list[str]) -> int:
    if argv == ["--check-tight"]:
        gone = stale(load_baseline(), measure())
        if gone:
            print("baseline is looser than reality — run `python -m tests.invariants.test_layering --update`:")
            print("\n".join(gone[:40]))
            return 1
        print("baseline is tight")
        return 0
    if argv != ["--update"]:
        print("usage: python -m tests.invariants.test_layering --update | --check-tight")
        return 2
    now = measure()
    if BASELINE.exists():
        bad = regressions(load_baseline(), now)
        if bad:
            print("REFUSED: --update never raises the baseline. Fix these first:")
            print("\n".join(bad[:40]))
            return 1
    BASELINE.write_text(dump_baseline(now), encoding="utf-8")
    print(f"baseline written: {sum(len(v) for v in now['violating_edges'].values())} edges, "
          f"{len(now['oversize_files'])} oversize files, {lazy_total(now)} lazy imports")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
