"""
Tool manifest loader — `config/tools.yaml`.

Collapses four tool surfaces into one (see the manifest's own header for what
each of them was). Everything an agent can call is declared in that file and
registered into the agent's `McpServer`; the HTTP endpoints became a read-only
view of the same set rather than a second, divergent registry.

Resolution is deliberately narrow. `func:` and `bundle:` are dotted paths, which
means the manifest can name code to import — so only `src.`-rooted modules are
allowed, a `bundle:` must expose `register(mcp_server)`, and a `func:` must be
callable. A manifest that names something else is skipped with an error, never
silently treated as a working tool.

本模組載入 config/tools.yaml，把四個工具介面收斂成一個。dotted path 只允許 src. 底下的
模組，bundle 必須有 register(mcp_server)，func 必須可呼叫；不合格者記錄錯誤並略過，
絕不當成可用工具靜默通過。
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from src.utils.logger import setup_logger

logger = setup_logger("ToolManifest")

MANIFEST_ENV = "TOOLS_MANIFEST"
DEFAULT_MANIFEST = "config/tools.yaml"

# Only this package may be named by a manifest. Without it, `func:` would be an
# arbitrary-import primitive reachable by editing a mounted config file.
# 僅允許此套件；否則 func: 等於可任意匯入的原語。
_ALLOWED_ROOTS = ("src.",)

_cache: Dict[str, Any] = {"mtime": None, "data": None}


class ToolManifestError(Exception):
    """Raised for a manifest entry that cannot be honoured."""


def manifest_path() -> Path:
    explicit = os.getenv(MANIFEST_ENV)
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[2] / DEFAULT_MANIFEST


def load_manifest(force: bool = False) -> Dict[str, Any]:
    """
    Parse the manifest, cached on mtime so an edit is picked up without a restart.
    以 mtime 快取，編輯後無須重啟即生效。
    """
    path = manifest_path()
    if not path.exists():
        logger.error(f"Tool manifest missing at {path}; no tools will be registered")
        return {"version": 0, "builtin": [], "external_mcp": {}}

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _cache["data"] or {"version": 0, "builtin": [], "external_mcp": {}}

    if not force and _cache["mtime"] == mtime and _cache["data"] is not None:
        return _cache["data"]

    raw = yaml.safe_load(path.read_text()) or {}
    data = {
        "version": raw.get("version", 0),
        "builtin": list(raw.get("builtin") or []),
        "external_mcp": dict(raw.get("external_mcp") or {}),
    }
    _cache["mtime"] = mtime
    _cache["data"] = data
    logger.info(f"Tool manifest loaded: {len(data['builtin'])} builtin entries")
    return data


def reset_cache() -> None:
    _cache["mtime"] = None
    _cache["data"] = None


def _check_root(dotted: str) -> None:
    if not any(dotted.startswith(root) for root in _ALLOWED_ROOTS):
        raise ToolManifestError(
            f"'{dotted}' is outside the allowed roots {_ALLOWED_ROOTS}; "
            "the manifest may only name project code"
        )


def _import_attr(dotted: str) -> Any:
    _check_root(dotted)
    if ":" in dotted:
        module_name, _, attr = dotted.partition(":")
    else:
        module_name, _, attr = dotted.rpartition(".")
    if not module_name or not attr:
        raise ToolManifestError(f"'{dotted}' is not a dotted path to an attribute")
    if attr.startswith("_"):
        raise ToolManifestError(f"'{dotted}' names a private attribute")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ToolManifestError(f"'{dotted}' does not exist") from exc


def resolve_callable(dotted: str) -> Callable:
    """Resolve a `func:` entry. Must be callable and must not be a class."""
    obj = _import_attr(dotted)
    if isinstance(obj, type):
        raise ToolManifestError(f"'{dotted}' is a class; use `bundle:` for those")
    if not callable(obj):
        raise ToolManifestError(f"'{dotted}' is not callable")
    return obj


def resolve_bundle(dotted: str) -> type:
    """
    Resolve a `bundle:` entry — a class whose `register(mcp_server)` adds several
    tools at once. The `register` requirement is what keeps `bundle:` from being
    a way to instantiate arbitrary classes.
    register(mcp_server) 的要求讓 bundle 無法用來實例化任意類別。
    """
    obj = _import_attr(dotted)
    if not isinstance(obj, type):
        raise ToolManifestError(f"'{dotted}' is not a class")
    if not callable(getattr(obj, "register", None)):
        raise ToolManifestError(f"'{dotted}' has no register(mcp_server) method")
    return obj


def _applies_to(entry: Dict[str, Any], agent_name: str) -> bool:
    agents = entry.get("agents")
    if not agents or "*" in agents:
        return True
    return agent_name in agents


def builtin_entries(agent_name: str = "") -> List[Dict[str, Any]]:
    """Enabled builtin entries that apply to this agent, in manifest order."""
    entries = []
    for entry in load_manifest()["builtin"]:
        if not entry.get("name"):
            logger.error(f"Tool entry without a name, skipped: {entry!r}")
            continue
        if entry.get("enabled") is False:
            continue
        if agent_name and not _applies_to(entry, agent_name):
            continue
        kinds = [k for k in ("method", "func", "bundle") if entry.get(k)]
        if len(kinds) != 1:
            logger.error(
                f"Tool '{entry['name']}' must declare exactly one of "
                f"method/func/bundle, found {kinds or 'none'}; skipped"
            )
            continue
        entries.append(entry)
    return entries


def external_mcp_config() -> Dict[str, Any]:
    cfg = load_manifest()["external_mcp"]
    return {
        "enabled_setting": cfg.get("enabled_setting", "external_mcp_enabled"),
        "namespace_prefix": cfg.get("namespace_prefix", "ext_"),
        "servers": [s for s in (cfg.get("servers") or []) if s.get("url")],
    }


def enabled_external_servers() -> List[Dict[str, Any]]:
    """
    Servers marked enabled in the manifest. The settings-level gate is checked by
    the caller, which has the settings service; both must agree.
    設定層級的開關由呼叫端檢查（它才有 settings service），兩者都須成立。
    """
    return [s for s in external_mcp_config()["servers"] if s.get("enabled") is True]


def register_builtin_tools(agent) -> List[str]:
    """
    Register this agent's manifest tools into `agent.toold`.

    Returns the names registered. A failing entry is logged at error and skipped:
    one bad tool must not stop an agent from starting, but it must not look like
    it worked either.
    回傳已註冊的名稱。單一條目失敗會以 error 記錄並略過：壞掉的工具不該讓 agent 無法啟動，
    但也不能看起來像成功。
    """
    from src.tools.mcp_server import McpTool

    registered: List[str] = []
    agent_name = getattr(agent, "name", "") or ""

    for entry in builtin_entries(agent_name):
        name = entry["name"]
        try:
            if entry.get("bundle"):
                bundle_cls = resolve_bundle(entry["bundle"])
                bundle = bundle_cls(user_id=getattr(agent, "user_id", None) or "default")
                before = set(agent.toold.tools)
                bundle.register(agent.toold)
                registered += sorted(set(agent.toold.tools) - before)
                continue

            if entry.get("method"):
                method_name = entry["method"]
                if method_name.startswith("_"):
                    raise ToolManifestError(f"'{method_name}' is private")
                func = getattr(agent, method_name, None)
                if not callable(func):
                    raise ToolManifestError(
                        f"agent has no callable method '{method_name}'"
                    )
            else:
                func = resolve_callable(entry["func"])

            agent.toold.register_tool(McpTool(
                name=name,
                description=entry.get("description", "") or "",
                func=func,
                category=entry.get("category", "") or "",
            ))
            registered.append(name)
        except Exception as exc:
            logger.error(f"Tool '{name}' not registered for {agent_name or 'agent'}: {exc}")

    return registered
