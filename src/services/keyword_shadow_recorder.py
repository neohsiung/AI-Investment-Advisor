"""Keyword shadow recorder: how often the live and the shadow keyword rules would trigger, per day.
關鍵字 shadow 紀錄器：每天記錄正式規則與 shadow 規則各會觸發幾次。

Sentinel scores news against risk keywords with the live rule and, beside it, with the shadow rule
(``keyword_match.shadow_weight``, DD-2026-1025). This module only counts the outcomes so the two rules can be
compared after a week; it never changes a trigger decision. Counts are "would trigger at the keyword stage", not
council counts: later gates (global event filter, cooldown, halt gate) apply to both rules alike.
Recording never raises into Sentinel: a Redis failure is logged at WARNING and the count is lost.

哨兵用正式規則為新聞評分，同時用 shadow 規則再算一次。這裡只計數，讓一週後能比較兩套規則，不改變任何觸發。
計數是「在關鍵字階段會觸發」，不是議會場數；之後的閘門（全球事件過濾、冷卻、停機）對兩套規則一樣。
紀錄失敗不影響哨兵：Redis 失敗只記 WARNING，該次計數遺失。

Compare after a week / 一週後比較：
    docker exec advisor_prod_worker python -c \
      "from src.services.keyword_shadow_recorder import summary; print(summary(7))"
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Sequence

from src.infrastructure.cache.redis_client import get_redis_sync

logger = logging.getLogger(__name__)

KEY_PREFIX = "sentinel:kw_shadow:"
TTL_SECONDS = 35 * 86400


def _key(day: datetime) -> str:
    return f"{KEY_PREFIX}{day.date().isoformat()}"


def outcome_fields(path: str, live: bool, shadow: bool) -> List[str]:
    """Counter fields one scored item increments. / 一次評分要加的計數欄位。"""
    fields = [f"{path}:scanned"]
    if live:
        fields.append(f"{path}:live")
    if shadow:
        fields.append(f"{path}:shadow")
    if live and not shadow:
        fields.append(f"{path}:live_only")
    if shadow and not live:
        fields.append(f"{path}:shadow_only")
    return fields


def record(path: str, live: bool, shadow: bool, label: str, now: Optional[datetime] = None) -> None:
    """Count one scored item. Never raises. / 計數一次評分，永不拋錯。"""
    key = _key(now or datetime.now(timezone.utc))
    try:
        # One round trip: Sentinel runs on an event loop and this is a sync client.
        # 一次往返：哨兵跑在 event loop 上，這是同步客戶端。
        pipe = get_redis_sync().pipeline(transaction=False)
        for f in outcome_fields(path, live, shadow):
            pipe.hincrby(key, f, 1)
        pipe.expire(key, TTL_SECONDS)
        pipe.execute()
    except Exception as e:  # noqa: BLE001 - recording only, never a decision
        logger.warning("keyword shadow: could not record %s (%s)", path, type(e).__name__)
        return
    if live != shadow:
        logger.info("keyword shadow: %s live=%s shadow=%s %s", path, live, shadow, str(label)[:100])


def compare(path: str, threshold: float, live_total: float, shadow_total_fn: Callable[[], float], label: str) -> None:
    """Record whether the live total and the shadow total reach ``threshold``. Shadow only: never raises and never
    changes the caller's decision; a scoring failure is logged at WARNING and nothing is recorded.
    記錄正式總分與 shadow 總分是否達門檻；只記錄，永不拋錯，不改呼叫端判斷；計分失敗記 WARNING、不計數。"""
    try:
        live = float(live_total) >= threshold
        shadow = float(shadow_total_fn()) >= threshold
    except Exception as e:  # noqa: BLE001 - shadow recording only, not a decision
        logger.warning("keyword shadow: skipped %s (%s)", path, type(e).__name__)
        return
    record(path, live, shadow, label)


def compare_keywords(path: str, threshold: float, texts: Sequence[str], keywords: Sequence, label: str) -> None:
    """``compare`` for a batch of texts scored keyword by keyword (best text wins under each rule). Uses the
    keywords' own ``score``/``shadow_score``, neither of which records hits.
    逐則文字用關鍵字計分（各規則取最高分）後比較；score／shadow_score 都不記命中次數。"""
    def best(rule: str) -> float:
        return max((sum(getattr(kw, rule)(t) for kw in keywords) for t in texts), default=0.0)

    try:
        live_total = best("score")
    except Exception as e:  # noqa: BLE001 - shadow recording only, not a decision
        logger.warning("keyword shadow: skipped %s (%s)", path, type(e).__name__)
        return
    compare(path, threshold, live_total, lambda: best("shadow_score"), label)


def summary(days: int = 7, now: Optional[datetime] = None) -> Dict[str, int]:
    """Totals over the last ``days`` days (today included). Raises if Redis is unreadable, so a gap is never
    reported as zero. / 最近 days 天（含今天）的合計；Redis 讀不到就拋錯，不把缺資料當成 0。"""
    now = now or datetime.now(timezone.utc)
    client = get_redis_sync()
    totals: Dict[str, int] = {}
    for i in range(days):
        raw = client.hgetall(_key(now - timedelta(days=i))) or {}
        for k, v in raw.items():
            k = k.decode() if isinstance(k, bytes) else k
            totals[k] = totals.get(k, 0) + int(v)
    return totals
