"""
Daily LLM spend cap (DD-2026-1030 L2).
每日 LLM 花費上限（DD-2026-1030 L2）。

A cost control, not a safety control: when the day's billed LLM spend reaches the cap, further
non-essential calls stop and say so (DailyBudgetExhaustedError). They never return a made-up answer.
Essential calls (exit / safety paths) bypass it. A cap of 0/None disables the check entirely.
Spend is read from `llm_real_cost_daily` (LiteLLM-billed, refreshed by the collector every 15 minutes), so the
line is approximate, not a hard real-time limit.

成本控制而非安全控制：當日計費花費達上限後，非必要呼叫停止並明確丟出錯誤，不回傳編造的答案。
必要呼叫（出場／安全路徑）不受限。上限為 0／None 時完全停用。花費來自 `llm_real_cost_daily`（約 15 分鐘更新），
因此是粗略的日界線，不是即時硬上限。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.data.database import get_db_engine

logger = logging.getLogger(__name__)

# What an unreadable spend/setting looks like: DB, I/O, or a malformed value. Anything else is a bug and propagates.
_READ_ERRORS = (SQLAlchemyError, OSError, RuntimeError, ValueError, TypeError, KeyError)

CAP_SETTING_KEY = "llm_daily_cap_usd"


class DailyBudgetExhaustedError(Exception):
    """Raised instead of calling the LLM once the day's spend has reached the cap. / 當日花費達上限時丟出。"""

    def __init__(self, cap_usd: float, spent_usd: float):
        self.cap_usd = cap_usd
        self.spent_usd = spent_usd
        super().__init__(f"daily LLM budget exhausted: spent ${spent_usd:.4f} of ${cap_usd:.4f} cap")


@dataclass(frozen=True)
class DailySpendCap:
    """cap_usd 0/None = disabled. spent_today_usd is read lazily so a disabled cap costs no query."""

    cap_usd: Optional[float]
    spent_today_usd: Callable[[], float]

    @property
    def enabled(self) -> bool:
        return bool(self.cap_usd) and self.cap_usd > 0

    def check(self, label: str = "") -> None:
        """Raise DailyBudgetExhaustedError when spend >= cap. Unreadable spend lets the call through, loudly."""
        if not self.enabled:
            return
        try:
            spent = float(self.spent_today_usd())
        except _READ_ERRORS as exc:
            logger.warning("llm_daily_cap_unreadable: %s; call allowed without a cap check (%s)", exc, label)
            return
        if spent >= self.cap_usd:
            logger.warning("llm_daily_cap_exhausted: spent=%.4f cap=%.4f (%s)", spent, self.cap_usd, label)
            raise DailyBudgetExhaustedError(self.cap_usd, spent)


def _read_spent_today(engine: Any, today: Optional[date] = None) -> float:
    today = today or datetime.now(timezone.utc).date()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COALESCE(SUM(spend_usd), 0) FROM llm_real_cost_daily WHERE day = :d"), {"d": today}
        ).fetchone()
    return float(row[0] or 0.0)


def cap_from_settings(
    settings_service: Any, user_id: Optional[str] = None, engine: Any = None
) -> Optional[DailySpendCap]:
    """Build the cap from the `llm_daily_cap_usd` setting; None when unset/0/unreadable-as-disabled.
    An unreadable setting returns None with a warning (cap off), never a guessed number.
    以設定 `llm_daily_cap_usd` 建立上限；未設或 0 回 None。讀不到設定時警告並視為停用，不猜數字。"""
    try:
        raw = settings_service.get_setting(CAP_SETTING_KEY, user_id=user_id)
        cap = float(raw or 0.0)
    except _READ_ERRORS as exc:
        logger.warning("llm_daily_cap_unreadable: setting %s unreadable (%s); cap disabled", CAP_SETTING_KEY, exc)
        return None
    if cap <= 0:
        return None

    def _spent() -> float:
        eng = engine
        if eng is None:
            eng = get_db_engine()
        return _read_spent_today(eng)

    return DailySpendCap(cap_usd=cap, spent_today_usd=_spent)
