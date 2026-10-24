#!/usr/bin/env python3
"""
Ratchet ruff violations: existing ones are frozen as per-(file, rule) counts, CI fails only when a count grows.
以計數棘輪管 ruff：舊違規以「(檔案, 規則) → 次數」凍結，只有次數增加時 CI 才失敗。

Why counts, not `ruff check --add-noqa`: adding noqa would edit hundreds of files, R3 money paths included, just to
adopt lint. Counts keep every source file untouched and still catch a second violation of the same rule in a file
(per-file-ignores would not).
為什麼不用 --add-noqa：那會為了導入 lint 改到數百個檔（含 R3 動錢路徑）。
計數不動任何原始碼，而且同檔同規則多一個也抓得到。

  python3 scripts/ruff_baseline.py check    # CI: exit 1 if any (file, rule) count is above the baseline
  python3 scripts/ruff_baseline.py update   # rewrite the baseline after fixing old violations (only ever shrinks it)

Known gap / 已知殘留: fixing one violation and adding another of the same rule in the same file nets to zero.
A renamed file shows up as new violations; run `update` in the same PR and say so in the description.
"""
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / ".ruff-baseline.json"


def _ruff_cmd() -> list:
    exe = shutil.which("ruff")
    return [exe] if exe else [sys.executable, "-m", "ruff"]


def ruff_version() -> str:
    out = subprocess.run(_ruff_cmd() + ["--version"], capture_output=True, text=True, check=True)
    return out.stdout.strip().split()[-1]


def current_counts() -> Counter:
    proc = subprocess.run(_ruff_cmd() + ["check", "--output-format", "json", "--exit-zero", "."],
                          cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        # A config error or crash must not read as "no violations". 設定錯誤或當掉不能當成零違規。
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"ruff failed (exit {proc.returncode})")
    counts: Counter = Counter()
    for item in json.loads(proc.stdout or "[]"):
        rel = Path(item["filename"]).resolve().relative_to(REPO).as_posix()
        counts[f"{rel}::{item['code']}"] += 1
    return counts


def load_baseline() -> dict:
    if not BASELINE.exists():
        raise SystemExit(f"{BASELINE.name} missing: run `python3 scripts/ruff_baseline.py update` once")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def cmd_update() -> int:
    counts = current_counts()
    data = {"ruff_version": ruff_version(), "total": sum(counts.values()),
            "counts": dict(sorted(counts.items()))}
    BASELINE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"baseline written: {data['total']} violations in {len({k.split('::')[0] for k in counts})} files")
    return 0


def cmd_check() -> int:
    base = load_baseline()
    have = ruff_version()
    if base.get("ruff_version") != have:
        # Rule sets change between versions; comparing across them gives false red or false green.
        print(f"ruff {have} != baseline ruff {base.get('ruff_version')}: install the pinned version "
              f"(pip install ruff=={base.get('ruff_version')}) or re-baseline in its own PR")
        return 1
    allowed = base["counts"]
    counts = current_counts()
    grown = {k: (allowed.get(k, 0), v) for k, v in counts.items() if v > allowed.get(k, 0)}
    shrunk = {k: (n, counts.get(k, 0)) for k, n in allowed.items() if counts.get(k, 0) < n}
    if grown:
        print("new ruff violations (baseline -> now) / 新增的 ruff 違規：")
        for k, (was, now) in sorted(grown.items()):
            print(f"  {k}: {was} -> {now}")
        print(f"see them: ruff check {' '.join(sorted({k.split('::')[0] for k in grown}))}")
        return 1
    if shrunk:
        print(f"{len(shrunk)} baseline entries shrank: run `python3 scripts/ruff_baseline.py update` to lock it in")
    print(f"ruff baseline ok: {sum(counts.values())} existing violations, none new")
    return 0


def main(argv: list) -> int:
    if argv[:1] == ["update"]:
        return cmd_update()
    if argv[:1] == ["check"]:
        return cmd_check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
