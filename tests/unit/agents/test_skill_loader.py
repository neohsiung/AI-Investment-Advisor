import pytest
import os
import yaml
from src.agents.skills.skill_loader import SkillLoader

@pytest.fixture
def temp_skill_dir(tmp_path):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    
    # Create a valid skill
    valid_skill = skill_dir / "valid_skill"
    valid_skill.mkdir()
    (valid_skill / "SKILL.md").write_text("""---
name: valid_skill
description: A valid test skill
version: 1.0.0
category: test
tier: fast
input_schema:
  type: object
  properties:
    param1: {type: string}
---
# Instruction
Test instruction
""")
    
    # Create an invalid skill (missing name)
    invalid_skill = skill_dir / "invalid_skill"
    invalid_skill.mkdir()
    (invalid_skill / "SKILL.md").write_text("""---
description: Missing name
---
Body
""")
    
    return str(skill_dir)

def test_discover_skills(temp_skill_dir):
    loader = SkillLoader(skills_dir=temp_skill_dir)
    metadata = loader.discover_skills()
    
    assert "valid_skill" in metadata
    assert metadata["valid_skill"].description == "A valid test skill"
    assert "invalid_skill" not in metadata

def test_load_skills(temp_skill_dir):
    loader = SkillLoader(skills_dir=temp_skill_dir)
    skills = loader.load_skills()
    
    assert "valid_skill" in skills
    skill = skills["valid_skill"]
    assert skill.instruction == "# Instruction\nTest instruction".replace("\\n", "\n")
    assert skill.input_schema["properties"]["param1"]["type"] == "string"

def test_get_skill_registry_xml(temp_skill_dir):
    loader = SkillLoader(skills_dir=temp_skill_dir)
    loader.load_skills()
    xml = loader.get_skill_registry_xml()
    
    assert "<tool name=\"valid_skill\"" in xml
    assert "<description>A valid test skill</description>" in xml
    assert "param1" in xml
