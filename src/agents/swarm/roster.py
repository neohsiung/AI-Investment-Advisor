"""
Swarm sub-agent rosters, loaded from config/agents/swarms/*.yaml.

Each swarm declared its sub-agents as Python literals in `__init__` — name,
instruction text and tier inline, plus the registration column. Retuning an
instruction or moving a sub-agent to a cheaper tier therefore required a code
change and a redeploy, for values that are prompt copy and cost policy.

Falls back to an empty roster rather than raising: a swarm with no sub-agents is
visibly degraded and logged, whereas an exception here would take down whichever
workflow layer the swarm sits in.

各 swarm 原本以 Python 字面值宣告子代理（名稱、指令、tier 內嵌），調整指令或
tier 都需改程式並重新部署。載入失敗時回傳空名單並記錄，而非拋錯——空名單是
可見的降級，拋錯則會讓該 swarm 所在的 workflow 層整層失敗。
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DIR_ENV = "SWARMS_DIR"
_DEFAULT_DIR = "config/agents/swarms"

_lock = threading.Lock()
_cache: Dict[str, tuple] = {}   # id -> (mtime, roster)


@dataclass
class SubAgentSpec:
    name: str
    instruction: str
    tier: str = "fast"
    column: Optional[str] = None


def swarms_dir() -> Path:
    explicit = os.getenv(_DIR_ENV)
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[3] / _DEFAULT_DIR


def load_roster(swarm_id: str) -> List[SubAgentSpec]:
    """
    Sub-agent specs for `swarm_id`, cached on the file's mtime so an instruction
    edit applies without restarting the workers.
    以 mtime 快取：修改指令無須重啟 worker。
    """
    path = swarms_dir() / f"{swarm_id}.yaml"
    if not path.exists():
        logger.warning("swarm roster not found: %s", path)
        return []

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []

    with _lock:
        cached = _cache.get(swarm_id)
        if cached and cached[0] == mtime:
            return cached[1]

        try:
            import yaml

            raw = yaml.safe_load(path.read_text()) or {}
            entries = raw.get("sub_agents") or []
            roster = []
            for e in entries:
                name = e.get("name")
                instruction = e.get("instruction")
                if not name or not instruction:
                    logger.error(
                        "swarm %s: sub-agent needs both `name` and `instruction`, got %r",
                        swarm_id, e,
                    )
                    continue
                roster.append(SubAgentSpec(
                    name=name,
                    instruction=instruction,
                    tier=e.get("tier", "fast"),
                    column=e.get("column"),
                ))
        except Exception as exc:
            logger.error("could not load swarm roster %s: %s", swarm_id, exc)
            return []

        if not roster:
            logger.error(
                "swarm %s loaded an EMPTY roster — it will produce no sub-agent "
                "output. Check %s.", swarm_id, path,
            )

        _cache[swarm_id] = (mtime, roster)
        return roster
