"""
Tests for SkillScaffolder — Task 4B-3.
"""
import json
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.skills.gap_detector import GapReport
from src.agents.skills.skill_scaffolder import SkillScaffolder


class TestSkillScaffolder:
    def setup_method(self):
        """Create a temp directory for each test."""
        self.temp_dir = tempfile.mkdtemp(prefix="skill_scaffold_test_")
        self.scaffolder = SkillScaffolder(skills_base_dir=self.temp_dir)

    def teardown_method(self):
        """Cleanup temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _make_gap(self, name="test_skill", category="analysis"):
        return GapReport(
            is_gap=True,
            suggested_skill_name=name,
            suggested_category=category,
            reasoning="Test gap for unit testing",
            can_auto_scaffold=True,
            existing_similar="search_web",
        )

    def test_scaffold_creates_directory(self):
        gap = self._make_gap()
        path = self.scaffolder.scaffold(gap)
        assert os.path.isdir(path)
        assert "test_skill" in path

    def test_scaffold_creates_metadata_json(self):
        gap = self._make_gap()
        path = self.scaffolder.scaffold(gap)
        meta_path = os.path.join(path, "metadata.json")
        assert os.path.exists(meta_path)

        with open(meta_path, "r") as f:
            meta = json.load(f)
        assert meta["name"] == "test_skill"
        assert meta["category"] == "analysis"
        assert meta["version"] == "0.1.0"

    def test_scaffold_creates_skill_md(self):
        gap = self._make_gap()
        path = self.scaffolder.scaffold(gap)
        md_path = os.path.join(path, "SKILL.md")
        assert os.path.exists(md_path)

        with open(md_path, "r") as f:
            content = f.read()
        assert "test_skill" in content
        assert "auto_generated: true" in content

    def test_scaffold_creates_impl_py_stub(self):
        gap = self._make_gap()
        path = self.scaffolder.scaffold(gap)
        impl_path = os.path.join(path, "impl.py")
        assert os.path.exists(impl_path)

        with open(impl_path, "r") as f:
            content = f.read()
        assert "def test_skill" in content
        assert "TODO" in content

    def test_scaffold_with_custom_impl(self):
        gap = self._make_gap()
        custom = 'def test_skill(user_id): return "custom"'
        path = self.scaffolder.scaffold(gap, impl_code=custom)
        impl_path = os.path.join(path, "impl.py")
        with open(impl_path, "r") as f:
            content = f.read()
        assert 'return "custom"' in content

    def test_scaffold_goes_to_pending(self):
        gap = self._make_gap()
        path = self.scaffolder.scaffold(gap)
        assert "_pending" in path

    def test_list_pending(self):
        self.scaffolder.scaffold(self._make_gap("skill_a"))
        self.scaffolder.scaffold(self._make_gap("skill_b"))
        pending = self.scaffolder.list_pending()
        assert "skill_a" in pending
        assert "skill_b" in pending

    def test_approve_and_activate(self):
        self.scaffolder.scaffold(self._make_gap("activate_me"))
        assert "activate_me" in self.scaffolder.list_pending()

        result = self.scaffolder.approve_and_activate("activate_me")
        assert result is True
        assert "activate_me" not in self.scaffolder.list_pending()
        assert os.path.isdir(os.path.join(self.temp_dir, "activate_me"))

    def test_approve_nonexistent_fails(self):
        result = self.scaffolder.approve_and_activate("ghost_skill")
        assert result is False

    def test_reject(self):
        self.scaffolder.scaffold(self._make_gap("reject_me"))
        assert "reject_me" in self.scaffolder.list_pending()

        result = self.scaffolder.reject("reject_me")
        assert result is True
        assert "reject_me" not in self.scaffolder.list_pending()

    def test_reject_nonexistent(self):
        result = self.scaffolder.reject("ghost_skill")
        assert result is False

    def test_full_lifecycle(self):
        """scaffold → pending → approve → active → discoverable"""
        gap = self._make_gap("lifecycle_skill")
        self.scaffolder.scaffold(gap)

        # Pending
        assert "lifecycle_skill" in self.scaffolder.list_pending()
        assert not os.path.isdir(os.path.join(self.temp_dir, "lifecycle_skill"))

        # Activate
        self.scaffolder.approve_and_activate("lifecycle_skill")
        assert "lifecycle_skill" not in self.scaffolder.list_pending()
        active_path = os.path.join(self.temp_dir, "lifecycle_skill")
        assert os.path.isdir(active_path)
        assert os.path.exists(os.path.join(active_path, "metadata.json"))
        assert os.path.exists(os.path.join(active_path, "SKILL.md"))
        assert os.path.exists(os.path.join(active_path, "impl.py"))


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
