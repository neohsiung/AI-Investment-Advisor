"""Skip a Sentinel news alert for a ticker we do not hold while the charter halt is on.
章程停機中，對「沒有持有的標的」的新聞警報不開議會。

While charter_state is frozen / human_stop, a new non-safety BUY is refused by the risk gateway. A news alert about a
ticker we do not hold can only lead to a BUY, so a council on it spends LLM money on an outcome that cannot be executed.
This module decides to skip that one case; everything else (held tickers, price / risk / cash triggers, critical
priority, anything it cannot read) keeps the existing behaviour. A skip is never silent: it logs a WARNING and writes an
alert-history row with ``council_skipped`` in its metadata. It never adds a trade, so it can only reduce spend.
停機中新的非安全買單會被風控閘門擋下；對沒持有標的的新聞警報，議會只可能得出買進，無法執行。本模組只處理這一種情況，
其餘（持有的標的、價格／風險／現金觸發、高優先級、任何讀不到的狀態）維持原行為。略過一律留痕，不新增任何交易。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.services import charter_state_service

logger = logging.getLogger(__name__)

SKIP_MARKER = "council_skipped:charter_halt"
_NEWS_TYPES = ("news", "breaking_news")
_CRITICAL_LEVELS = ("CRITICAL", "EMERGENCY")


def trigger_ticker(trigger: Dict[str, Any]) -> Optional[str]:
    """Ticker a trigger is about: its ``ticker`` field, else the second part of ids like ``news_AMZN_0.80``.
    觸發訊號所指的標的：優先用 ticker 欄位，否則取 ``news_AMZN_0.80`` 這類 id 的第二段。"""
    ticker = trigger.get("ticker")
    trigger_id = str(trigger.get("id", ""))
    if not ticker and "_" in trigger_id:
        parts = trigger_id.split("_")
        if len(parts) >= 2 and parts[1].isupper():
            ticker = parts[1]
    return ticker


def _is_plain_news(trigger: Dict[str, Any]) -> bool:
    if str(trigger.get("level", "")).upper() in _CRITICAL_LEVELS:
        return False
    priority = trigger.get("priority")
    if isinstance(priority, (int, float)) and priority <= 1:
        return False
    return (str(trigger.get("id", "")).startswith("news_") or trigger.get("type") in _NEWS_TYPES
            or trigger.get("trigger_type") == "news")


def skip_for_halt(trigger: Dict[str, Any], ticker: Optional[str], transaction_service: Any, repo: Any,
                  user_id: str, engine: Any = None) -> bool:
    """True when the council for this trigger should be skipped (and the skip has been recorded). Any doubt returns False:
    no ticker, a state or holdings read that fails, a held ticker, a non-news or critical trigger.
    該略過這個觸發的議會時回 True（並已留痕）；任何存疑都回 False。"""
    if not ticker or not _is_plain_news(trigger):
        return False
    try:
        st = charter_state_service.read_state(engine)
        if not (st.human_stop or st.mode in charter_state_service.BLOCKING_MODES):
            return False
        holdings = transaction_service.get_holdings_map(user_id)
    except Exception as e:  # noqa: BLE001 - unreadable means "do not skip": the council runs as before
        logger.warning("council halt gate: cannot read charter state or holdings (%s); not skipping", type(e).__name__)
        return False
    touched = {str(ticker).upper(), *(str(x).upper() for x in (trigger.get("affected_tickers") or []))}
    held = {str(sym).upper() for sym, pos in holdings.items() if float((pos or {}).get("quantity", 0) or 0) > 0}
    if touched & held:
        return False
    logger.warning("%s: %s (charter %s; no council on a ticker we do not hold, a new BUY is refused anyway)",
                   SKIP_MARKER, ",".join(sorted(touched)), st.mode)
    try:
        repo.log_alert(SKIP_MARKER, str(trigger.get("text", ""))[:500],
                       metadata={"council_skipped": "charter_halt", "tickers": sorted(touched),
                                 "signal_id": trigger.get("id"), "charter_mode": st.mode})
    except Exception as e:  # noqa: BLE001 - the WARNING above is already the trace
        logger.warning("council halt gate: could not write alert-history row (%s)", type(e).__name__)
    return True
