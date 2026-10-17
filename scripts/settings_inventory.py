#!/usr/bin/env python3
"""
Print a Markdown inventory of every switch / mode / cap setting: family, default, group and how many src/ files read it.
輸出所有開關/模式/上限設定的 Markdown 清單：所屬家族、預設值、群組與 src/ 中讀取它的檔案數。

Offline and fast (one pass over src/). Source of truth for families: config/settings_families.yaml.
Used to generate the wiki inventory:  .venv/bin/python scripts/settings_inventory.py > /tmp/inventory.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "config" / "settings_schema.yaml"
REGISTRY = REPO / "config" / "settings_families.yaml"

# Same pattern the ratchet test uses (tests/invariants/test_settings_families.py imports it from here).
KEY_PATTERN = re.compile(r"(_mode|_enabled|^enable_|^allow_|_cap$|max_order|max_tickers|friction|min_holding)")


def load_settings() -> list[dict]:
    return yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))["settings"]


def load_family_index() -> dict[str, str]:
    fams = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["families"]
    return {k: f["id"] for f in fams for k in f["members"]}


def count_readers(keys: list[str]) -> dict[str, int]:
    """Number of src/ .py files containing each key as a literal string. / 含該鍵字面值的 src/ 檔案數。"""
    counts = dict.fromkeys(keys, 0)
    for p in (REPO / "src").rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for k in keys:
            if k in text:
                counts[k] += 1
    return counts


def build_rows() -> list[dict]:
    fam = load_family_index()
    entries = [e for e in load_settings() if KEY_PATTERN.search(e["key"])]
    counts = count_readers([e["key"] for e in entries])
    return [
        {
            "key": e["key"],
            "family": fam.get(e["key"], "UNREGISTERED"),
            "default": e.get("default"),
            "group": e.get("group", ""),
            "readers": counts[e["key"]],
        }
        for e in entries
    ]


def main() -> int:
    rows = build_rows()
    rows.sort(key=lambda r: (r["family"] == "UNREGISTERED", r["family"], r["key"]))
    print("| key | family | default | group | src files reading |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| `{r['key']}` | {r['family']} | `{r['default']!r}` | {r['group']} | {r['readers']} |")
    unreg = sum(1 for r in rows if r["family"] == "UNREGISTERED")
    print(f"\n{len(rows)} settings, {unreg} unregistered.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
