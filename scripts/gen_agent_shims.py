#!/usr/bin/env python3
"""
Keep every AI-agent instruction file in sync with the mission rules in AGENTS.md (single source of truth).
讓所有 AI agent 指令檔與 AGENTS.md 的使命規則保持一致（單一來源）。

AGENTS.md holds the rules between <!-- MISSION:BEGIN --> and <!-- MISSION:END -->. This script copies that block
into each tool's file between <!-- GENERATED:MISSION:BEGIN/END --> (inserted at the top if absent) and never touches
the rest of those files. `--check` exits non-zero if any file is stale (used by CI via tests/invariants).
AGENTS.md 在兩個標記之間存放規則；本腳本把該區塊複製到各工具檔案的 GENERATED 區塊（若無則插入檔案開頭），
不動其餘內容。--check 在有檔案過期時回傳非 0（由 tests/invariants 在 CI 執行）。
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "AGENTS.md"
TARGETS = ["GEMINI.md", "QODER.md", ".cursorrules", ".windsurfrules", ".kiro/steering/mission.md"]
SRC_RE = re.compile(r"<!-- MISSION:BEGIN -->\n(.*?)<!-- MISSION:END -->", re.S)
GEN_RE = re.compile(r"<!-- GENERATED:MISSION:BEGIN -->\n(.*?)<!-- GENERATED:MISSION:END -->\n?", re.S)
HEADER = "<!-- Generated from AGENTS.md by scripts/gen_agent_shims.py — edit AGENTS.md, not this block. -->\n"


def source_block() -> str:
    m = SRC_RE.search(SOURCE.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("AGENTS.md has no <!-- MISSION:BEGIN --> ... <!-- MISSION:END --> block")
    return m.group(1).strip() + "\n"


def render(block: str) -> str:
    return f"<!-- GENERATED:MISSION:BEGIN -->\n{HEADER}{block}<!-- GENERATED:MISSION:END -->\n"


def updated(text: str, block: str) -> str:
    gen = render(block)
    if GEN_RE.search(text):
        return GEN_RE.sub(lambda _m: gen, text, count=1)
    return gen + ("\n" + text if text else "")


def main(argv) -> int:
    check = "--check" in argv
    block = source_block()
    stale = []
    for rel in TARGETS:
        path = REPO / rel
        if check and not path.exists():
            continue   # tool files are git-ignored per developer; only existing ones can be stale
        cur = path.read_text(encoding="utf-8") if path.exists() else ""
        new = updated(cur, block)
        if new != cur:
            stale.append(rel)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new, encoding="utf-8")
    if check and stale:
        print("stale agent instruction files (run scripts/gen_agent_shims.py): " + ", ".join(stale))
        return 1
    print(("up to date" if not stale else "updated: " + ", ".join(stale)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
