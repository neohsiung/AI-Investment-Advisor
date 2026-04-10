"""
Skill Loader — Progressive Disclosure 3-Tier Architecture.
技能載入器 — 三層漸進式揭露架構。

Loading Tiers:
  1. Metadata (SKILL.md frontmatter) — Lightweight discovery: name, description, schema
  2. Manifest (SKILL.md frontmatter) — Full config: OS restrictions, metadata
  3. Detail (SKILL.md body) — Full instruction text for system prompt injection

遵循規範:
  - 規範三 (Spec-Driven Design): Pydantic schema 驗證 Skill I/O
  - 規範四 (模組化設計): 獨立可單元測試
  - 規範八 (動態指標原則): 支援 YAML Frontmatter 動態發現
"""

import os
import json
import yaml
import logging
import sys
import re
import pathlib
import subprocess
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class SkillTier(str, Enum):
    """Skill execution tier (maps to LLM tier choice)."""
    FAST = "fast"
    SMART = "smart"
    ADVANCED = "advanced"


@dataclass
class SkillMetadata:
    """
    Layer 1: Lightweight metadata from SKILL.md frontmatter.
    第一層：來自 SKILL.md Frontmatter 的輕量級元資料。
    """
    name: str
    version: str = "1.0.0"
    description: str = ""
    category: str = "general"
    tier: str = "fast"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    platform: List[str] = field(default_factory=lambda: ["linux", "darwin"])
    tags: List[str] = field(default_factory=list)


@dataclass
class Skill:
    """
    Full skill definition (Layer 1 + 2 + 3).
    完整技能定義（第一層 + 第二層 + 第三層）。
    """
    name: str
    description: str
    metadata: Dict[str, Any]
    instruction: str
    code_path: Optional[str] = None
    # Layer 1 fields
    version: str = "1.0.0"
    category: str = "general"
    tier: str = "fast"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    platform: List[str] = field(default_factory=lambda: ["linux", "darwin"])
    tags: List[str] = field(default_factory=list)


class SkillLoader:
    """
    3-Tier Progressive Disclosure Skill Loader.
    三層漸進式揭露技能載入器。

    Layer 1 (Metadata):  SKILL.md frontmatter → fast discovery
    Layer 2 (Manifest):  SKILL.md frontmatter → OS config, extended metadata
    Layer 3 (Detail):    SKILL.md body → full instruction for prompt injection
    """

    def __init__(self, skills_dir: str = "src/agents/skills"):
        self.skills_dir = skills_dir
        self.skills: Dict[str, Skill] = {}
        self._metadata_cache: Dict[str, SkillMetadata] = {}
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir, exist_ok=True)

    # ── Layer 1: Metadata Discovery ──────────────────────────

    def _extract_frontmatter(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Efficiently extract YAML Frontmatter from SKILL.md.
        高效地從 SKILL.md 提取 YAML Frontmatter。
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # Read the first 4KB, usually enough for frontmatter
                # 讀取前 4KB，通常足以包含 frontmatter
                chunk = f.read(4096)
                if not chunk.startswith("---"):
                    return None
                parts = chunk.split("---", 2)
                if len(parts) < 3:
                    return None
                return yaml.safe_load(parts[1])
        except Exception as e:
            logger.error(f"SkillLoader: Error reading frontmatter from {file_path}: {e}")
            return None

    def discover_skills(self) -> Dict[str, SkillMetadata]:
        """
        Layer 1: Scan for SKILL.md files and extract basic metadata.
        第一層：掃描 SKILL.md 檔案並提取基本元資料。
        """
        self._metadata_cache = {}
        current_platform = "darwin" if sys.platform == "darwin" else "linux"

        if not os.path.exists(self.skills_dir):
            return {}

        for root, dirs, files in os.walk(self.skills_dir):
            if "SKILL.md" in files:
                full_path = os.path.join(root, "SKILL.md")
                raw = self._extract_frontmatter(full_path)
                if not raw:
                    continue

                try:
                    name = raw.get("name")
                    if not name:
                        continue

                    meta = SkillMetadata(
                        name=name,
                        version=raw.get("version", "1.0.0"),
                        description=raw.get("description", ""),
                        category=raw.get("category", "general"),
                        tier=raw.get("tier", "fast"),
                        input_schema=raw.get("input_schema", {}),
                        output_schema=raw.get("output_schema", {}),
                        platform=raw.get("platform", ["linux", "darwin"]),
                        tags=raw.get("tags", []),
                    )

                    # Platform filter
                    if meta.platform and current_platform not in meta.platform:
                        logger.debug(
                            f"SkillLoader: Skipping {meta.name} "
                            f"(platform {current_platform} not in {meta.platform})"
                        )
                        continue

                    self._metadata_cache[name] = meta
                except Exception as e:
                    logger.error(f"SkillLoader: Invalid metadata in {full_path}: {e}")

        logger.info(f"SkillLoader: Discovered {len(self._metadata_cache)} skills (Layer 1).")
        return self._metadata_cache

    # ── Layer 2+3: Full Loading ──────────────────────────────

    def load_skills(self) -> Dict[str, Skill]:
        """
        Full load: Parse Layer 2 (frontmatter) and Layer 3 (body).
        完整載入：解析第二層（Frontmatter）與第三層（Body）。
        """
        # Start with Layer 1 discovery if cache is empty
        if not self._metadata_cache:
            self.discover_skills()
            
        self.skills = {}

        if not os.path.exists(self.skills_dir):
            return {}

        for root, dirs, files in os.walk(self.skills_dir):
            if "SKILL.md" in files:
                full_path = os.path.join(root, "SKILL.md")
                try:
                    skill = self._parse_skill_file(full_path)
                    if skill:
                        self.skills[skill.name] = skill
                except Exception as e:
                    logger.error(f"SkillLoader: Failed to load {full_path}: {e}")

        logger.info(f"SkillLoader: Loaded {len(self.skills)} skills (Layer 2+3).")
        return self.skills

    def _parse_skill_file(self, file_path: str) -> Optional[Skill]:
        """
        Parses a single SKILL.md file (Layer 2 + 3).
        Merges with Layer 1 metadata from cache.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"SkillLoader: Could not read {file_path}: {e}")
            return None

        # Split Frontmatter and Content
        if not content.startswith("---"):
            logger.warning(
                f"SkillLoader: Invalid format (missing frontmatter) in {file_path}"
            )
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        yaml_content = parts[1]
        markdown_body = parts[2].strip()

        try:
            meta_raw = yaml.safe_load(yaml_content)
            name = meta_raw.get("name")
            desc = meta_raw.get("description", "")
            metadata = meta_raw.get("metadata", {})

            if not name:
                logger.warning(f"SkillLoader: Missing 'name' in {file_path}")
                return None

            # Check OS restrictions from metadata
            openclaw_meta = metadata.get("openclaw", {})
            allowed_os = openclaw_meta.get("os", [])
            if allowed_os:
                current_os = "darwin" if sys.platform == "darwin" else "linux"
                if current_os not in allowed_os:
                    logger.debug(
                        f"SkillLoader: Skipping {name} "
                        f"(OS mismatch: {current_os} not in {allowed_os})"
                    )
                    return None

            # Retrieve Layer 1 metadata from cache
            layer1 = self._metadata_cache.get(name)

            return Skill(
                name=name,
                description=desc,
                metadata=metadata,
                instruction=markdown_body,
                code_path=os.path.dirname(file_path),
                version=meta_raw.get("version", layer1.version if layer1 else "1.0.0"),
                category=meta_raw.get("category", layer1.category if layer1 else "general"),
                tier=meta_raw.get("tier", layer1.tier if layer1 else "fast"),
                input_schema=layer1.input_schema if layer1 else meta_raw.get("input_schema", {}),
                output_schema=layer1.output_schema if layer1 else meta_raw.get("output_schema", {}),
                platform=meta_raw.get("platform", layer1.platform if layer1 else ["linux", "darwin"]),
                tags=meta_raw.get("tags", layer1.tags if layer1 else []),
            )

        except yaml.YAMLError as e:
            logger.error(f"SkillLoader: YAML error in {file_path}: {e}")
            return None

    # ── Query API ────────────────────────────────────────────

    def get_skills_by_category(self, category: str) -> Dict[str, Skill]:
        """Filter loaded skills by category."""
        return {n: s for n, s in self.skills.items() if s.category == category}

    def get_skills_by_tier(self, tier: str) -> Dict[str, Skill]:
        """Filter loaded skills by execution tier."""
        return {n: s for n, s in self.skills.items() if s.tier == tier}

    def get_skills_by_tag(self, tag: str) -> Dict[str, Skill]:
        """Filter loaded skills by tag."""
        return {n: s for n, s in self.skills.items() if tag in s.tags}

    # ── Prompt Injection ─────────────────────────────────────

    def get_skill_registry_xml(self) -> str:
        """
        Generates XML format list of skills for System Prompt injection.
        產生 XML 格式的技能清單，用於系統提示詞注入。
        """
        xml = "<tools>\n"
        for name, skill in self.skills.items():
            xml += f'  <tool name="{name}" category="{skill.category}" tier="{skill.tier}">\n'
            xml += f"    <description>{skill.description}</description>\n"

            # Inject input schema if available
            if skill.input_schema:
                props = skill.input_schema.get("properties", {})
                required = skill.input_schema.get("required", [])
                if props:
                    xml += "    <parameters>\n"
                    for pname, pdef in props.items():
                        req = " required" if pname in required else ""
                        ptype = pdef.get("type", "string")
                        pdesc = pdef.get("description", "")
                        xml += f'      <param name="{pname}" type="{ptype}"{req}>{pdesc}</param>\n'
                    xml += "    </parameters>\n"

            xml += f"    <instruction>\n{skill.instruction}\n    </instruction>\n"
            xml += "  </tool>\n"
        xml += "</tools>"
        return xml


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = SkillLoader()
    # Layer 1 only
    metadata = loader.discover_skills()
    print(f"Discovered: {list(metadata.keys())}")
    # Full load
    skills = loader.load_skills()
    print(loader.get_skill_registry_xml())
