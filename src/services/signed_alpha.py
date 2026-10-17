"""
Direction-signed alpha (WP3a).

`alpha = realized - benchmark` is the return of a LONG position relative to
the benchmark. For a SELL the call is right when the price falls, so the
success/failure score of a SELL must be the negation. Without this a
profitable SELL is scored as a loss and distilled into a "failure rule".

方向校正 alpha：alpha = 實現報酬 - 基準，是「做多」視角。SELL 的對錯要反號，
否則賺錢的賣出會被當成失敗並被蒸餾成失敗規則。

Pure functions; no I/O. Unknown directions raise: a plausible default here
would silently invert learning signal (see AGENTS.md constraint #0).
純函式、無 I/O；未知方向一律 raise，不給預設值。
"""
from __future__ import annotations

from typing import Optional

_SIGN = {"BUY": 1.0, "SELL": -1.0}
_SIGNAL_TO_DIRECTION = {
    "BUY": "BUY",
    "STRONG_BUY": "BUY",
    "SELL": "SELL",
    "STRONG_SELL": "SELL",
}


def signed_alpha(alpha: float, direction: Optional[str]) -> float:
    """Return `alpha` oriented to the trade direction (BUY=+1, SELL=-1)."""
    key = str(direction).strip().upper() if direction is not None else ""
    if key not in _SIGN:
        raise ValueError(f"signed_alpha: unknown direction {direction!r} (expected BUY or SELL)")
    return alpha * _SIGN[key]


def direction_of_signal(signal: Optional[str]) -> str:
    """Map the five-value rating scale (STRONG_BUY|BUY|SELL|STRONG_SELL) to BUY/SELL.

    HOLD and anything else raise ValueError; callers decide explicitly what a
    non-directional signal means.
    """
    key = str(signal).strip().upper().replace(" ", "_") if signal is not None else ""
    if key not in _SIGNAL_TO_DIRECTION:
        raise ValueError(f"direction_of_signal: signal {signal!r} has no BUY/SELL direction")
    return _SIGNAL_TO_DIRECTION[key]
