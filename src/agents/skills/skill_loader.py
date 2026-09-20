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
import importlib.util
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
    intents: List[str] = field(default_factory=list)
    enabled: bool = True
    async_execution: bool = False


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
    intents: List[str] = field(default_factory=list)
    enabled: bool = True
    async_execution: bool = False


class SkillLoader:
    """
    3-Tier Progressive Disclosure Skill Loader.
    三層漸進式揭露技能載入器。

    Layer 1 (Metadata):  SKILL.md frontmatter → fast discovery
    Layer 2 (Manifest):  SKILL.md frontmatter → OS config, extended metadata
    Layer 3 (Detail):    SKILL.md body → full instruction for prompt injection
    """

    def __init__(self, skills_dir: str = "src/agents/skills", user_id: str = None):
        self.skills_dir = skills_dir
        self.user_id = user_id
        self.skills: Dict[str, Skill] = {}
        self._metadata_cache: Dict[str, SkillMetadata] = {}
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir, exist_ok=True)

    def run_skill(self, skill_name: str, **kwargs) -> Any:
        """
        Dynamically load and execute a skill's implementation (impl.py).
        動態載入並執行技能實作 (impl.py)。
        """
        # Ensure user_id is in kwargs if passed in __init__
        if self.user_id and "user_id" not in kwargs:
            kwargs["user_id"] = self.user_id

        # 1. Locate skill directory
        skill_dir = os.path.join(self.skills_dir, skill_name)
        if not os.path.isdir(skill_dir):
            # Fallback check in sub-directories
            for root, dirs, _ in os.walk(self.skills_dir):
                if skill_name in dirs:
                    skill_dir = os.path.join(root, skill_name)
                    break
            else:
                raise ValueError(f"Skill '{skill_name}' not found in {self.skills_dir}")

        impl_path = os.path.join(skill_dir, "impl.py")
        if not os.path.exists(impl_path):
            raise AttributeError(f"Skill '{skill_name}' has no implementation (impl.py) at {skill_dir}")

        # 2. Dynamic Import
        try:
            module_name = f"src.agents.skills.{skill_name}.impl"
            spec = importlib.util.spec_from_file_location(module_name, impl_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {impl_path}")
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 3. Execute main function (assumed to have same name as skill)
            func = getattr(module, skill_name, None)
            if not func:
                # Fallback: look for any function if only one exists or try 'run'
                func = getattr(module, "run", None)
                if not func:
                    raise AttributeError(f"Module {module_name} has no function '{skill_name}' or 'run'")

            import inspect
            if inspect.iscoroutinefunction(func):
                return func(**kwargs)
            else:
                # Wrap sync in a way that it can be awaited if the caller expects a coroutine
                async def _sync_wrapper():
                    return func(**kwargs)
                return _sync_wrapper()

        except Exception as e:
            logger.error(f"SkillLoader: Failed to run skill '{skill_name}': {e}")
            raise

    # ── Layer 1: Metadata Discovery ──────────────────────────

    def _extract_frontmatter(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract YAML frontmatter from SKILL.md.

        Delegates to src/utils/frontmatter.py, shared with PersonaProvider and the
        agent registry. This method used to read only the first 4096 bytes "as
        that is usually enough": frontmatter longer than that yielded fewer than
        three parts, the method returned None, and the skill silently vanished
        from discovery with no error logged. The shared parser reads whole files.

        原本只讀前 4096 bytes（「通常足夠」）：frontmatter 超過即回傳 None，
        該 skill 會在毫無錯誤訊息的情況下從探索結果消失。共用解析器完整讀取檔案。
        """
        from src.utils.frontmatter import read_meta

        return read_meta(file_path)

    def is_skill_enabled(self, name: str, default_enabled: bool = True) -> bool:
        """Check whether a skill is enabled for this user or globally."""
        if not self.user_id:
            return default_enabled
        try:
            from src.services.settings_service import SettingsService
            svc = SettingsService(user_id=self.user_id)
            val = svc.get_setting(f"skill_{name}_enabled")
            if val is not None:
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    return val.strip().lower() in ("true", "1", "yes")
        except Exception as e:
            logger.debug(f"SkillLoader: could not check setting for skill_{name}_enabled: {e}")
        return default_enabled

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

                    raw_enabled = raw.get("enabled", True)
                    if isinstance(raw_enabled, str):
                        raw_enabled = raw_enabled.strip().lower() in ("true", "1", "yes")
                    is_enabled = self.is_skill_enabled(name, bool(raw_enabled))

                    raw_intents = raw.get("intents", [])
                    if isinstance(raw_intents, str):
                        raw_intents = [raw_intents]
                    elif not isinstance(raw_intents, list):
                        raw_intents = []
                    intents = [str(x).strip() for x in raw_intents if x]

                    raw_async = raw.get("async", False)
                    if isinstance(raw_async, str):
                        raw_async = raw_async.strip().lower() in ("true", "1", "yes")

                    tags = raw.get("tags") or raw.get("categories") or []
                    if isinstance(tags, str):
                        tags = [tags]

                    meta = SkillMetadata(
                        name=name,
                        version=str(raw.get("version", "1.0.0")),
                        description=raw.get("description", ""),
                        category=raw.get("category", "general"),
                        tier=raw.get("tier", "fast"),
                        input_schema=raw.get("input_schema", {}),
                        output_schema=raw.get("output_schema", {}),
                        platform=raw.get("platform", ["linux", "darwin"]),
                        tags=tags,
                        intents=intents,
                        enabled=is_enabled,
                        async_execution=bool(raw_async),
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
        from src.utils.frontmatter import parse_file

        try:
            doc = parse_file(file_path)
            meta_raw = doc.meta
            markdown_body = doc.body
        except Exception as e:
            logger.error(f"SkillLoader: Could not read {file_path}: {e}")
            return None

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

        raw_enabled = meta_raw.get("enabled", layer1.enabled if layer1 else True)
        if isinstance(raw_enabled, str):
            raw_enabled = raw_enabled.strip().lower() in ("true", "1", "yes")
        is_enabled = self.is_skill_enabled(name, bool(raw_enabled))

        raw_intents = meta_raw.get("intents", layer1.intents if layer1 else [])
        if isinstance(raw_intents, str):
            raw_intents = [raw_intents]
        elif not isinstance(raw_intents, list):
            raw_intents = []
        intents = [str(x).strip() for x in raw_intents if x]

        raw_async = meta_raw.get("async", layer1.async_execution if layer1 else False)
        if isinstance(raw_async, str):
            raw_async = raw_async.strip().lower() in ("true", "1", "yes")

        tags = meta_raw.get("tags") or meta_raw.get("categories") or (layer1.tags if layer1 else [])
        if isinstance(tags, str):
            tags = [tags]

        return Skill(
            name=name,
            description=desc,
            metadata=metadata,
            instruction=markdown_body,
            code_path=os.path.dirname(file_path),
            version=str(meta_raw.get("version", layer1.version if layer1 else "1.0.0")),
            category=meta_raw.get("category", layer1.category if layer1 else "general"),
            tier=meta_raw.get("tier", layer1.tier if layer1 else "fast"),
            input_schema=layer1.input_schema if layer1 else meta_raw.get("input_schema", {}),
            output_schema=layer1.output_schema if layer1 else meta_raw.get("output_schema", {}),
            platform=meta_raw.get("platform", layer1.platform if layer1 else ["linux", "darwin"]),
            tags=tags,
            intents=intents,
            enabled=is_enabled,
            async_execution=bool(raw_async),
        )

    def get_direct_skill_map(self) -> Dict[str, str]:
        """
        Return intent -> skill_name mapping for all active, enabled skills.
        回傳所有已啟用技能的「意圖關鍵字 -> 技能名稱」映射表。
        """
        if not self._metadata_cache:
            self.discover_skills()
        mapping = {}
        for skill_name, meta in self._metadata_cache.items():
            if not meta.enabled:
                continue
            for intent in meta.intents:
                mapping[intent.lower().strip()] = skill_name
        return mapping

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
