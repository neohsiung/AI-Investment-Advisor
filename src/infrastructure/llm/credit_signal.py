"""LLM credit-limit signal: remember that the provider refused a call because the key's credit or spend limit is used up.
LLM 額度用盡訊號：記下「供應商因金鑰額度用完而拒絕呼叫」這件事，讓自我維運能當天告警。

A weekly limit set upstream (for example on an OpenRouter key) makes LLM calls fail from then on. Until now that looked
like an ordinary failure in the logs. The pipeline calls ``record()`` when it classifies an error as CREDIT_LIMIT; the
self-ops named check ``llm_credit_available`` reads ``probe()``. Redis keeps the last time seen with a short TTL, so the
alert clears itself when calls succeed again. Recording never raises into the LLM path.
上游（例如 OpenRouter 金鑰）設週額度後，LLM 呼叫之後都會失敗，日誌裡看起來只是一般失敗。管線把錯誤分類為
CREDIT_LIMIT 時呼叫 ``record()``；自我維運讀 ``probe()``。Redis 只留最近一次時間並設短 TTL，恢復後告警自動消失。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from src.infrastructure.cache.redis_client import get_redis_sync

logger = logging.getLogger(__name__)

KEY = "llm:credit_limit:last_seen"
TTL_SECONDS = 2 * 3600
ALERT_WINDOW_MINUTES = 60


def record(now: Optional[datetime] = None) -> None:
    """Remember a credit-limit refusal. A Redis failure is logged at WARNING and never reaches the LLM caller.
    記下一次額度用盡的拒絕；Redis 失敗只記 WARNING，不影響 LLM 呼叫端。"""
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    try:
        get_redis_sync().set(KEY, stamp, ex=TTL_SECONDS)
    except Exception as e:  # noqa: BLE001 - recording only
        logger.warning("llm credit signal: could not record (%s)", type(e).__name__)


def probe(now: Optional[datetime] = None) -> Tuple[bool, str, str]:
    """(ok, detail, severity). Not ok when a credit-limit refusal was seen within ALERT_WINDOW_MINUTES (critical). An
    unreadable Redis is reported as unknown (warning), never as fine. / 近 60 分鐘內有額度用盡的拒絕為 critical；
    Redis 讀不到回 warning（未知），不當成正常。"""
    now = now or datetime.now(timezone.utc)
    try:
        raw = get_redis_sync().get(KEY)
    except Exception as e:  # noqa: BLE001 - reported as a breach, not swallowed
        logger.warning("llm credit signal: Redis unreadable (%s)", type(e).__name__)
        return False, f"credit signal unreadable ({type(e).__name__})", "warning"
    if not raw:
        return True, "no credit-limit refusal recorded", "warning"
    try:
        seen = datetime.fromisoformat(raw if isinstance(raw, str) else raw.decode())
    except (ValueError, AttributeError):
        return False, "credit signal value unreadable", "warning"
    age_min = (now - seen).total_seconds() / 60.0
    if age_min <= ALERT_WINDOW_MINUTES:
        return False, (f"LLM provider refused a call {age_min:.0f} min ago because the key's credit or spend limit is used "
                       "up; new decisions that need an LLM are paused until the limit resets"), "critical"
    return True, f"last credit-limit refusal {age_min:.0f} min ago", "warning"
