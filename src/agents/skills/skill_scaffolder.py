"""
Skill Scaffolder — Automated Skill Directory Generator.
Skill 骨架生成器 — 自動化 Skill 目錄產生器。

Generates compliant skill directory structure (metadata.json + SKILL.md + impl.py)
based on GapReport analysis. New skills are placed in a '_pending' directory
for mandatory user review before activation.

遵循規範:
  - 規範四 (模組化設計): 獨立可單元測試
  - 遵循 skill-scaffolding SKILL 標準
  - 安全控制: _pending/ 目錄先行，使用者核准後才移入正式目錄
"""

import json
import logging
import os
import shutil
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.agents.skills.gap_detector import GapReport

logger = logging.getLogger(__name__)


class SkillScaffolder:
    """
    Generates skill directory scaffolding based on gap analysis.
    根據缺口分析產生 Skill 目錄骨架。

    All new skills are generated in _pending/ first.
    Use approve_and_activate() to move to the active skill directory.
    """

    def __init__(self, skills_base_dir: str = None):
        if skills_base_dir is None:
            skills_base_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__))
            )
        self._base_dir = skills_base_dir
        self._pending_dir = os.path.join(skills_base_dir, "_pending")
        os.makedirs(self._pending_dir, exist_ok=True)

    def scaffold(
        self,
        gap: GapReport,
        user_context: str = "",
        impl_code: str = "",
    ) -> str:
        """
        Generate a new skill directory in _pending/.

        Args:
            gap: GapReport from GapDetector
            user_context: Additional context from the user conversation
            impl_code: Optional LLM-generated implementation code

        Returns:
            Absolute path to the generated skill directory
        """
        skill_name = gap.suggested_skill_name
        if not skill_name:
            raise ValueError("GapReport must have a suggested_skill_name")

        # Sanitize name
        skill_name = skill_name.strip().lower().replace("-", "_").replace(" ", "_")
        skill_dir = os.path.join(self._pending_dir, skill_name)

        # Create directory
        os.makedirs(skill_dir, exist_ok=True)

        # 1. Generate metadata.json
        metadata = {
            "name": skill_name,
            "version": "0.1.0",
            "description": gap.reasoning or f"Auto-generated skill: {skill_name}",
            "category": gap.suggested_category or "general",
            "tier": "fast",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User ID for context-aware execution"
                    }
                },
                "required": ["user_id"]
            },
            "output_schema": {
                "type": "string",
                "description": f"Result from {skill_name}"
            },
            "platform": ["linux", "darwin"],
            "tags": ["auto-generated", gap.suggested_category or "general"],
        }
        metadata_path = os.path.join(skill_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # 2. Generate SKILL.md
        skill_md = f"""---
name: {skill_name}
description: {gap.reasoning or f'Auto-generated skill: {skill_name}'}
metadata:
  openclaw:
    os: [linux, darwin]
  auto_generated: true
  gap_context: "{user_context[:200] if user_context else ''}"
---

# {skill_name.replace('_', ' ').title()}

{gap.reasoning or 'Automatically generated skill to fill a detected capability gap.'}

## When to Use

- 使用者的需求超出現有工具能力時
- 類似請求: {user_context[:100] if user_context else 'N/A'}

## Notes

> ⚠️ This skill was auto-generated and requires review before activation.
> Existing similar skill: {gap.existing_similar or 'None'}
"""
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(skill_md)

        # 3. Generate impl.py (with LLM-generated code or stub)
        if impl_code:
            impl_content = impl_code
        else:
            impl_content = f'''"""
Auto-generated implementation for {skill_name}.
⚠️ This is a stub — implement the actual logic before activating.
"""

import logging

logger = logging.getLogger(__name__)


def {skill_name}(user_id: str, **kwargs) -> str:
    """
    {gap.reasoning or f'Execute {skill_name} logic.'}

    Args:
        user_id: System user ID
        **kwargs: Additional parameters

    Returns:
        Result string
    """
    # TODO: Implement actual logic
    logger.info(f"Skill {skill_name} called for user {{user_id}} with {{kwargs}}")
    return f"[{skill_name}] Not yet implemented. Please complete the implementation."
'''

        impl_path = os.path.join(skill_dir, "impl.py")
        with open(impl_path, "w", encoding="utf-8") as f:
            f.write(impl_content)

        logger.info(
            f"SkillScaffolder: Generated scaffold for '{skill_name}' at {skill_dir}"
        )
        return os.path.abspath(skill_dir)

    def approve_and_activate(self, skill_name: str) -> bool:
        """
        Move a pending skill to the active skill directory.
        將待核准的 Skill 移入正式目錄。

        Args:
            skill_name: Name of the skill to activate

        Returns:
            True if successfully moved
        """
        pending_path = os.path.join(self._pending_dir, skill_name)
        active_path = os.path.join(self._base_dir, skill_name)

        if not os.path.isdir(pending_path):
            logger.error(f"SkillScaffolder: Pending skill '{skill_name}' not found")
            return False

        if os.path.exists(active_path):
            logger.error(
                f"SkillScaffolder: Active skill '{skill_name}' already exists"
            )
            return False

        try:
            shutil.move(pending_path, active_path)
            logger.info(
                f"SkillScaffolder: Activated skill '{skill_name}' → {active_path}"
            )
            return True
        except Exception as e:
            logger.error(f"SkillScaffolder: Failed to activate '{skill_name}': {e}")
            return False

    def reject(self, skill_name: str) -> bool:
        """
        Delete a pending skill directory.
        刪除待核准的 Skill 目錄。
        """
        pending_path = os.path.join(self._pending_dir, skill_name)
        if not os.path.isdir(pending_path):
            logger.warning(f"SkillScaffolder: Pending skill '{skill_name}' not found")
            return False

        try:
            shutil.rmtree(pending_path)
            logger.info(f"SkillScaffolder: Rejected and removed '{skill_name}'")
            return True
        except Exception as e:
            logger.error(f"SkillScaffolder: Failed to remove '{skill_name}': {e}")
            return False

    def list_pending(self) -> List[str]:
        """List all pending skills awaiting approval."""
        if not os.path.isdir(self._pending_dir):
            return []
        return [
            d for d in os.listdir(self._pending_dir)
            if os.path.isdir(os.path.join(self._pending_dir, d))
            and not d.startswith("_")
        ]
