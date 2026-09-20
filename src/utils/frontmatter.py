"""
YAML-frontmatter + Markdown-body parsing, in one place.

The project uses this file convention in three places — SKILL.md manifests,
config/personas/*.md, and (from M6) config/agents/*.md — and each had its own
parser:

* `PersonaProvider._parse_persona_file` read the whole file and split on "---".
* `SkillLoader._extract_frontmatter` read only the FIRST 4096 BYTES. Frontmatter
  longer than that produced fewer than three parts, the function returned None,
  and the skill silently disappeared from discovery with no error — a skill that
  simply stops existing because its metadata grew.

This module is the single implementation. It never truncates, and it separates
"this file has no frontmatter" from "this file has broken frontmatter" so callers
can say which happened instead of both surfacing as None.

專案在三處使用「YAML frontmatter + Markdown 本文」慣例，原本各有一份解析器。
其中 SkillLoader 只讀前 4096 bytes：frontmatter 一旦超過就會回傳 None，
該 skill 會在沒有任何錯誤訊息的情況下從探索結果中消失。
本模組為單一實作，不截斷，且區分「沒有 frontmatter」與「frontmatter 壞掉」。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_DELIM = "---"


class FrontmatterError(ValueError):
    """The document has frontmatter, but it is malformed."""


@dataclass
class Document:
    """A parsed frontmatter document."""
    meta: Dict[str, Any]
    body: str
    path: Optional[Path] = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.meta.get(key, default)


def parse(text: str, source: str = "<string>") -> Document:
    """
    Split `text` into its YAML frontmatter and Markdown body.

    Raises FrontmatterError when a document opens with the delimiter but does not
    close it, or when the YAML does not parse. A document with no frontmatter at
    all is valid and yields empty metadata — some bodies are just prose.

    以 YAML frontmatter 與 Markdown 本文拆分；有開頭分隔線但未閉合、或 YAML
    無法解析時拋出 FrontmatterError。完全沒有 frontmatter 視為合法（純本文）。
    """
    import yaml

    lines = text.splitlines()
    if not lines or lines[0].strip() != _DELIM:
        return Document(meta={}, body=text.strip())

    # The delimiter is matched only as a WHOLE LINE.
    #
    # Both previous implementations used `text.split("---", 2)`, which matches the
    # delimiter anywhere — including inside a YAML comment or a sentence. A
    # frontmatter comment containing the characters "---" (e.g. "after the closing
    # ---") therefore truncated the frontmatter mid-comment, the YAML parsed to
    # nothing, and every field silently disappeared. An em-dash-free prose line in
    # a Markdown body could do the same.
    #
    # 分隔線只在「整行」相符時才算。原本兩份實作都用 split("---")，會匹配任意位置
    # ——包含註解或句子之中。frontmatter 註解只要含有 "---" 就會被截斷，
    # YAML 解析為空，所有欄位靜默消失。
    closing = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIM:
            closing = i
            break

    if closing is None:
        raise FrontmatterError(
            f"{source}: frontmatter opens with '---' but is never closed"
        )

    front = "\n".join(lines[1:closing])
    body = "\n".join(lines[closing + 1:])

    try:
        meta = yaml.safe_load(front) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"{source}: invalid YAML in frontmatter: {exc}") from exc

    if not isinstance(meta, dict):
        raise FrontmatterError(
            f"{source}: frontmatter must be a mapping, got {type(meta).__name__}"
        )

    return Document(meta=meta, body=body.strip())


def parse_file(path: str | Path) -> Document:
    """Parse a file. Reads it whole — never truncated."""
    p = Path(path)
    doc = parse(p.read_text(encoding="utf-8"), source=str(p))
    doc.path = p
    return doc


def read_meta(path: str | Path) -> Optional[Dict[str, Any]]:
    """
    Metadata only, or None if the file cannot be parsed.

    Convenience for discovery passes that scan many files and want to skip bad
    ones rather than abort. The failure is logged, not swallowed silently.
    供掃描大量檔案的探索流程使用：壞檔跳過而非中斷，且失敗會被記錄而非靜默吞掉。
    """
    try:
        return parse_file(path).meta
    except (FrontmatterError, OSError) as exc:
        logger.warning("frontmatter: skipping %s — %s", path, exc)
        return None


def dump(meta: Dict[str, Any], body: str) -> str:
    """Serialise metadata and body back into a frontmatter document."""
    import yaml

    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip()
    return f"{_DELIM}\n{front}\n{_DELIM}\n\n{body.strip()}\n"


def split_meta_body(text: str) -> Tuple[Dict[str, Any], str]:
    """Tuple form, for callers that prefer unpacking."""
    doc = parse(text)
    return doc.meta, doc.body
