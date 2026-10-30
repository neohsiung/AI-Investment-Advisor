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
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.config.owner import resolve_user_id
from src.data.database import get_db_engine
from src.repositories.settings_repository import AlchemySettingsRepository

logger = logging.getLogger(__name__)

# What an unreadable spend/setting looks like: DB, I/O, or a malformed value. Anything else is a bug and propagates.
_READ_ERRORS = (SQLAlchemyError, OSError, RuntimeError, ValueError, TypeError, KeyError)

CAP_SETTING_KEY = "llm_daily_cap_usd"
CAP_CACHE_TTL_SECONDS = 60.0  # setting changes take effect within this long / 設定變更最久這麼久生效
SPEND_CACHE_TTL_SECONDS = 30.0  # billed spend is refreshed ~15 min upstream; no need to query per call
_now = time.monotonic  # patched in tests
_cap_cache: dict = {}  # user_id -> (expires_at, DailySpendCap | None)


def clear_default_cap_cache() -> None:
    _cap_cache.clear()


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


def _cached_spend(read: Callable[[], float]) -> Callable[[], float]:
    state: dict = {"at": None, "value": 0.0}

    def _spent() -> float:
        now = _now()
        if state["at"] is None or now - state["at"] >= SPEND_CACHE_TTL_SECONDS:
            state["value"] = read()  # a failed read raises and is NOT cached
            state["at"] = now
        return state["value"]

    return _spent


def default_cap(user_id: Optional[str] = None, engine: Any = None) -> Optional[DailySpendCap]:
    """The cap every pipeline gets when its builder passes none: the `llm_daily_cap_usd` setting. / 預設上限。
    None when unset or 0 (disabled). An unreadable setting returns None with a warning (not cached), never a guess.
    Cached per user for CAP_CACHE_TTL_SECONDS so the disabled path costs ~no DB read per LLM call.
    未設或 0 回 None（停用）；讀不到設定時警告、不快取、視為停用。每位使用者快取 60 秒，避免每次呼叫都讀資料庫。"""
    now = _now()
    hit = _cap_cache.get(user_id)
    if hit is not None and hit[0] > now:
        return hit[1]
    try:
        raw = AlchemySettingsRepository().get(resolve_user_id(user_id), CAP_SETTING_KEY, 0.0)
        cap_usd = float(raw or 0.0)
    except _READ_ERRORS as exc:
        logger.warning("llm_daily_cap_unreadable: setting %s unreadable (%s); cap disabled", CAP_SETTING_KEY, exc)
        return None
    cap = None
    if cap_usd > 0:
        cap = DailySpendCap(
            cap_usd=cap_usd,
            spent_today_usd=_cached_spend(lambda: _read_spent_today(engine or get_db_engine())),
        )
    _cap_cache[user_id] = (now + CAP_CACHE_TTL_SECONDS, cap)
    return cap
