"""
Shared frontmatter parsing.

Two real defects motivated this module, both caught by verification rather than
by review:

  1. `SkillLoader._extract_frontmatter` read only the first 4096 bytes. Longer
     frontmatter yielded fewer than three split parts, the method returned None,
     and the skill silently vanished from discovery.

  2. Both original implementations used `text.split("---", 2)`, which matches the
     delimiter ANYWHERE. A frontmatter comment containing the characters "---"
     truncated the frontmatter mid-comment; the YAML then parsed to nothing and
     every field disappeared with no error. This bit the M6 agent manifests: a
     comment reading "after the closing ---" silently emptied all 14 of them.

兩個真實缺陷促成本模組：舊實作只讀前 4KB（超過則 skill 靜默消失）；
且 split("---") 會匹配任意位置——註解中只要含 "---" 就會截斷 frontmatter，
YAML 解析為空、所有欄位無聲消失（M6 的 14 個 agent manifest 就是這樣全空）。
"""
from __future__ import annotations

import pytest

from src.utils.frontmatter import (
    Document,
    FrontmatterError,
    dump,
    parse,
    parse_file,
    read_meta,
)


class TestDelimiterIsLineAnchored:

    def test_comment_containing_the_delimiter_does_not_truncate(self):
        """The exact failure that emptied the agent manifests."""
        doc = parse("---\n# see the closing --- below\nid: x\nimpl: y\n---\n\nbody\n")
        assert doc.meta == {"id": "x", "impl": "y"}
        assert doc.body == "body"

    def test_value_containing_the_delimiter_survives(self):
        doc = parse('---\nnote: "a --- b"\nid: x\n---\nbody\n')
        assert doc.meta["note"] == "a --- b"
        assert doc.meta["id"] == "x"

    def test_horizontal_rule_stays_in_the_body(self):
        doc = parse("---\nid: z\n---\n\nintro\n\n---\n\noutro\n")
        assert doc.meta == {"id": "z"}
        assert "---" in doc.body
        assert "outro" in doc.body

    def test_inline_dashes_in_prose_stay_in_the_body(self):
        doc = parse("---\nid: z\n---\n\nProse with --- inline.\n")
        assert doc.meta == {"id": "z"}
        assert "---" in doc.body

    def test_indented_delimiter_is_not_a_delimiter(self):
        """Only a whole line counts, so indented dashes cannot close the block."""
        doc = parse("---\nid: z\nlist:\n  - a\n---\nbody\n")
        assert doc.meta["id"] == "z"
        assert doc.meta["list"] == ["a"]


class TestNoTruncation:

    def test_frontmatter_larger_than_4kb_parses(self):
        """
        The old SkillLoader read 4096 bytes and returned None past that, removing
        the skill from discovery with no error.
        舊實作只讀 4096 bytes，超過即回傳 None，該 skill 從探索結果消失且無錯誤訊息。
        """
        big = "---\n" + "\n".join(f"key_{i}: value_{i}" for i in range(400)) + "\n---\n\nbody\n"
        assert len(big) > 4096
        doc = parse(big)
        assert len(doc.meta) == 400
        assert doc.body == "body"


class TestMalformedInput:

    def test_unclosed_frontmatter_raises(self):
        with pytest.raises(FrontmatterError, match="never closed"):
            parse("---\nid: q\n", source="probe")

    def test_invalid_yaml_raises(self):
        with pytest.raises(FrontmatterError, match="invalid YAML"):
            parse("---\n: :\n---\nbody\n", source="probe")

    def test_non_mapping_frontmatter_raises(self):
        with pytest.raises(FrontmatterError, match="must be a mapping"):
            parse("---\n- a\n- b\n---\nbody\n", source="probe")

    def test_no_frontmatter_is_valid(self):
        """Some bodies are just prose; that is not an error."""
        doc = parse("Just prose.")
        assert doc.meta == {}
        assert doc.body == "Just prose."

    def test_read_meta_skips_bad_files_without_raising(self, tmp_path):
        bad = tmp_path / "bad.md"
        bad.write_text("---\nunclosed: true\n")
        assert read_meta(bad) is None


class TestRoundTrip:

    def test_dump_then_parse_preserves_both_halves(self):
        text = dump({"id": "a", "tier": "fast"}, "Body here")
        doc = parse(text)
        assert doc.meta == {"id": "a", "tier": "fast"}
        assert doc.body == "Body here"

    def test_dump_preserves_non_ascii(self):
        text = dump({"display_name": "動能偵察兵"}, "本文")
        doc = parse(text)
        assert doc.meta["display_name"] == "動能偵察兵"
        assert doc.body == "本文"

    def test_parse_file_sets_the_path(self, tmp_path):
        p = tmp_path / "x.md"
        p.write_text(dump({"id": "x"}, "b"))
        doc = parse_file(p)
        assert isinstance(doc, Document)
        assert doc.path == p
