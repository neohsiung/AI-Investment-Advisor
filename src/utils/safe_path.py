"""
Containment check for paths built from caller-supplied names.
以呼叫端提供的名稱組路徑時的目錄限制檢查。

Callers must still validate the *name* (allowlist regex); this is the second
fence: after normalising symlinks and `..`, the result has to stay under `base`.
"""
from __future__ import annotations

import os


def resolve_within(base: str | os.PathLike, *parts: str) -> str:
    """Join `parts` under `base` and return the real path, or raise ValueError.

    Uses realpath + a separator-terminated prefix test (not a bare startswith,
    which would accept `/data/wf-evil` for base `/data/wf`).
    """
    base_real = os.path.realpath(os.fspath(base))
    full = os.path.realpath(os.path.join(base_real, *parts))
    if full != base_real and not full.startswith(base_real + os.sep):
        raise ValueError("path escapes base directory")
    return full
