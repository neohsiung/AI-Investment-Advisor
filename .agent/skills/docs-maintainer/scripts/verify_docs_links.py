#!/usr/bin/env python3
"""檢查 docs/ 內所有 markdown 的相對連結是否指到存在的檔案。
Verify that every relative markdown link under docs/ points to an existing file.

Exit code 1 when any link is broken (the old wiki checker always exited 0).
有壞連結就回傳 1（舊的 wiki 檢查永遠回 0，等於沒擋）。
"""
import os
import re
import sys
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DOCS = os.path.join(ROOT, "docs")
LINK = re.compile(r'(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
EXTERNAL = re.compile(r'^(https?:|mailto:|#|tel:|gbrain:)')


def broken_links(docs_dir: str = DOCS) -> list[str]:
    bad = []
    for dirpath, _dirs, files in os.walk(docs_dir):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            in_code = False
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if line.lstrip().startswith("```"):
                        in_code = not in_code
                    if in_code:
                        continue
                    for m in LINK.finditer(re.sub(r"`[^`]*`", "", line)):
                        target = m.group(1)
                        if EXTERNAL.match(target):
                            continue
                        target = unquote(target.split("#")[0].split("?")[0])
                        if target and not os.path.exists(os.path.normpath(os.path.join(dirpath, target))):
                            bad.append(f"{os.path.relpath(path, ROOT)}:{lineno} -> {m.group(1)}")
    return bad


def main() -> int:
    if not os.path.isdir(DOCS):
        print("docs/ 不存在 / docs/ not found")
        return 1
    bad = broken_links()
    if bad:
        print(f"Found {len(bad)} broken links:")
        print("\n".join(bad))
        return 1
    print("No broken internal links found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
