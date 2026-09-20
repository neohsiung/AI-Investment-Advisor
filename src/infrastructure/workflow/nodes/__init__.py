"""
Registry of code-node functions referenceable from workflow YAML.

Why a registry rather than a dotted import path in the YAML: a workflow file is
editable from the UI, and `ref: os.system` would otherwise be a remote code
execution primitive handed to whoever can reach the settings page. A registry
means YAML can only name functions this package has deliberately published.

為何用註冊表而非 YAML 裡的 dotted path：workflow 檔可從 UI 編輯，
若允許任意匯入路徑，`ref: os.system` 就是一個遠端執行原語。
註冊表讓 YAML 只能指名本套件刻意公開的函式。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Callable[..., Any]] = {}


def register_node(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Publish a function under `name` for use as a workflow `type: code` node.

    Mirrors the decorator pattern already used by
    src/data/ingestors/factory.py's @register_ingestor.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if name in _REGISTRY and _REGISTRY[name] is not func:
            raise ValueError(
                f"node '{name}' is already registered to "
                f"{_REGISTRY[name].__module__}.{_REGISTRY[name].__name__}"
            )
        _REGISTRY[name] = func
        return func
    return decorator


def get_node(name: str) -> Callable[..., Any]:
    """Resolve a registered node function, or raise with the valid options."""
    _ensure_loaded()
    if name not in _REGISTRY:
        raise KeyError(
            f"unknown code node '{name}'. Registered nodes: "
            f"{', '.join(sorted(_REGISTRY)) or '(none)'}"
        )
    return _REGISTRY[name]


def list_nodes() -> Dict[str, str]:
    """name -> one-line description, for the UI's node palette."""
    _ensure_loaded()
    out = {}
    for name, func in sorted(_REGISTRY.items()):
        doc = (func.__doc__ or "").strip().split("\n")[0]
        out[name] = doc
    return out


_loaded = False


def _ensure_loaded() -> None:
    """Import the modules that register nodes. Idempotent."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from src.infrastructure.workflow.nodes import portfolio  # noqa: F401
