"""
Skills discovery, inspection, and activation endpoints.
技能探索、檢視與啟用/停用 REST 端點。

Manifests: src/agents/skills/*/SKILL.md
User overrides: SettingsService(user_id) -> skill_{name}_enabled
Pending queue: src/agents/skills/_pending/ managed by SkillScaffolder
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.v1.dependencies import get_current_user_id
from src.agents.skills.skill_loader import SkillLoader
from src.agents.skills.skill_scaffolder import SkillScaffolder
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("API_Skills")
router = APIRouter()


class SkillItem(BaseModel):
    name: str
    description: str = ""
    category: str = "general"
    tier: str = "fast"
    version: str = "1.0.0"
    intents: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    platform: List[str] = Field(default_factory=list)
    enabled: bool = True
    is_pending: bool = False
    has_impl: bool = False


class SkillListResponse(BaseModel):
    skills: List[SkillItem]
    pending_count: int = 0


class SkillToggleRequest(BaseModel):
    enabled: Optional[bool] = None  # If None, toggles current state


class SkillActionResponse(BaseModel):
    name: str
    status: str
    message: str


@router.get("", response_model=SkillListResponse)
def list_skills(user_id: str = Depends(get_current_user_id)):
    """
    List all active skills and pending skills awaiting approval.
    列出所有可用技能以及等待核准的待定技能。
    """
    loader = SkillLoader(user_id=user_id)
    discovered = loader.discover_skills()
    scaffolder = SkillScaffolder()
    pending_names = set(scaffolder.list_pending())

    skills_list: List[SkillItem] = []

    # Active skills
    for name, meta in sorted(discovered.items()):
        skill_dir = os.path.join(loader.skills_dir, name)
        has_impl = os.path.exists(os.path.join(skill_dir, "impl.py")) or os.path.exists(
            os.path.join(skill_dir, "cli.py")
        )

        skills_list.append(
            SkillItem(
                name=meta.name,
                description=meta.description,
                category=meta.category,
                tier=meta.tier,
                version=meta.version,
                intents=meta.intents,
                tags=meta.tags,
                platform=meta.platform,
                enabled=meta.enabled,
                is_pending=False,
                has_impl=has_impl,
            )
        )

    # Pending skills
    for pending_name in sorted(pending_names):
        pending_dir = os.path.join(scaffolder._pending_dir, pending_name)
        skill_md_path = os.path.join(pending_dir, "SKILL.md")
        desc = "Pending auto-generated skill"
        category = "general"
        if os.path.exists(skill_md_path):
            raw = loader._extract_frontmatter(skill_md_path)
            if raw:
                desc = raw.get("description", desc)
                category = raw.get("category", category)

        skills_list.append(
            SkillItem(
                name=pending_name,
                description=desc,
                category=category,
                tier="fast",
                version="0.1.0",
                intents=[],
                tags=["pending"],
                platform=["linux", "darwin"],
                enabled=False,
                is_pending=True,
                has_impl=os.path.exists(os.path.join(pending_dir, "impl.py")),
            )
        )

    return SkillListResponse(skills=skills_list, pending_count=len(pending_names))


@router.post("/{name}/toggle", response_model=SkillActionResponse)
def toggle_skill(
    name: str,
    body: Optional[SkillToggleRequest] = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Enable or disable a skill for the user.
    切換或設定技能的啟用/停用狀態。
    """
    loader = SkillLoader(user_id=user_id)
    discovered = loader.discover_skills()
    if name not in discovered:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{name}' not found",
        )

    current_meta = discovered[name]
    if body and body.enabled is not None:
        new_state = body.enabled
    else:
        new_state = not current_meta.enabled

    svc = SettingsService(user_id=user_id)
    svc.save_settings_bulk({f"skill_{name}_enabled": new_state})

    action_str = "enabled" if new_state else "disabled"
    return SkillActionResponse(
        name=name,
        status=action_str,
        message=f"Skill '{name}' has been {action_str}.",
    )


@router.post("/{name}/approve", response_model=SkillActionResponse)
def approve_pending_skill(name: str, user_id: str = Depends(get_current_user_id)):
    """
    Approve an auto-generated pending skill and move it to the active directory.
    核准自動產生的待定技能並移入正式目錄。
    """
    scaffolder = SkillScaffolder()
    if name not in scaffolder.list_pending():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending skill '{name}' not found in queue",
        )

    success = scaffolder.approve_and_activate(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to activate skill '{name}'",
        )

    return SkillActionResponse(
        name=name,
        status="activated",
        message=f"Skill '{name}' has been approved and moved to active directory.",
    )


@router.post("/{name}/reject", response_model=SkillActionResponse)
def reject_pending_skill(name: str, user_id: str = Depends(get_current_user_id)):
    """
    Reject an auto-generated pending skill and delete it from the queue.
    拒絕自動產生的待定技能並自佇列中刪除。
    """
    scaffolder = SkillScaffolder()
    if name not in scaffolder.list_pending():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending skill '{name}' not found in queue",
        )

    success = scaffolder.reject(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to reject skill '{name}'",
        )

    return SkillActionResponse(
        name=name,
        status="rejected",
        message=f"Pending skill '{name}' has been rejected and removed.",
    )
