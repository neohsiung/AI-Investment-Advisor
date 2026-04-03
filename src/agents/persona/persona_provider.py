"""
Persona Provider — OpenClaw-style MD + YAML Frontmatter Persona Loader.
人格提供者 — 相容 OpenClaw 的 MD + YAML Frontmatter 人格載入器。

Design Philosophy:
  - Persona files follow the SKILL.md convention (YAML frontmatter + Markdown body)
  - YAML frontmatter → structured metadata (name, tone, emoji_style, etc.)
  - Markdown body → system_prompt_prefix (injected before IDENTITY.md)
  - Agent reads the markdown body as natural-language personality instructions

遵循規範:
  - 規範四 (模組化設計): 獨立可單元測試
  - 規範八 (動態指標原則): 動態載入 persona 檔案
  - 規範十五 (AI-Support First): 聲明式結構化
"""

import os
import yaml
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentPersona:
    """
    Defines an agent's personality, tone, and behavioral constraints.
    定義 Agent 的人格、語氣與行為約束。

    Loaded from an .md file with YAML frontmatter (OpenClaw SKILL.md pattern).
    """
    name: str
    display_name: str = ""
    tone: str = "professional"
    language_preference: str = "zh-TW"
    emoji_style: str = "moderate"
    behavioral_rules: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    # Markdown body — natural-language personality instructions
    system_prompt_prefix: str = ""

    def get_rules_text(self) -> str:
        """Format behavioral rules as a bullet list for prompt injection."""
        if not self.behavioral_rules:
            return ""
        lines = [f"- {rule}" for rule in self.behavioral_rules]
        return "**Behavioral Rules:**\n" + "\n".join(lines)

    def render_prefix(self) -> str:
        """
        Render the full persona prefix for system prompt injection.
        渲染完整的人格前綴，用於系統提示詞注入。
        """
        parts = []
        if self.system_prompt_prefix:
            parts.append(self.system_prompt_prefix.strip())
        rules = self.get_rules_text()
        if rules:
            parts.append(rules)
        return "\n\n".join(parts)


class PersonaProvider:
    """
    Loads and manages agent personas from .md files (OpenClaw SKILL.md pattern).
    從 .md 檔案載入並管理 Agent 人格（OpenClaw SKILL.md 格式）。

    Directory structure:
        config/personas/
        ├── conversation.md
        ├── cio.md
        ├── sentinel.md
        └── ...

    Each file:
        ---
        name: conversation
        display_name: 投資顧問小安
        tone: professional_friendly
        ...
        ---
        # Persona Instructions (Markdown body)
        你是一位專業且友善的投資顧問助理...
    """

    DEFAULT_PERSONAS_DIR = "config/personas"

    def __init__(self, personas_dir: str = None):
        self._personas_dir = personas_dir or self.DEFAULT_PERSONAS_DIR
        self._personas: Dict[str, AgentPersona] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load all persona files on first access."""
        if self._loaded:
            return
        self._loaded = True
        self._load_all()

    def _load_all(self) -> None:
        """Scan personas directory and load all .md files."""
        if not os.path.isdir(self._personas_dir):
            logger.warning(
                f"PersonaProvider: Directory not found: {self._personas_dir}. "
                "Using default personas."
            )
            return

        for entry in os.scandir(self._personas_dir):
            if entry.is_file() and entry.name.endswith(".md"):
                try:
                    persona = self._parse_persona_file(entry.path)
                    if persona:
                        self._personas[persona.name] = persona
                        logger.info(
                            f"PersonaProvider: Loaded persona '{persona.name}' "
                            f"({persona.display_name})"
                        )
                except Exception as e:
                    logger.error(
                        f"PersonaProvider: Failed to load {entry.path}: {e}"
                    )

        logger.info(
            f"PersonaProvider: Loaded {len(self._personas)} personas from "
            f"{self._personas_dir}"
        )

    def _parse_persona_file(self, file_path: str) -> Optional[AgentPersona]:
        """
        Parse a single .md persona file (YAML frontmatter + Markdown body).
        解析單一 .md 人格檔案（YAML frontmatter + Markdown body）。
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.startswith("---"):
            logger.warning(
                f"PersonaProvider: Invalid format (missing frontmatter) in "
                f"{file_path}"
            )
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            logger.warning(
                f"PersonaProvider: Incomplete frontmatter in {file_path}"
            )
            return None

        yaml_content = parts[1]
        markdown_body = parts[2].strip()

        try:
            meta = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError as e:
            logger.error(f"PersonaProvider: YAML error in {file_path}: {e}")
            return None

        name = meta.get("name")
        if not name:
            logger.warning(f"PersonaProvider: Missing 'name' in {file_path}")
            return None

        return AgentPersona(
            name=name,
            display_name=meta.get("display_name", name),
            tone=meta.get("tone", "professional"),
            language_preference=meta.get("language_preference", "zh-TW"),
            emoji_style=meta.get("emoji_style", "moderate"),
            behavioral_rules=meta.get("behavioral_rules", []),
            version=meta.get("version", "1.0.0"),
            tags=meta.get("tags", []),
            system_prompt_prefix=markdown_body,
        )

    # ── Public API ───────────────────────────────────────────

    def get_persona(self, agent_name: str) -> Optional[AgentPersona]:
        """
        Get persona for a specific agent role.
        取得特定 Agent 角色的人格設定。

        Falls back to None if no persona file exists (agent uses default prompts).
        """
        self._ensure_loaded()
        return self._personas.get(agent_name)

    def get_or_default(self, agent_name: str) -> AgentPersona:
        """
        Get persona or return a minimal default.
        取得人格或回傳最小預設值。
        """
        persona = self.get_persona(agent_name)
        if persona:
            return persona
        return AgentPersona(name=agent_name, display_name=agent_name)

    def list_personas(self) -> List[str]:
        """List all loaded persona names."""
        self._ensure_loaded()
        return list(self._personas.keys())

    def reload(self) -> None:
        """Force reload all persona files."""
        self._loaded = False
        self._personas.clear()
        self._ensure_loaded()

    def update_persona_file(
        self, agent_name: str, updates: Dict[str, Any]
    ) -> bool:
        """
        Update a persona's YAML frontmatter and/or body in-place.
        原地更新人格的 YAML frontmatter 和/或 body。

        Used for persona optimization feedback loop.
        """
        file_path = os.path.join(self._personas_dir, f"{agent_name}.md")
        if not os.path.exists(file_path):
            logger.warning(
                f"PersonaProvider: Cannot update — file not found: {file_path}"
            )
            return False

        persona = self._parse_persona_file(file_path)
        if not persona:
            return False

        # Apply updates to metadata
        meta_updates = {}
        for key in [
            "display_name", "tone", "language_preference",
            "emoji_style", "behavioral_rules", "version", "tags",
        ]:
            if key in updates:
                meta_updates[key] = updates[key]
                setattr(persona, key, updates[key])

        # Apply body update
        new_body = updates.get("system_prompt_prefix", persona.system_prompt_prefix)

        # Reconstruct file
        meta_dict = {
            "name": persona.name,
            "display_name": persona.display_name,
            "tone": persona.tone,
            "language_preference": persona.language_preference,
            "emoji_style": persona.emoji_style,
            "version": persona.version,
            "tags": persona.tags,
        }
        if persona.behavioral_rules:
            meta_dict["behavioral_rules"] = persona.behavioral_rules

        yaml_str = yaml.dump(
            meta_dict,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"---\n{yaml_str}---\n\n{new_body}\n")

        # Refresh cache
        self._personas[persona.name] = persona
        logger.info(f"PersonaProvider: Updated persona '{agent_name}'")
        return True


# ── Singleton ────────────────────────────────────────────────

_default_provider: Optional[PersonaProvider] = None


def get_default_persona_provider() -> PersonaProvider:
    """Get module-level singleton PersonaProvider."""
    global _default_provider
    if _default_provider is None:
        _default_provider = PersonaProvider()
    return _default_provider
