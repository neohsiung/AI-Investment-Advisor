#!/usr/bin/env python3
"""Map changed files to the unit tests worth running before a push.
把變更檔對應到推送前值得跑的單元測試。

Rules / 規則:
  * changed ``src/**/<name>.py``  -> every ``tests/**/test_<name>*.py`` that exists
  * changed ``tests/**/test_*.py`` -> that file itself (if it still exists)
  * ``tests/invariants`` and ``tests/unit/config`` and ``test_fail_silent_policy.py`` are
    always run by ``scripts/pre_push_check.sh``, so they are never returned here.
  * result is de-duplicated, sorted, capped at ``MAX_FILES``.

Usage: ``git diff --name-only origin/main...HEAD | scripts/pre_push_select_tests.py``
Prints one test path per line.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_FILES = 40

# Covered by the always-run part of the gate; do not select them twice.
# 已由固定必跑區涵蓋，不重複選取。
_ALWAYS_PREFIXES = ("tests/invariants/", "tests/unit/config/")
_ALWAYS_FILES = ("tests/unit/test_fail_silent_policy.py",)


def _is_always(rel: str) -> bool:
    return rel.startswith(_ALWAYS_PREFIXES) or rel in _ALWAYS_FILES


def select_tests(changed: list[str], root: Path) -> list[str]:
    root = Path(root)
    picked: set[str] = set()
    for rel in changed:
        rel = rel.strip()
        if not rel.endswith(".py"):
            continue
        p = Path(rel)
        if p.parts[0] == "tests" and p.name.startswith("test_"):
            if (root / rel).is_file() and not _is_always(rel):
                picked.add(rel)
        elif p.parts[0] == "src" and p.stem != "__init__":
            for hit in (root / "tests").rglob(f"test_{p.stem}*.py"):
                hit_rel = hit.relative_to(root).as_posix()
                if not _is_always(hit_rel):
                    picked.add(hit_rel)
    return sorted(picked)[:MAX_FILES]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    changed = [line for line in sys.stdin.read().splitlines() if line.strip()]
    for t in select_tests(changed, root):
        print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
