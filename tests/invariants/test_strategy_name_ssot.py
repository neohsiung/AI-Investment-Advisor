"""Strategy-name ratchet: decision code must not grow new hand-copied name lists, substring tests on names, or
producers that send a name nobody defined.
策略名棘輪：決策程式不得新增手抄名單、對名稱做子字串比對，或送出沒人定義的名稱。

Four AST measurements over `src/` and `services/` (nothing is imported). The definition lives in
`src/domain/strategy_names.py`; this file only keeps copies from coming back.
  literal_name_lists  — tuple/list/set/frozenset literals holding >= 2 known strategy names (a hand-copied list);
  substring_tests     — `"<name>" in x` and `any(k in strat for k in ("<keyword>", ...))` idioms on names;
  dynamic_strategy_names — order calls whose `strategy_name=` is not a literal (cannot be checked statically).
And two absolute rules: every literal strategy name sent to an order call is defined, and every role is made of
defined names. Counts may only fall (same comparator and `--update` / `--check-tight` as test_layering).
測量三項：手抄名單、子字串比對、非字面策略名；另有兩條絕對規則：送進下單呼叫的字面策略名必須已定義、角色只含已定義名稱。
計數只准下降。
    .venv/bin/python -m tests.invariants.test_strategy_name_ssot --check-tight
    .venv/bin/python -m tests.invariants.test_strategy_name_ssot --update
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from src.domain import strategy_names as sn

REPO = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("strategy_name_baseline.json")
SCAN_ROOTS = ("src", "services")
DEFINITION = "src/domain/strategy_names.py"
ORDER_CALLS = ("evaluate_and_execute_trade", "evaluate_trade_risk", "order_allowed", "check_constraints")
KEYS = ("literal_name_lists", "substring_tests", "dynamic_strategy_names")

NAMES = sn.universe()
# producers may send these; LEGACY names must not be sent (they only live inside the old exemption lists)
PRODUCIBLE = sn.ALL | frozenset(f"proposal_{s}" for s in sn.PROPOSAL_SOURCES)
# a keyword is "on a strategy name" when it is a substring of one (rebalance, rotation, deploy, stop_loss ...)
KEYWORDS = frozenset(w for n in NAMES for w in n.split("_") if len(w) >= 4) | NAMES


def _files() -> list[Path]:
    return sorted(p for root in SCAN_ROOTS for p in (REPO / root).rglob("*.py")
                  if "__pycache__" not in p.parts and p.relative_to(REPO).as_posix() != DEFINITION)


def _str(node: ast.AST) -> str | None:
    return node.value.strip().lower() if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_name_list(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "frozenset" and len(node.args) == 1:
        node = node.args[0]
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return False
    return len({s for s in map(_str, node.elts) if s in NAMES}) >= 2


def _is_keyword_scan(node: ast.AST) -> bool:
    """`any(k in strat for k in ("rebalance", "rotation", ...))` — a keyword loop over a literal tuple."""
    if not isinstance(node, ast.GeneratorExp) or len(node.generators) != 1:
        return False
    it = node.generators[0].iter
    if not isinstance(it, (ast.Tuple, ast.List, ast.Set)):
        return False
    elt = node.elt
    in_test = isinstance(elt, ast.Compare) and any(isinstance(o, (ast.In, ast.NotIn)) for o in elt.ops)
    return in_test and any(s in KEYWORDS for s in map(_str, it.elts) if s)


def _is_substring_test(node: ast.AST) -> bool:
    """`"stop_loss" in strat` — a literal strategy name tested against a non-literal (hand-made membership)."""
    if not isinstance(node, ast.Compare) or not any(isinstance(o, (ast.In, ast.NotIn)) for o in node.ops):
        return False
    left = _str(node.left)
    right = node.comparators[0]
    return left in NAMES and not isinstance(right, (ast.Tuple, ast.List, ast.Set, ast.Dict))


def _sent_strategy_values(n: ast.AST) -> list[ast.AST]:
    """The expressions an order call (or a ``{"strategy_name": ...}`` dict) passes as the strategy name."""
    sent: list[ast.AST] = []
    if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in ORDER_CALLS:
        sent += [k.value for k in n.keywords if k.arg == "strategy_name"]
    if isinstance(n, ast.Dict):
        sent += [v for k, v in zip(n.keys, n.values, strict=True) if _str(k) == "strategy_name"]
    return sent


def _measure_file(tree: ast.AST, rel: str) -> tuple[dict[str, int], list[str]]:
    counts = dict.fromkeys(KEYS, 0)
    undefined: list[str] = []
    for n in ast.walk(tree):
        counts["literal_name_lists"] += _is_name_list(n)
        counts["substring_tests"] += _is_keyword_scan(n) or _is_substring_test(n)
        for v in _sent_strategy_values(n):
            literal = _str(v)
            if literal is not None:
                if literal not in PRODUCIBLE:
                    undefined.append(f"{rel}:{getattr(v, 'lineno', '?')} {literal!r}")
            elif not (isinstance(v, ast.Constant) and v.value is None):
                counts["dynamic_strategy_names"] += 1
    return counts, undefined


def measure() -> dict:
    out: dict[str, dict[str, int]] = {k: {} for k in KEYS}
    undefined: list[str] = []
    for p in _files():
        rel = p.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        counts, bad = _measure_file(tree, rel)
        undefined += bad
        for k in KEYS:
            if counts[k]:
                out[k][rel] = counts[k]
    return {"counts": {k: dict(sorted(v.items())) for k, v in out.items()}, "undefined": sorted(undefined)}


def regressions(base: dict, now: dict) -> list[str]:
    out = []
    for k in KEYS:
        for f, n in now[k].items():
            old = base[k].get(f, 0)
            if n > old:
                out.append(f"{k} rose in {f}: {old} -> {n}")
    return out


def stale(base: dict, now: dict) -> list[str]:
    out = []
    for k in KEYS:
        for f, old in base[k].items():
            if now[k].get(f, 0) < old:
                out.append(f"{k} fell in {f}: {old} -> {now[k].get(f, 0)}")
    return out


def dump_baseline(d: dict) -> str:
    def block(name: str, m: dict) -> str:
        if not m:
            return f'  "{name}": {{}}'
        body = ",\n".join(f"    {json.dumps(k)}: {json.dumps(m[k])}" for k in sorted(m))
        return f'  "{name}": {{\n{body}\n  }}'
    return "{\n" + ",\n".join(block(k, d[k]) for k in KEYS) + "\n}\n"


def load_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_no_new_hand_copied_lists_or_substring_tests():
    bad = regressions(load_baseline(), measure()["counts"])
    assert not bad, ("strategy-name ratchet regressed: import the role from src/domain/strategy_names.py instead of "
                     "copying a list or testing a substring (do not raise the baseline):\n" + "\n".join(bad[:30]))


def test_every_literal_strategy_name_sent_to_an_order_call_is_defined():
    bad = measure()["undefined"]
    assert not bad, ("strategy_name literals that strategy_names.py does not define (add the name there first, "
                     "legacy names must not be sent):\n" + "\n".join(bad[:30]))


def test_every_role_is_made_of_defined_names():
    """The roles are frozensets in strategy_names.py; each member must be a producible or legacy name."""
    allowed = NAMES
    roles = {n: v for n, v in vars(sn).items() if isinstance(v, frozenset) and n.isupper()
             and n not in ("ALL", "LEGACY")}
    assert roles, "no roles found in strategy_names"
    for name, members in roles.items():
        unknown = sorted(m for m in members if m not in allowed)
        assert not unknown, f"{name} holds undefined names {unknown}"


def test_legacy_names_are_not_produced_by_any_order_path():
    sent = {m.split(" ")[-1].strip("'") for m in measure()["undefined"]}
    assert not (sent & sn.LEGACY)


def test_comparator_flags_worse_and_stale_on_synthetic_data():
    base = {"literal_name_lists": {"a.py": 2}, "substring_tests": {"b.py": 1}, "dynamic_strategy_names": {}}
    worse = {"literal_name_lists": {"a.py": 3, "c.py": 1}, "substring_tests": {"b.py": 1},
             "dynamic_strategy_names": {"d.py": 1}}
    assert len(regressions(base, worse)) == 3
    better = {"literal_name_lists": {"a.py": 1}, "substring_tests": {}, "dynamic_strategy_names": {}}
    assert regressions(base, better) == [] and len(stale(base, better)) == 2
    assert regressions(base, base) == [] and stale(base, base) == []


def test_detectors_see_the_idioms_they_exist_for():
    src = (
        'a = ("stop_loss", "emergency_exit")\n'
        'b = any(k in strat for k in ("rebalance", "rotation"))\n'
        'c = "stop_loss" in strat\n'
        'x.evaluate_and_execute_trade(strategy_name=name)\n'
        'y.evaluate_and_execute_trade(strategy_name="not_a_strategy")\n'
    )
    tree = ast.parse(src)
    nodes = list(ast.walk(tree))
    assert sum(_is_name_list(n) for n in nodes) == 1
    assert sum(_is_keyword_scan(n) for n in nodes) == 1
    assert sum(_is_substring_test(n) for n in nodes) == 1


def test_baseline_file_is_merge_friendly():
    text = BASELINE.read_text(encoding="utf-8")
    assert text == dump_baseline(json.loads(text))
    assert all(len(line) < 400 for line in text.splitlines())


def main(argv: list[str]) -> int:
    if argv == ["--check-tight"]:
        gone = stale(load_baseline(), measure()["counts"])
        if gone:
            print("baseline is looser than reality — run "
                  "`python -m tests.invariants.test_strategy_name_ssot --update`:")
            print("\n".join(gone[:40]))
            return 1
        print("baseline is tight")
        return 0
    if argv != ["--update"]:
        print("usage: python -m tests.invariants.test_strategy_name_ssot --update | --check-tight")
        return 2
    now = measure()["counts"]
    if BASELINE.exists():
        bad = regressions(load_baseline(), now)
        if bad:
            print("REFUSED: --update never raises the baseline. Fix these first:")
            print("\n".join(bad[:40]))
            return 1
    BASELINE.write_text(dump_baseline(now), encoding="utf-8")
    print("baseline written: " + ", ".join(f"{k}={sum(now[k].values())}" for k in KEYS))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
