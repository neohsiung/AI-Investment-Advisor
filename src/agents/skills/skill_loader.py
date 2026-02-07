import os
import yaml
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Skill:
    name: str
    description: str
    metadata: Dict[str, Any]
    instruction: str
    code_path: Optional[str] = None

class SkillLoader:
    """
    OpenClaw Skill System.
    Parses `SKILL.md` files to register tools dynamically.
    """

    def __init__(self, skills_dir: str = "src/agents/skills"):
        self.skills_dir = skills_dir
        self.skills: Dict[str, Skill] = {}
        # Ensure dir exists
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir, exist_ok=True)

    def load_skills(self) -> Dict[str, Skill]:
        """
        Scans the skills directory and loads all SKILL.md files.
        Returns a dictionary of loaded skills.
        """
        self.skills = {}
        if not os.path.exists(self.skills_dir):
            return {}

        for root, dirs, files in os.walk(self.skills_dir):
            for file in files:
                if file == "SKILL.md":
                    full_path = os.path.join(root, file)
                    try:
                        skill = self._parse_skill_file(full_path)
                        if skill:
                            self.skills[skill.name] = skill
                    except Exception as e:
                        logger.error(f"SkillLoader: Failed to load {full_path}: {e}")
        
        logger.info(f"SkillLoader: Loaded {len(self.skills)} skills.")
        return self.skills

    def _parse_skill_file(self, file_path: str) -> Optional[Skill]:
        """
        Parses a single SKILL.md file.
        Format:
        ---
        name: tool_name
        description: ...
        metadata: ...
        ---
        ## Instruction
        ...
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split Frontmatter and Content
        if not content.startswith("---"):
            logger.warning(f"SkillLoader: Invalid format (missing frontmatter) in {file_path}")
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        yaml_content = parts[1]
        markdown_body = parts[2].strip()

        try:
            meta = yaml.safe_load(yaml_content)
            name = meta.get("name")
            desc = meta.get("description", "")
            metadata = meta.get("metadata", {})
            
            if not name:
                logger.warning(f"SkillLoader: Missing 'name' in {file_path}")
                return None

            # Check OS restrictions
            openclaw_meta = metadata.get("openclaw", {})
            allowed_os = openclaw_meta.get("os", [])
            if allowed_os:
                import sys
                current_os = "darwin" if sys.platform == "darwin" else "linux" # simple check
                if current_os not in allowed_os:
                    logger.debug(f"SkillLoader: Skipping {name} (OS mismatch: {current_os} not in {allowed_os})")
                    return None

            return Skill(
                name=name,
                description=desc,
                metadata=metadata,
                instruction=markdown_body,
                code_path=os.path.dirname(file_path)
            )

        except yaml.YAMLError as e:
            logger.error(f"SkillLoader: YAML error in {file_path}: {e}")
            return None

    def get_skill_registry_xml(self) -> str:
        """
        Generates XML format list of skills for System Prompt injection.
        """
        xml = "<tools>\n"
        for name, skill in self.skills.items():
            xml += f'  <tool name="{name}">\n'
            xml += f'    <description>{skill.description}</description>\n'
            xml += f'    <instruction>\n{skill.instruction}\n    </instruction>\n'
            xml += '  </tool>\n'
        xml += "</tools>"
        return xml

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    loader = SkillLoader()
    skills = loader.load_skills()
    print(loader.get_skill_registry_xml())
