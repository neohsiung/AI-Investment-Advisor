"""
Tests for M7-6: Unified Skill Manifests and Exposing Skills.
驗證 M7-6: Skill 規格標準化 (SKILL.md) 與 API/Router 動態化測試。
"""
import os
import pytest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.skills.skill_loader import SkillLoader
from src.agents.skill_router import SkillRouter
from src.api.v1.endpoints import skills as ep

SKILLS_ROOT = Path("src/agents/skills")


class TestSkillManifestUnification:
    """Verify that all skills in the repository use standard SKILL.md manifests."""

    def test_no_legacy_manifest_files_exist(self):
        """Ensure no skill.yaml or metadata.json files exist in active skill dirs."""
        for skill_dir in SKILLS_ROOT.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("_") or skill_dir.name == "__pycache__":
                continue
            assert not (skill_dir / "skill.yaml").exists(), f"{skill_dir.name} still contains skill.yaml"
            assert not (skill_dir / "metadata.json").exists(), f"{skill_dir.name} still contains metadata.json"

    def test_every_skill_directory_has_skill_md(self):
        """Every skill directory must contain a valid SKILL.md."""
        for skill_dir in SKILLS_ROOT.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("_") or skill_dir.name == "__pycache__":
                continue
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists(), f"Skill directory {skill_dir.name} is missing SKILL.md"

    def test_distill_insight_and_event_research_are_discovered(self):
        """distill_insight and event_research previously had only skill.yaml and were never discovered."""
        loader = SkillLoader()
        skills = loader.discover_skills()
        assert "distill_insight" in skills
        assert skills["distill_insight"].category == "memory"
        assert "memory" in skills["distill_insight"].tags

        assert "event_research" in skills
        assert skills["event_research"].category == "research"

    def test_knowledge_vault_has_full_metadata(self):
        """knowledge_vault has merged metadata into SKILL.md frontmatter."""
        loader = SkillLoader()
        skills = loader.discover_skills()
        assert "knowledge_vault" in skills
        kv = skills["knowledge_vault"]
        assert kv.category == "core"
        assert "rag" in kv.tags
        assert "action" in kv.input_schema.get("required", [])


class TestFrontmatterIntentMapping:
    """Verify that skill intents in frontmatter correctly populate the direct skill map."""

    def test_get_direct_skill_map(self):
        loader = SkillLoader()
        intent_map = loader.get_direct_skill_map()

        expected = {
            "price": "get_market_data",
            "holdings": "get_user_holdings",
            "portfolio": "get_user_holdings",
            "macro": "get_macro_summary",
            "vix": "get_macro_summary",
            "momentum": "run_momentum_analysis",
        }
        for keyword, expected_skill in expected.items():
            assert intent_map.get(keyword) == expected_skill, (
                f"Keyword '{keyword}' expected '{expected_skill}', got '{intent_map.get(keyword)}'"
            )

    @pytest.mark.asyncio
    async def test_skill_router_routes_via_manifest_intents(self):
        """SkillRouter resolves keywords from SKILL.md intents without hardcoding."""
        router = SkillRouter(user_id="test-user")
        direct_map = router.get_direct_skill_map()
        assert "price" in direct_map
        assert "holdings" in direct_map
        assert "macro" in direct_map
        assert "momentum" in direct_map


class TestSkillsApiEndpoints:
    """Verify GET/POST endpoints for skills in FastAPI."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("OWNER_ID", "test-owner")
        app = FastAPI()
        app.include_router(ep.router, prefix="/api/v1/skills")
        return TestClient(app)

    def test_get_skills_list(self, client):
        resp = client.get("/api/v1/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert "skills" in data
        assert "pending_count" in data
        assert len(data["skills"]) >= 20

        names = {s["name"] for s in data["skills"]}
        assert "get_market_data" in names
        assert "distill_insight" in names
        assert "knowledge_vault" in names

    def test_toggle_skill(self, client):
        # Toggle get_market_data
        resp = client.post("/api/v1/skills/get_market_data/toggle", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

        # Re-enable
        resp = client.post("/api/v1/skills/get_market_data/toggle", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "enabled"

    def test_toggle_nonexistent_skill(self, client):
        resp = client.post("/api/v1/skills/non_existent_skill_xyz/toggle")
        assert resp.status_code == 404
