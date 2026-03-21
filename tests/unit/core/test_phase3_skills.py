"""
Tests for Phase 3: SkillLoader 3-Tier Progressive Disclosure + SkillRegistry Dynamic Plugin.
Phase 3 測試：技能載入器三層漸進揭露 + 技能註冊表動態插件。
"""

import pytest
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from src.agents.skills.skill_loader import SkillLoader, Skill, SkillMetadata, SkillTier
from src.agents.skills.registry import SkillRegistry, bind_skills_to_agent


# ──────────────────────────────────────────────────────
# SkillMetadata / Skill Dataclass Tests
# ──────────────────────────────────────────────────────

class TestSkillDataclasses:

    def test_skill_metadata_defaults(self):
        meta = SkillMetadata(name="test_skill")
        assert meta.version == "1.0.0"
        assert meta.category == "general"
        assert meta.tier == "fast"
        assert meta.platform == ["linux", "darwin"]
        assert meta.tags == []

    def test_skill_metadata_custom(self):
        meta = SkillMetadata(
            name="custom", category="market", tier="smart",
            tags=["price", "data"]
        )
        assert meta.category == "market"
        assert meta.tier == "smart"
        assert "price" in meta.tags

    def test_skill_full(self):
        skill = Skill(
            name="test", description="desc", metadata={},
            instruction="Do X", category="research", tier="fast",
            input_schema={"type": "object"}, tags=["search"]
        )
        assert skill.name == "test"
        assert skill.category == "research"
        assert "search" in skill.tags

    def test_skill_tier_enum(self):
        assert SkillTier.FAST == "fast"
        assert SkillTier.SMART == "smart"
        assert SkillTier.ADVANCED == "advanced"


# ──────────────────────────────────────────────────────
# SkillLoader Tests
# ──────────────────────────────────────────────────────

class TestSkillLoaderDiscovery:
    """Tests for Layer 1: metadata.json discovery."""

    @pytest.fixture
    def skill_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill with metadata.json
            search_dir = os.path.join(tmpdir, "search_web")
            os.makedirs(search_dir)
            with open(os.path.join(search_dir, "metadata.json"), "w") as f:
                json.dump({
                    "name": "search_web",
                    "version": "2.0.0",
                    "description": "Web search",
                    "category": "research",
                    "tier": "fast",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    },
                    "platform": ["linux", "darwin"],
                    "tags": ["search", "web"]
                }, f)
            # Create SKILL.md
            with open(os.path.join(search_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: search_web\ndescription: Web search\nmetadata:\n  openclaw:\n    os: [linux, darwin]\n---\n## Instruction\nSearch the web.")
            yield tmpdir

    def test_discover_skills(self, skill_dir):
        loader = SkillLoader(skills_dir=skill_dir)
        metadata = loader.discover_skills()
        assert "search_web" in metadata
        assert metadata["search_web"].version == "2.0.0"
        assert metadata["search_web"].category == "research"

    def test_discover_platform_filter(self, skill_dir):
        """Skills not matching current platform should be filtered."""
        # Add a windows-only skill
        win_dir = os.path.join(skill_dir, "win_tool")
        os.makedirs(win_dir)
        with open(os.path.join(win_dir, "metadata.json"), "w") as f:
            json.dump({"name": "win_tool", "platform": ["windows"]}, f)

        loader = SkillLoader(skills_dir=skill_dir)
        metadata = loader.discover_skills()
        assert "win_tool" not in metadata
        assert "search_web" in metadata

    def test_discover_invalid_json(self, skill_dir):
        """Invalid metadata.json should be skipped gracefully."""
        bad_dir = os.path.join(skill_dir, "bad_skill")
        os.makedirs(bad_dir)
        with open(os.path.join(bad_dir, "metadata.json"), "w") as f:
            f.write("{invalid json}")

        loader = SkillLoader(skills_dir=skill_dir)
        metadata = loader.discover_skills()
        assert "bad_skill" not in metadata


class TestSkillLoaderFullLoad:
    """Tests for Layer 2+3: Full SKILL.md loading with metadata merge."""

    @pytest.fixture
    def skill_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Skill with both metadata.json and SKILL.md
            market_dir = os.path.join(tmpdir, "market_data")
            os.makedirs(market_dir)
            with open(os.path.join(market_dir, "metadata.json"), "w") as f:
                json.dump({
                    "name": "get_market_data",
                    "version": "1.2.0",
                    "category": "market",
                    "tier": "fast",
                    "input_schema": {
                        "type": "object",
                        "properties": {"ticker": {"type": "string"}},
                        "required": ["ticker"]
                    },
                    "tags": ["market", "price"],
                    "platform": ["linux", "darwin"]
                }, f)
            with open(os.path.join(market_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: get_market_data\ndescription: Market data\nmetadata:\n  openclaw:\n    os: [linux, darwin]\n---\nGet prices and indicators.")

            # Skill with SKILL.md only (legacy)
            legacy_dir = os.path.join(tmpdir, "legacy_tool")
            os.makedirs(legacy_dir)
            with open(os.path.join(legacy_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: legacy_tool\ndescription: Legacy\nmetadata: {}\n---\nDo legacy things.")

            yield tmpdir

    def test_load_merges_metadata(self, skill_dir):
        """Layer 1 metadata should be merged into Layer 2+3 Skill."""
        loader = SkillLoader(skills_dir=skill_dir)
        skills = loader.load_skills()
        assert "get_market_data" in skills
        s = skills["get_market_data"]
        assert s.version == "1.2.0"
        assert s.category == "market"
        assert "ticker" in s.input_schema.get("properties", {})

    def test_load_legacy_skill(self, skill_dir):
        """Skills without metadata.json should still load with defaults."""
        loader = SkillLoader(skills_dir=skill_dir)
        skills = loader.load_skills()
        assert "legacy_tool" in skills
        s = skills["legacy_tool"]
        assert s.version == "1.0.0"  # Default
        assert s.category == "general"  # Default

    def test_query_by_category(self, skill_dir):
        loader = SkillLoader(skills_dir=skill_dir)
        loader.load_skills()
        market = loader.get_skills_by_category("market")
        assert "get_market_data" in market
        assert "legacy_tool" not in market

    def test_query_by_tier(self, skill_dir):
        loader = SkillLoader(skills_dir=skill_dir)
        loader.load_skills()
        fast = loader.get_skills_by_tier("fast")
        assert "get_market_data" in fast

    def test_query_by_tag(self, skill_dir):
        loader = SkillLoader(skills_dir=skill_dir)
        loader.load_skills()
        price = loader.get_skills_by_tag("price")
        assert "get_market_data" in price


class TestSkillLoaderXml:
    """Tests for enriched XML generation."""

    def test_xml_includes_schema(self):
        loader = SkillLoader()
        loader.skills = {
            "test": Skill(
                name="test", description="Test tool", metadata={},
                instruction="Use me", category="market", tier="fast",
                input_schema={
                    "type": "object",
                    "properties": {"ticker": {"type": "string", "description": "Symbol"}},
                    "required": ["ticker"]
                }
            )
        }
        xml = loader.get_skill_registry_xml()
        assert 'name="test"' in xml
        assert 'category="market"' in xml
        assert 'name="ticker"' in xml
        assert "required" in xml
        assert "Symbol" in xml


# ──────────────────────────────────────────────────────
# SkillRegistry Tests
# ──────────────────────────────────────────────────────

class TestSkillRegistry:

    def test_register_and_get(self):
        reg = SkillRegistry()
        fn = lambda uid, q: f"Result for {q}"
        reg.register("my_skill", fn)
        assert reg.has("my_skill")
        assert reg.get("my_skill") is fn

    def test_unregister(self):
        reg = SkillRegistry()
        reg.register("temp", lambda: None)
        assert reg.has("temp")
        reg.unregister("temp")
        assert not reg.has("temp")

    def test_list_registered(self):
        reg = SkillRegistry()
        reg.register("a", lambda: None)
        reg.register("b", lambda: None)
        names = reg.list_registered()
        assert "a" in names
        assert "b" in names

    def test_ensure_builtins(self):
        reg = SkillRegistry()
        reg._ensure_builtins()
        assert reg.has("search_web")
        assert reg.has("get_market_data")
        assert reg.has("get_portfolio")

    def test_ensure_builtins_idempotent(self):
        reg = SkillRegistry()
        reg._ensure_builtins()
        reg._ensure_builtins()
        assert len([n for n in reg.list_registered() if n == "search_web"]) == 1

    def test_bind_to_agent(self):
        """Test that skills are bound to agent's McpServer."""
        reg = SkillRegistry()
        reg.register("custom_skill", lambda uid, x: f"result_{x}")

        agent = MagicMock()
        agent.skill_loader = MagicMock()
        agent.skill_loader.skills = {
            "custom_skill": MagicMock(description="Custom")
        }
        agent.user_id = "test_user"

        reg.bind_to_agent(agent)
        agent.register_tool.assert_called()

    def test_bind_unmatched_skill_skipped(self):
        """Skills without implementation should not be bound."""
        reg = SkillRegistry()
        agent = MagicMock()
        agent.skill_loader = MagicMock()
        agent.skill_loader.skills = {
            "unknown_skill": MagicMock(description="Unknown")
        }
        reg.bind_to_agent(agent)
        agent.register_tool.assert_not_called()

    def test_backward_compatible_bind(self):
        """Module-level bind_skills_to_agent should work."""
        agent = MagicMock()
        agent.skill_loader = MagicMock()
        agent.skill_loader.skills = {}

        # Should not raise even with empty skills
        bind_skills_to_agent(agent)
