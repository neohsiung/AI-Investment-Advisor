"""
Agent, prompt and persona editing.

The declarations behind these endpoints are config/agents/*.md manifests; the
prompt overrides they read and write are rows in `user_custom_prompts`.

That split matches the rest of the system: product definition ships in files, user
state lives in the database. It also makes this module the first writer
`user_custom_prompts` has ever had — the table, its ORM model and the
`prompt_repository.log_change`/`get_history` audit pair all existed already, with
no code path writing to any of them outside a verification script.

SAFETY: `POST /agents/{id}/test` runs a real agent against real LLM credentials.
It forces `ai_trading_enabled=false` for the duration, because a prompt under test
must never reach the order path. It deliberately does NOT use TRADING_MODE=paper —
the eToro token has no demo permission, so paper mode makes every broker call fail
outright instead of degrading safely.

manifest（產品定義）在檔案，prompt 覆寫（使用者狀態）在資料庫。
本模組是 user_custom_prompts 表歷來第一個寫入端。
安全性：測試執行會強制 ai_trading_enabled=false；不使用 TRADING_MODE=paper
（本專案 token 無 demo 權限，paper 會讓所有 broker 呼叫直接失敗）。
"""
from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.v1.dependencies import get_current_user_id
from src.utils.logger import setup_logger

logger = setup_logger("API_Agents")
router = APIRouter()


# ── schemas ──────────────────────────────────────────────────────────────

class AgentSummary(BaseModel):
    id: str
    display_name: str
    impl: str
    default_tier: str
    description: str = ""
    workspace: Optional[str] = None
    persona: Optional[str] = None
    enabled: bool = True
    skills: List[str] = Field(default_factory=list)
    has_prompt_override: bool = False


class PromptDetail(BaseModel):
    agent: str
    prompt: str
    # Which of the four sources supplied this text — the UI shows it so an
    # operator knows whether they are looking at their own edit or a default.
    source: str
    has_override: bool


class PromptSaveRequest(BaseModel):
    prompt: str
    reason: str = "edited via UI"


class PersonaSummary(BaseModel):
    name: str
    display_name: str = ""
    tone: str = ""
    body: str = ""


class SwarmRoster(BaseModel):
    id: str
    sub_agents: List[Dict[str, Any]]


class TestRunRequest(BaseModel):
    input: str = "Summarise the current market in two sentences."


class TestRunResponse(BaseModel):
    agent: str
    output: str
    trading_was_disabled: bool


# ── helpers ──────────────────────────────────────────────────────────────

def _override_row(user_id: str, agent_name: str):
    """The stored prompt override for (user, agent), or None."""
    from sqlalchemy.orm import sessionmaker

    from src.data.database import get_db_engine
    from src.data.models import UserCustomPrompt

    session = sessionmaker(bind=get_db_engine())()
    try:
        return session.query(UserCustomPrompt).filter_by(
            user_id=user_id, agent_name=agent_name,
        ).first()
    finally:
        session.close()


def _resolve_prompt(user_id: str, manifest) -> tuple:
    """
    (text, source) for an agent's effective prompt.

    Mirrors BaseAgent._load_prompt's order exactly — override, manifest body,
    workspace files, legacy file — so the UI shows what the agent will actually
    use. A separate reimplementation here would be free to disagree with the
    agent, which is the one thing a prompt editor must not do.
    與 BaseAgent._load_prompt 的順序完全一致，確保 UI 顯示的就是代理實際使用的內容；
    另寫一份解析邏輯可能與代理不符，而這正是提示詞編輯器最不該發生的事。
    """
    import os

    row = _override_row(user_id, manifest.name)
    if row and row.custom_prompt:
        return row.custom_prompt, "override"

    if manifest.prompt.strip():
        return manifest.prompt.strip(), "manifest"

    workspace = manifest.workspace or manifest.name.lower().replace(" ", "-")
    ws_path = os.path.join("workspace", workspace)
    if os.path.isdir(ws_path):
        text = ""
        for filename in ("IDENTITY.md", "SOUL.md"):
            candidate = os.path.join(ws_path, filename)
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as fh:
                    text += fh.read() + "\n\n"
        if text.strip():
            return text.strip(), "workspace"

    return "", "none"


# ── agents ───────────────────────────────────────────────────────────────

@router.get("", response_model=List[AgentSummary])
async def list_agents(user_id: str = Depends(get_current_user_id)):
    """
    Every declared agent.

    Before the registry this list did not exist anywhere as data: the population
    was hardcoded three times over (the factory's if/elif chain, BaseAgent's
    workspace_map, and LLMAgentOverrideService.KNOWN_AGENT_NAMES).
    在註冊表之前，這份清單並不以資料形式存在——同一群代理硬編在三個地方。
    """
    from src.agents.registry import load_manifests

    out = []
    for m in sorted(load_manifests().values(), key=lambda x: x.id):
        row = _override_row(user_id, m.name)
        out.append(AgentSummary(
            id=m.id, display_name=m.name, impl=m.impl,
            default_tier=m.default_tier, description=m.description,
            workspace=m.workspace, persona=m.persona, enabled=m.enabled,
            skills=m.skills,
            has_prompt_override=bool(row and row.custom_prompt),
        ))
    return out


@router.get("/impls", response_model=List[str])
async def list_implementations(user_id: str = Depends(get_current_user_id)):
    """Implementation keys a manifest's `impl:` may name."""
    from src.agents.registry import list_impls

    return list_impls()


# ── prompts ──────────────────────────────────────────────────────────────

@router.get("/{agent_id}/prompt", response_model=PromptDetail)
async def get_prompt(agent_id: str, user_id: str = Depends(get_current_user_id)):
    from src.agents.registry import get_manifest

    manifest = get_manifest(agent_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")

    text, source = _resolve_prompt(user_id, manifest)
    return PromptDetail(
        agent=manifest.name, prompt=text, source=source,
        has_override=(source == "override"),
    )


@router.put("/{agent_id}/prompt", response_model=PromptDetail)
async def save_prompt(agent_id: str, payload: PromptSaveRequest,
                      user_id: str = Depends(get_current_user_id)):
    """
    Store a prompt override for this agent, with an audit entry.

    Writes to `user_custom_prompts` rather than to the manifest file: a prompt a
    person edited is user state, and keeping it in the database means a release
    that changes the shipped default cannot silently overwrite it.

    SAFETY BOUNDARY: a prompt cannot widen what an agent is permitted to do. Order
    placement still passes through RiskManager.check_constraints (daily trade
    caps, circuit breakers, the ai_trading_enabled gate), none of which reads the
    prompt. Editing text here changes what the agent SAYS, not what it may DO.

    寫入 user_custom_prompts 而非 manifest 檔：人為修改的提示詞屬於使用者狀態，
    放在資料庫可避免升級時被出貨預設值靜默覆寫。
    安全邊界：提示詞無法擴大代理的權限——下單仍須通過 RiskManager.check_constraints
    （每日上限、斷路器、ai_trading_enabled），而這些都不讀取提示詞。
    """
    from sqlalchemy.orm import sessionmaker

    from src.agents.registry import get_manifest
    from src.data.database import get_db_engine
    from src.data.models import UserCustomPrompt

    manifest = get_manifest(agent_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")

    new_text = payload.prompt.strip()
    if not new_text:
        # Deleting the override is a distinct operation (DELETE below); an empty
        # save would otherwise silently blank the agent's instructions.
        # 清空覆寫是另一個操作；空字串儲存會靜默清掉代理的指令。
        raise HTTPException(
            status_code=400,
            detail="prompt is empty — use DELETE to remove the override and fall "
                   "back to the shipped default",
        )

    old_text, _ = _resolve_prompt(user_id, manifest)

    session = sessionmaker(bind=get_db_engine())()
    try:
        row = session.query(UserCustomPrompt).filter_by(
            user_id=user_id, agent_name=manifest.name,
        ).first()
        if row:
            row.custom_prompt = new_text
        else:
            session.add(UserCustomPrompt(
                user_id=user_id, agent_name=manifest.name, custom_prompt=new_text,
            ))
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("failed to store prompt for %s: %s", manifest.name, exc)
        raise HTTPException(status_code=500, detail="could not store the prompt") from exc
    finally:
        session.close()

    # Audit trail via the repository that already existed for this purpose.
    try:
        from src.repositories.prompt_repository import AlchemyPromptRepository

        diff = "\n".join(difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(),
            fromfile="before", tofile="after", lineterm="",
        ))
        AlchemyPromptRepository().log_change(
            agent_name=manifest.name, reason=payload.reason,
            old_prompt=old_text, new_prompt=new_text, diff=diff, user_id=user_id,
        )
    except Exception as exc:
        # Losing the audit entry is not worth failing the save, but it must be
        # visible — an unlogged prompt change is an unexplained behaviour change.
        # 稽核記錄失敗不值得中止儲存，但必須可見：未記錄的提示詞變更等於無法解釋的行為變更。
        logger.warning("prompt saved but audit logging failed for %s: %s", manifest.name, exc)

    logger.info("prompt override stored for agent %s by %s", manifest.name, user_id)
    return await get_prompt(agent_id, user_id=user_id)


@router.delete("/{agent_id}/prompt", response_model=PromptDetail)
async def delete_prompt(agent_id: str, user_id: str = Depends(get_current_user_id)):
    """Remove the override, reverting to the shipped default."""
    from sqlalchemy.orm import sessionmaker

    from src.agents.registry import get_manifest
    from src.data.database import get_db_engine
    from src.data.models import UserCustomPrompt

    manifest = get_manifest(agent_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")

    old_text, _ = _resolve_prompt(user_id, manifest)

    session = sessionmaker(bind=get_db_engine())()
    try:
        session.query(UserCustomPrompt).filter_by(
            user_id=user_id, agent_name=manifest.name,
        ).delete()
        session.commit()
    finally:
        session.close()

    try:
        from src.repositories.prompt_repository import AlchemyPromptRepository

        AlchemyPromptRepository().log_change(
            agent_name=manifest.name, reason="override removed via UI",
            old_prompt=old_text, new_prompt="", diff="", user_id=user_id,
        )
    except Exception as exc:
        logger.warning("override removed but audit logging failed: %s", exc)

    return await get_prompt(agent_id, user_id=user_id)


@router.get("/{agent_id}/history")
async def prompt_history(agent_id: str, limit: int = 50,
                         user_id: str = Depends(get_current_user_id)):
    """
    Change history for this agent's prompt.

    Reads `prompt_repository.get_history`, which existed unused — the meta-prompt
    agent had a writer but nothing ever displayed the result.
    讀取既有但未被使用的 get_history：meta-prompt 代理有寫入端，卻沒有任何地方顯示結果。
    """
    from src.agents.registry import get_manifest
    from src.repositories.prompt_repository import AlchemyPromptRepository

    manifest = get_manifest(agent_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")

    try:
        rows = AlchemyPromptRepository().get_history(user_id, limit=limit) or []
    except Exception as exc:
        logger.warning("prompt history unavailable: %s", exc)
        return []

    out = []
    for r in rows:
        entry = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        if entry.get("agent_name") == manifest.name:
            out.append({k: (str(v) if v is not None else None) for k, v in entry.items()})
    return out


# ── personas ─────────────────────────────────────────────────────────────

@router.get("/personas/all", response_model=List[PersonaSummary])
async def list_personas(user_id: str = Depends(get_current_user_id)):
    """Personas from config/personas/*.md."""
    from pathlib import Path

    from src.utils.frontmatter import FrontmatterError, parse_file

    out = []
    directory = Path("config/personas")
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.md")):
        try:
            doc = parse_file(path)
        except (FrontmatterError, OSError) as exc:
            logger.warning("skipping persona %s: %s", path, exc)
            continue
        out.append(PersonaSummary(
            name=doc.get("name", path.stem),
            display_name=doc.get("display_name", ""),
            tone=doc.get("tone", ""),
            body=doc.body,
        ))
    return out


# ── swarms ───────────────────────────────────────────────────────────────

@router.get("/swarms/all", response_model=List[SwarmRoster])
async def list_swarms(user_id: str = Depends(get_current_user_id)):
    """
    Swarm sub-agent rosters from config/agents/swarms/*.yaml — names, instructions
    and tiers that were Python string literals inside each swarm's __init__.
    子代理名單：原本是各 swarm __init__ 中的 Python 字面值。
    """
    from src.agents.swarm.roster import load_roster, swarms_dir

    out = []
    directory = swarms_dir()
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.yaml")):
        roster = load_roster(path.stem)
        out.append(SwarmRoster(
            id=path.stem,
            sub_agents=[
                {"name": s.name, "tier": s.tier, "column": s.column,
                 "instruction": s.instruction}
                for s in roster
            ],
        ))
    return out


# ── test run ─────────────────────────────────────────────────────────────

@router.post("/{agent_id}/test", response_model=TestRunResponse)
async def test_run(agent_id: str, payload: TestRunRequest,
                   user_id: str = Depends(get_current_user_id)):
    """
    Run the agent once against its current prompt.

    This spends real LLM credits and constructs a real agent, so trading is pinned
    off for the duration: `ai_trading_enabled` is forced to false and restored
    afterwards, including on failure. A prompt being evaluated must not be able to
    reach the order path.

    Why not TRADING_MODE=paper: the configured eToro token has no demo permission,
    so paper mode makes every broker call return InsufficientPermissions — a hard
    failure, not a safe sandbox.

    此端點會花費真實 LLM 費用並建構真實代理，故執行期間強制關閉交易
    （ai_trading_enabled=false，結束後還原，失敗亦還原）。
    不用 TRADING_MODE=paper：本專案 token 無 demo 權限，paper 會讓 broker 呼叫全數失敗。
    """
    from src.agents.registry import AgentRegistryError
    from src.services.settings_service import SettingsService

    settings = SettingsService(user_id=user_id)
    previous = settings.get_setting("ai_trading_enabled")

    try:
        settings.save_settings_bulk({"ai_trading_enabled": False})
    except Exception as exc:
        # If the brake cannot be applied, do not run the agent at all.
        # 無法套用煞車就不執行代理。
        logger.error("refusing test run — could not disable trading: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="could not disable trading for the test run; refusing to proceed",
        ) from exc

    try:
        from src.agents.factory import AgentFactory

        agent = AgentFactory.create_agent(agent_id, user_id=user_id)
        result = await agent.run({"topic": payload.input, "input": payload.input})
        output = result if isinstance(result, str) else str(result)
    except (AgentRegistryError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("test run failed for %s", agent_id)
        raise HTTPException(status_code=500, detail=f"test run failed: {exc}") from exc
    finally:
        # Restore whatever was there before, including when the run raised.
        try:
            if previous is not None:
                settings.save_settings_bulk({"ai_trading_enabled": previous})
        except Exception as exc:
            # This one matters: failing to restore leaves trading disabled.
            # 還原失敗會讓交易保持關閉，必須明確記錄為錯誤。
            logger.error(
                "TEST RUN LEFT ai_trading_enabled=false — restore failed: %s", exc,
            )

    return TestRunResponse(
        agent=agent_id, output=output[:8000], trading_was_disabled=True,
    )
