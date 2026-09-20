"""
Agent registry: manifest-driven agent construction.

`AgentFactory.create_agent` was a literal if/elif chain over ten hardcoded
names, `BaseAgent.__init__` carried a hardcoded `workspace_map` dict, and
`LLMAgentOverrideService.KNOWN_AGENT_NAMES` was a third hardcoded list of the
same population. Adding an agent meant editing all three, plus creating a
workspace directory — five edits for what is a declaration.

Two halves now:

* the IMPLEMENTATION is Python, published here via `@register_agent("key")`.
  Agents run LLM calls and place orders; the class has to be real code.
* the DECLARATION is a manifest in config/agents/<id>.md — display name, default
  tier, persona, workspace directory, which implementation to use, and the system
  prompt as the Markdown body.

So a new *variant* of an existing implementation (a differently-prompted CIO, a
scout at another tier) is a file. A genuinely new *behaviour* still needs a class,
which is the honest boundary: no amount of YAML writes new logic.

原本同一份代理清單硬編在三處（factory 的 if/elif、workspace_map、
KNOWN_AGENT_NAMES），新增一個代理要改三處再加建 workspace 目錄。
現在實作仍是 Python（以 @register_agent 發布），宣告改為 config/agents/<id>.md。
既有實作的新「變體」只需一個檔案；真正的新行為仍需要類別——這是誠實的界線。
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DIR_ENV = "AGENTS_DIR"
_DEFAULT_DIR = "config/agents"

# implementation key -> factory callable
_IMPLS: Dict[str, Callable[..., Any]] = {}

_lock = threading.Lock()
_manifests: Dict[str, "AgentManifest"] = {}
_manifest_mtimes: Dict[str, float] = {}


class AgentRegistryError(ValueError):
    """A manifest is malformed or names an unknown implementation."""


@dataclass
class AgentManifest:
    """One agent declaration, from config/agents/<id>.md."""
    id: str
    impl: str
    display_name: str = ""
    default_tier: str = "fast"
    persona: Optional[str] = None
    workspace: Optional[str] = None
    temperature: Optional[float] = None
    skills: List[str] = field(default_factory=list)
    enabled: bool = True
    description: str = ""
    # Markdown body — the system prompt, when the manifest supplies one.
    prompt: str = ""
    path: Optional[Path] = None

    @property
    def name(self) -> str:
        """The display name agents are addressed by (e.g. "Momentum Scout")."""
        return self.display_name or self.id


def register_agent(key: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Publish an agent implementation under `key`, referenceable as `impl:` in a
    manifest. Manifests may only name keys registered here — never a dotted
    import path, since manifests are editable from the UI.
    manifest 只能指名此處註冊的 key，不接受 dotted path（manifest 可從 UI 編輯）。
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if key in _IMPLS and _IMPLS[key] is not func:
            raise ValueError(f"agent impl '{key}' is already registered")
        _IMPLS[key] = func
        return func
    return decorator


def agents_dir() -> Path:
    explicit = os.getenv(_DIR_ENV)
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[2] / _DEFAULT_DIR


def _parse_manifest(path: Path) -> AgentManifest:
    from src.utils.frontmatter import FrontmatterError, parse_file

    try:
        doc = parse_file(path)
    except FrontmatterError as exc:
        raise AgentRegistryError(str(exc)) from exc

    meta = doc.meta
    agent_id = meta.get("id") or path.stem
    impl = meta.get("impl")
    if not impl:
        raise AgentRegistryError(f"{path}: manifest needs an `impl:` key")

    return AgentManifest(
        id=agent_id,
        impl=impl,
        display_name=meta.get("display_name", ""),
        default_tier=meta.get("default_tier", "fast"),
        persona=meta.get("persona"),
        workspace=meta.get("workspace"),
        temperature=meta.get("temperature"),
        skills=list(meta.get("skills") or []),
        enabled=bool(meta.get("enabled", True)),
        description=meta.get("description", ""),
        prompt=doc.body,
        path=path,
    )


def load_manifests(force: bool = False) -> Dict[str, AgentManifest]:
    """
    All manifests, keyed by id. Reloaded per file when its mtime changes, so a
    prompt or tier edit applies without restarting the workers.
    以 mtime 逐檔重載：修改 prompt 或 tier 無須重啟 worker。
    """
    directory = agents_dir()
    if not directory.exists():
        return {}

    with _lock:
        seen = set()
        for path in sorted(directory.glob("*.md")):
            wf_id = path.stem
            seen.add(wf_id)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if not force and _manifest_mtimes.get(wf_id) == mtime and wf_id in _manifests:
                continue
            try:
                manifest = _parse_manifest(path)
            except AgentRegistryError as exc:
                # A broken manifest must not remove a working agent from the
                # registry — it keeps the last good version and logs.
                # 壞掉的 manifest 不應讓既有可用代理消失，保留上一份並記錄。
                logger.error("agent manifest rejected: %s", exc)
                continue
            _manifests[manifest.id] = manifest
            _manifest_mtimes[wf_id] = mtime

        # Drop manifests whose files were deleted.
        for gone in set(_manifests) - seen:
            _manifests.pop(gone, None)
            _manifest_mtimes.pop(gone, None)

        return dict(_manifests)


def get_manifest(agent_id: str) -> Optional[AgentManifest]:
    """
    Look up a manifest by id, display name or a case-insensitive match.

    Callers address agents inconsistently — the workflow YAML says
    "Momentum Scout", council_service says "CIO", older code says "momentum".
    Accepting all three keeps every existing call site working.
    呼叫端的稱呼並不一致（"Momentum Scout" / "CIO" / "momentum"），全部接受。
    """
    manifests = load_manifests()
    if agent_id in manifests:
        return manifests[agent_id]

    needle = str(agent_id).strip().lower()
    for m in manifests.values():
        if m.id.lower() == needle or m.name.lower() == needle:
            return m
    return None


def known_agent_names() -> List[str]:
    """
    Display names of every enabled agent.

    Replaces LLMAgentOverrideService.KNOWN_AGENT_NAMES, which was a hardcoded
    list of eleven strings used to validate the per-agent model override UI — so
    a new agent silently could not be given an override until someone remembered
    to append to it.
    取代 KNOWN_AGENT_NAMES 硬編清單；原本新增代理後無法設定 per-agent 模型覆寫，
    直到有人記得去補那份清單。
    """
    return sorted(m.name for m in load_manifests().values() if m.enabled)


def list_impls() -> List[str]:
    """Implementation keys a manifest may reference."""
    _ensure_impls()
    return sorted(_IMPLS)


def build(agent_id: str, **kwargs) -> Any:
    """
    Construct an agent from its manifest.

    Raises AgentRegistryError for an unknown agent or an unknown `impl:`, rather
    than returning a default — silently substituting a different agent on the
    path that produces trade decisions is the wrong failure.
    未知代理或未知 impl 一律拋錯而非回傳預設值：在產生交易決策的路徑上
    靜默換成別的代理是錯誤的失敗方式。
    """
    _ensure_impls()
    manifest = get_manifest(agent_id)
    if manifest is None:
        raise AgentRegistryError(
            f"unknown agent '{agent_id}'. Declared agents: "
            f"{', '.join(sorted(load_manifests())) or '(none)'}"
        )
    if not manifest.enabled:
        raise AgentRegistryError(f"agent '{manifest.id}' is disabled in its manifest")

    impl = _IMPLS.get(manifest.impl)
    if impl is None:
        raise AgentRegistryError(
            f"agent '{manifest.id}' names unknown impl '{manifest.impl}'. "
            f"Registered impls: {', '.join(sorted(_IMPLS))}"
        )
    return impl(manifest=manifest, **kwargs)


_impls_loaded = False


def _ensure_impls() -> None:
    global _impls_loaded
    if _impls_loaded:
        return
    _impls_loaded = True
    from src.agents import impls  # noqa: F401  — registers the implementations
