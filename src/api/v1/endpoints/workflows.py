"""
Workflow CRUD — the API behind the low-code workflow editor.

The graphs live in config/workflows/*.yaml and are loaded by
src/infrastructure/workflow/loader.py. This module exposes them for reading,
validating and editing.

Two design points worth stating:

* `validate` runs the REAL executor (`WorkflowSpec.layers()` constructs a
  `DAGExecutor`). A second, UI-only validator would be free to disagree with the
  engine, which is the worst possible outcome for a "check before you save"
  button — it would bless a graph the engine then rejects.

* `PUT` writes atomically via a temp file + replace, and snapshots the previous
  version into `.history/`. Workflow files are product state edited through a
  browser, so a half-written file or an unrecoverable mistake are both real.

驗證使用真正的 executor（而非另寫一份 UI 專用驗證器），否則「儲存前檢查」
可能放過引擎實際會拒絕的圖。PUT 以暫存檔原子寫入並將舊版快照到 .history/。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.v1.dependencies import get_current_user_id
from src.infrastructure.workflow.loader import (
    WorkflowError,
    list_workflows,
    load_workflow,
    workflows_dir,
)
from src.infrastructure.workflow.nodes import list_nodes
from src.utils.logger import setup_logger

logger = setup_logger("API_Workflows")
router = APIRouter()

# A workflow id becomes a filename, so it must not be able to escape the
# directory. Rejecting anything outside this alphabet is simpler to reason about
# than sanitising, and these ids are ours to choose.
# workflow id 會變成檔名，必須無法跳出目錄；直接限制字元集比事後清洗更容易論證。
_ID_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _safe_id(wf_id: str) -> str:
    clean_id = os.path.basename(wf_id.strip())
    if not clean_id or clean_id != wf_id or not set(clean_id) <= _ID_OK:
        raise HTTPException(
            status_code=400,
            detail="workflow id may contain only letters, digits, hyphen and underscore",
        )
    return clean_id


class WorkflowSummary(BaseModel):
    id: str
    version: int
    description: str = ""
    node_count: int
    layer_count: int
    valid: bool
    error: Optional[str] = None


class WorkflowDetail(BaseModel):
    id: str
    version: int
    description: str = ""
    yaml: str
    layers: List[List[str]] = Field(default_factory=list)
    valid: bool
    error: Optional[str] = None


class WorkflowSaveRequest(BaseModel):
    yaml: str


class WorkflowValidateResponse(BaseModel):
    valid: bool
    layers: List[List[str]] = Field(default_factory=list)
    node_count: int = 0
    error: Optional[str] = None


def _describe(wf_id: str) -> WorkflowSummary:
    try:
        spec = load_workflow(wf_id, force=True)
        return WorkflowSummary(
            id=spec.id, version=spec.version, description=spec.description,
            node_count=len(spec.nodes), layer_count=len(spec.layers()), valid=True,
        )
    except Exception as exc:
        # A broken file must still be listed — otherwise it vanishes from the UI
        # and becomes impossible to fix through it.
        # 壞掉的檔案仍須列出，否則會從 UI 消失而無法修復。
        return WorkflowSummary(
            id=wf_id, version=0, node_count=0, layer_count=0,
            valid=False, error=str(exc),
        )


@router.get("", response_model=List[WorkflowSummary])
async def list_all(user_id: str = Depends(get_current_user_id)):
    return [_describe(wf_id) for wf_id in list_workflows()]


@router.get("/nodes", response_model=Dict[str, str])
async def available_nodes(user_id: str = Depends(get_current_user_id)):
    """
    The code nodes a workflow may reference, as name -> description.

    `type: code` refs resolve through this registry only; an arbitrary dotted
    import path is deliberately not accepted, because these files are editable
    from a browser.
    code 節點只能取自此註冊表；刻意不接受任意 import 路徑，因為檔案可從瀏覽器編輯。
    """
    return list_nodes()


@router.get("/{wf_id}", response_model=WorkflowDetail)
async def get_one(wf_id: str, user_id: str = Depends(get_current_user_id)):
    safe_name = _safe_id(wf_id)
    base_dir = workflows_dir().resolve()
    path = (base_dir / f"{safe_name}.yaml").resolve()
    if not path.is_relative_to(base_dir) or not path.exists():
        raise HTTPException(status_code=404, detail=f"workflow '{wf_id}' not found")

    raw = path.read_text()
    try:
        spec = load_workflow(safe_name, force=True)
        return WorkflowDetail(
            id=spec.id, version=spec.version, description=spec.description,
            yaml=raw, layers=spec.layers(), valid=True,
        )
    except Exception as exc:
        return WorkflowDetail(
            id=safe_name, version=0, yaml=raw, layers=[], valid=False, error=str(exc),
        )


@router.post("/validate", response_model=WorkflowValidateResponse)
async def validate(payload: WorkflowSaveRequest, user_id: str = Depends(get_current_user_id)):
    """Parse and topologically sort a candidate document without saving it."""
    return _validate_yaml(payload.yaml)


def _validate_yaml(text: str) -> WorkflowValidateResponse:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return WorkflowValidateResponse(valid=False, error=f"invalid YAML: {exc}")

    if not isinstance(raw, dict):
        return WorkflowValidateResponse(valid=False, error="document must be a mapping")

    # Parse and build through the same code path the loader uses, then let the
    # real DAGExecutor derive the layers — that is what catches cycles and
    # duplicate output keys.
    # 走與 loader 相同的解析路徑，再由真正的 DAGExecutor 推導層級（可抓出環與重複輸出鍵）。
    from src.infrastructure.workflow.executor import DAGExecutor
    from src.infrastructure.workflow.loader import _parse

    try:
        spec = _parse(raw, raw.get("id", "candidate"))
        nodes = spec.build()
        executor = DAGExecutor(nodes)
        return WorkflowValidateResponse(
            valid=True,
            layers=[[n.name for n in layer] for layer in executor.layers],
            node_count=len(nodes),
        )
    except (WorkflowError, ValueError) as exc:
        return WorkflowValidateResponse(valid=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — surface anything else as a message
        logger.exception("workflow validation blew up")
        return WorkflowValidateResponse(valid=False, error=f"{type(exc).__name__}: {exc}")


@router.put("/{wf_id}", response_model=WorkflowDetail)
async def save(wf_id: str, payload: WorkflowSaveRequest,
               user_id: str = Depends(get_current_user_id)):
    """
    Replace a workflow document.

    Refuses to write anything that does not validate. Saving a broken graph and
    discovering it at the next scheduled run — which for these workflows means a
    missed portfolio review — is the failure this prevents.
    不接受無法通過驗證的內容：存下壞掉的圖、等到下次排程才發現，
    對這些 workflow 而言就是一次漏掉的投組審查。
    """
    safe_name = _safe_id(wf_id)
    payload_clean = payload.yaml

    result = _validate_yaml(payload_clean)
    if not result.valid:
        raise HTTPException(status_code=400, detail=result.error or "invalid workflow")

    directory = workflows_dir().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = (directory / f"{safe_name}.yaml").resolve()
    if not path.is_relative_to(directory):
        raise HTTPException(status_code=400, detail="invalid workflow path")

    # Snapshot the outgoing version before overwriting.
    if path.exists():
        history = (directory / ".history").resolve()
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_file = (history / f"{safe_name}.{stamp}.yaml").resolve()
        if snapshot_file.is_relative_to(history):
            try:
                shutil.copy2(path, snapshot_file)
            except OSError as exc:
                # Losing the snapshot is not worth failing the save, but the operator
                # should know their undo is missing.
                # 快照失敗不值得中止儲存，但必須讓使用者知道少了還原點。
                logger.warning("could not snapshot %s before overwrite: %s", safe_name, exc)

    # Atomic replace: a partially written workflow file would fail to parse on
    # the next load, taking the graph down between two keystrokes.
    # 原子寫入：半寫入的檔案下次載入會解析失敗。
    try:
        fd, tmp = tempfile.mkstemp(dir=str(directory), suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            fh.write(payload_clean)
        os.replace(tmp, path)
    except OSError as exc:
        logger.error("failed to write workflow %s: %s", safe_name, exc)
        raise HTTPException(
            status_code=500,
            detail="could not write the workflow file — is config/ mounted writable?",
        ) from exc

    logger.info("workflow %s saved by %s (%d nodes)", safe_name, user_id, result.node_count)
    return await get_one(safe_name, user_id=user_id)


@router.get("/{wf_id}/history", response_model=List[str])
async def history(wf_id: str, user_id: str = Depends(get_current_user_id)):
    """Snapshot filenames for this workflow, newest first."""
    _safe_id(wf_id)
    directory = workflows_dir() / ".history"
    if not directory.exists():
        return []
    return sorted((p.name for p in directory.glob(f"{wf_id}.*.yaml")), reverse=True)
