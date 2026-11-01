"""CODEOWNERS 的 R3 清單必須與 .dev-standard/risk.json 的 r3_globs 一致（DD-2026-1032 §6）。

Both files list the money paths; if one gains a path the other lacks, either the script
auto-merges a path GitHub does not guard, or GitHub blocks a path the script thinks is R1.
兩份清單任何一邊多列，不是腳本會自動合併 GitHub 沒保護的路徑，就是反過來。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _codeowners_patterns() -> set:
    patterns = set()
    for line in (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path = line.split()[0].lstrip("/")
        # CODEOWNERS 的目錄寫法 `secrets/` 在 risk.json 寫成 `secrets/*`
        patterns.add(path + "*" if path.endswith("/") else path)
    return patterns


def test_codeowners_r3_paths_equal_risk_json_r3_globs():
    r3_globs = set(json.loads((ROOT / ".dev-standard" / "risk.json").read_text(encoding="utf-8"))["r3_globs"])
    owners = _codeowners_patterns()
    assert owners == r3_globs, (
        f"只在 CODEOWNERS：{sorted(owners - r3_globs)}；只在 risk.json r3_globs：{sorted(r3_globs - owners)}"
    )
