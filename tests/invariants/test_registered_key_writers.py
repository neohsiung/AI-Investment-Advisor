"""
Registered-key writer ratchet (G3): only the UI settings path and the future parameter engine may write
a setting that the parameter registry (or the supplementary protected list) names.
登錄鍵寫入者棘輪（G3）：只有 UI 設定路徑與未來的參數引擎可以寫入被登錄檔（或補充保護清單）點名的設定。

Pure AST over `src/` and `services/` (no production code is imported). A "writer" is a call to a settings
write method (`set_setting`, `save_setting`, `save_settings_bulk`, `<*setting*>.set`) or raw SQL that
INSERTs/UPDATEs the `settings` table. Three kinds of finding, per file:
  * literal:<key>  — the call names a protected key as a string literal;
  * dynamic        — the key is not a literal, so the call COULD hit a protected key (counted);
  * raw_sql        — raw SQL on the settings table (counted).
Findings in files outside ALLOWED_WRITERS must be a subset of `registered_key_writers_baseline.json`.
The baseline may only shrink: it fails when code got worse, and also when the baseline is looser than
reality. Do NOT hand-edit the JSON to pass; fix the code, then:

    .venv/bin/python -m tests.invariants.test_registered_key_writers --update

(`--update` refuses to add anything; it only creates the file when absent or shrinks it.)
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from src.config.parameter_registry import load_registry

REPO = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("registered_key_writers_baseline.json")
SCAN_ROOTS = ("src", "services")

# Settings implementation + UI path + the future parameter engine (G2). Anything else is an offender.
# 設定實作、UI 設定路徑、未來參數引擎（G2）；其餘皆為違規。
ALLOWED_WRITERS = {
    "src/services/settings_service.py",
    "src/repositories/settings_repository.py",
    "src/api/v1/endpoints/settings.py",
    "src/services/parameter_engine.py",
}

# Keys the registry does not list yet but that tuning loops must not write directly either.
# 登錄檔尚未列入、但調參迴圈同樣不得直接寫入的鍵。
EXTRA_PROTECTED_KEYS = {
    "tactical_phase_factor_weights",
    "tactical_rotation_min_edge_pct",
    "factor_liquidity_premium_weight",
}
EXTRA_PROTECTED_PREFIXES = ("tactical_",)

_WRITE_METHODS = {"set_setting", "save_setting", "save_settings_bulk", "update_setting"}
_SQL_WRITE_RE = re.compile(r"\b(insert\s+into|update)\s+(?:public\.)?settings\b", re.I)


def protected_keys() -> set:
    return {p.key for p in load_registry().parameters if p.store == "settings"} | EXTRA_PROTECTED_KEYS


def _is_protected(key: str, keys: set) -> bool:
    return key in keys or key.startswith(EXTRA_PROTECTED_PREFIXES)


def _receiver_text(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return ""


def _is_write_call(call: ast.Call) -> bool:
    f = call.func
    if not isinstance(f, ast.Attribute):
        return False
    if f.attr in _WRITE_METHODS:
        return True
    return f.attr == "set" and "setting" in _receiver_text(f.value).lower()


def _literal_keys(call: ast.Call) -> List[str]:
    """String literals in the key position: args[1] for `<repo>.set(user, key, v)`, else args[0]; dict-literal
    keys for bulk saves; the `key=` keyword.
    鍵位置的字串常值：`.set(user, key, v)` 取第二個引數，其餘取第一個；批次寫入取 dict 常值鍵。"""
    out: List[str] = []
    pos = 1 if call.func.attr == "set" else 0
    for a in call.args[pos:pos + 1]:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            out.append(a.value)
        elif isinstance(a, ast.Dict):
            out += [k.value for k in a.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    for kw in call.keywords:
        if kw.arg == "key" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            out.append(kw.value.value)
    return out


def scan_source(source: str, keys: set) -> Dict[str, object]:
    """Findings for one module: {"literal": {key,...}, "dynamic": n, "raw_sql": n}."""
    literal: set = set()
    dynamic = raw_sql = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _is_write_call(node):
            lits = _literal_keys(node)
            hits = {k for k in lits if _is_protected(k, keys)}
            if hits:
                literal |= hits
            elif not lits:
                dynamic += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _SQL_WRITE_RE.search(node.value):
            raw_sql += 1
    return {"literal": sorted(literal), "dynamic": dynamic, "raw_sql": raw_sql}


def scan_repo(roots: Iterable[str] = SCAN_ROOTS) -> Dict[str, Dict[str, object]]:
    keys = protected_keys()
    out: Dict[str, Dict[str, object]] = {}
    for root in roots:
        for p in sorted((REPO / root).rglob("*.py")):
            rel = str(p.relative_to(REPO))
            if rel in ALLOWED_WRITERS:
                continue
            try:
                res = scan_source(p.read_text(encoding="utf-8"), keys)
            except SyntaxError:
                continue
            if res["literal"] or res["dynamic"] or res["raw_sql"]:
                out[rel] = res
    return out


def compare(now: Dict[str, dict], base: Dict[str, dict]) -> Dict[str, List[str]]:
    """{"worse": [...], "loose": [...]} — worse = code exceeds baseline; loose = baseline exceeds code."""
    worse: List[str] = []
    loose: List[str] = []
    for f in sorted(set(now) | set(base)):
        n = now.get(f, {"literal": [], "dynamic": 0, "raw_sql": 0})
        b = base.get(f, {"literal": [], "dynamic": 0, "raw_sql": 0})
        for k in sorted(set(n["literal"]) - set(b["literal"])):
            worse.append(f"{f}: new write of protected key '{k}'")
        for k in sorted(set(b["literal"]) - set(n["literal"])):
            loose.append(f"{f}: baseline still lists '{k}'")
        for field in ("dynamic", "raw_sql"):
            if n[field] > b[field]:
                worse.append(f"{f}: {field} writes {b[field]} -> {n[field]}")
            elif n[field] < b[field]:
                loose.append(f"{f}: baseline {field} {b[field]} > actual {n[field]}")
    return {"worse": worse, "loose": loose}


def _load_baseline() -> Dict[str, dict]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["offenders"]


def test_no_new_direct_writer_of_registered_keys():
    diff = compare(scan_repo(), _load_baseline())
    assert not diff["worse"], (
        "Setting writes outside the UI settings path / parameter engine are forbidden (propose via "
        "parameter_proposals instead):\n  " + "\n  ".join(diff["worse"])
    )


def test_baseline_is_not_looser_than_reality():
    diff = compare(scan_repo(), _load_baseline())
    assert not diff["loose"], (
        "Baseline is looser than the code; tighten it with --update:\n  " + "\n  ".join(diff["loose"])
    )


def test_ratchet_flags_new_direct_writer():
    """A fresh module that writes a registered key (or a tactical_* key) is flagged; allow-listed ones are not."""
    keys = protected_keys()
    registered = next(iter(k for k in keys if not k.startswith("tactical_") and "." not in k))
    assert scan_source(f"def f(s):\n    s.set_setting('{registered}', 1)\n", keys)["literal"] == [registered]
    assert scan_source("def f(r):\n    r.settings_repo.set('u', 'tactical_x', 1)\n", keys)["literal"] == ["tactical_x"]
    assert scan_source("def f(s, k):\n    s.save_setting(k, 1)\n", keys)["dynamic"] == 1
    assert scan_source("def f(c):\n    c.execute(\"UPDATE settings SET value=1\")\n", keys)["raw_sql"] == 1
    # unrelated redis-style `.set` and unregistered keys are not flagged
    assert scan_source("def f(r):\n    r.set('x', 1)\n    s.set_setting('totally_other_key', 1)\n", keys) == {
        "literal": [], "dynamic": 0, "raw_sql": 0}
    # the ratchet compares against the baseline: a new offender file is "worse"
    now = {"src/services/new_mod.py": {"literal": [registered], "dynamic": 0, "raw_sql": 0}}
    assert compare(now, {})["worse"]
    # allow-list members are never scanned
    assert "src/api/v1/endpoints/settings.py" in ALLOWED_WRITERS and "src/api/v1/endpoints/settings.py" not in scan_repo()


def test_engine_is_no_longer_a_direct_writer():
    assert "src/services/factor_genetic_evolution_engine.py" not in scan_repo()


def _update() -> int:
    now = scan_repo()
    if BASELINE.exists():
        base = _load_baseline()
        diff = compare(now, base)
        if diff["worse"]:
            print("refusing to raise baseline:\n  " + "\n  ".join(diff["worse"]))
            return 1
    BASELINE.write_text(json.dumps({"offenders": now}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"baseline written: {len(now)} offender files")
    return 0


if __name__ == "__main__":
    sys.exit(_update() if "--update" in sys.argv else 0)
