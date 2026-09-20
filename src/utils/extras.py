"""
Optional-dependency guard.

Splitting the dependency list turns a previously-eager ImportError into a
runtime feature outage that can hide in a Celery log. `require_extra()` makes
the failure explicit and actionable at the point of use: it names the extra to
install rather than the module that happened to be missing.

Rule for callers: never let a bare ImportError escape from an optional import.
Either handle it and degrade visibly, or re-raise it through this helper.

把相依拆成 extras 後，原本立即的 ImportError 會變成只在 log 裡出現的功能失效。
此輔助函式讓錯誤明確指出「要裝哪個 extra」，而不是「缺了哪個模組」。
"""
from __future__ import annotations

import importlib
from typing import Any


class MissingExtraError(ImportError):
    """An optional dependency group is not installed."""


# module name -> extra that provides it
_EXTRA_FOR_MODULE = {
    "timesfm": "forecast",
    "transformers": "forecast",
    "cvxpy": "optimize",
    "sklearn": "optimize",
    "mem0": "memory",
    "qdrant_client": "memory",
    "llama_index": "memory",
    "nltk": "memory",
    "playwright": "scrape",
    "newspaper": "scrape",
    "pytrends": "scrape",
    "opentelemetry": "obs",
    "dspy": "dspy",
    "linebot": "channels-line",
}


def extra_for(module: str) -> str:
    """Which extra provides `module` (falls back to the module's own name)."""
    return _EXTRA_FOR_MODULE.get(module.split(".")[0], module)


def require_extra(module: str, feature: str = "") -> Any:
    """
    Import `module`, or raise MissingExtraError naming the extra to install.

    >>> timesfm = require_extra("timesfm", "zero-shot price forecasting")
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        extra = extra_for(module)
        what = f" needed for {feature}" if feature else ""
        raise MissingExtraError(
            f"'{module}'{what} is not installed. It ships in the optional "
            f"'{extra}' dependency group — install it with:\n"
            f"    pip install '.[{extra}]'\n"
            f"(original error: {exc})"
        ) from exc


def has_extra(module: str) -> bool:
    """True when `module` can be imported. For soft feature detection."""
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False
