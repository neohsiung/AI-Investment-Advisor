"""CODEOWNERS must cover every money path (AGENTS.md rule 1).
CODEOWNERS 必須涵蓋每一個動錢路徑（AGENTS.md 規則 1）。

`tests/unit/test_codeowners_matches_r3_globs.py` only proves CODEOWNERS == risk.json r3_globs.
It cannot notice a money file that is in *neither* list. This test guards that:
  (a) the named money files are matched by a CODEOWNERS rule (and still exist);
  (b) every file under src/ and services/ that calls a broker order write
      (`place_order` / `execute_order` / `cancel_order`) is matched by a rule.
Gaps found by (b) today are frozen in KNOWN_UNCOVERED_ORDER_CALLERS: the set may only shrink.
Closing a gap means a human adds the file to CODEOWNERS and risk.json (founder-only files).
(b) 已知缺口凍結在 KNOWN_UNCOVERED_ORDER_CALLERS，只准縮；補進 CODEOWNERS 由創辦人做。
"""
import ast
import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("src", "services")
BROKER_WRITE_CALLS = {"place_order", "execute_order", "cancel_order"}

# AGENTS.md rule 1 money paths + the strategy-name SSOT file. Must exist and be owned.
NAMED_MONEY_FILES = (
    "src/services/automated_trading_service.py",
    "src/services/unified_risk_gateway_service.py",
    "src/services/capital_policy.py",
    "src/services/etoro_service.py",
    "src/domain/strategy_names.py",
    "config/mission.yaml",
)

# Ratchet: order-placing files not yet in CODEOWNERS (reported in the PR; do not add here).
KNOWN_UNCOVERED_ORDER_CALLERS = {
    "src/services/staggered_dip_buying_service.py",
    "src/services/cross_sector_harvest_rebalance_service.py",
}


def _owner_patterns() -> list:
    pats = []
    for line in (REPO / ".github" / "CODEOWNERS").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pats.append(line.split()[0])
    return pats


def _matches(rel: str, pattern: str) -> bool:
    anchored = pattern.startswith("/")
    pat = pattern.lstrip("/")
    if pat.endswith("/"):  # directory rule
        return rel.startswith(pat) if anchored else f"/{pat}" in f"/{rel}"
    if anchored:
        return fnmatch.fnmatchcase(rel, pat)
    return fnmatch.fnmatchcase(rel.rsplit("/", 1)[-1], pat) or fnmatch.fnmatchcase(rel, pat)


def _covered(rel: str) -> bool:
    return any(_matches(rel, p) for p in _owner_patterns())


def _order_callers() -> set:
    found = set()
    for root in SCAN_ROOTS:
        for path in (REPO / root).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in BROKER_WRITE_CALLS
                ):
                    found.add(path.relative_to(REPO).as_posix())
                    break
    return found


def test_named_money_files_exist_and_are_owned():
    missing = [f for f in NAMED_MONEY_FILES if not (REPO / f).exists()]
    unowned = [f for f in NAMED_MONEY_FILES if not _covered(f)]
    assert not missing, f"named money files no longer exist (renamed? update the list and CODEOWNERS): {missing}"
    assert not unowned, f"money files not matched by any CODEOWNERS rule: {unowned}"


def test_order_placing_files_are_owned_or_known_gap():
    uncovered = {f for f in _order_callers() if not _covered(f)}
    new_gaps = uncovered - KNOWN_UNCOVERED_ORDER_CALLERS
    assert not new_gaps, f"new order-placing file(s) outside CODEOWNERS (R3 needs an owner): {sorted(new_gaps)}"


def test_known_gap_list_only_shrinks():
    uncovered = {f for f in _order_callers() if not _covered(f)}
    stale = KNOWN_UNCOVERED_ORDER_CALLERS - uncovered
    assert not stale, f"gap closed or file gone; remove from KNOWN_UNCOVERED_ORDER_CALLERS: {sorted(stale)}"


def test_matcher_rejects_unowned_path():
    # Guard against a matcher that says yes to everything.
    assert not _covered("src/services/some_random_new_service.py")
