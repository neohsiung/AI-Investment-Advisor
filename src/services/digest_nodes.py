import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

@dataclass
class DigestNode:
    name: str
    selector: Callable[[Dict[str, Any]], bool]
    composer: Callable[[List[Dict[str, Any]]], Tuple[str, str]]
    category: str
    channels: Optional[List[str]] = None
    suppress: Optional[Callable[[List[Dict[str, Any]]], bool]] = None


def parse_datetime(val) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        val_str = str(val)
        if val_str.endswith('Z'):
            val_str = val_str[:-1] + '+00:00'
        return datetime.fromisoformat(val_str)
    except Exception as e:
        logger.warning(f'Exception in digest_nodes.py: {e}', exc_info=True)
        return None


# ── ops_health Node ───────────────────────────────────────────────────

def ops_selector(event: Dict[str, Any]) -> bool:
    event_type = event.get("event_type") or ""
    return event_type.startswith("self_ops") or event_type.startswith("ops_")


def compose_ops_health(events: List[Dict[str, Any]]) -> Tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    title = f"🛠️ 系統運作狀況摘要 (Ops Health) — {today}"
    
    lines = [
        f"🛠️ 系統運作狀況摘要 (Ops Health) — {today}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"今日系統事件共 {len(events)} 件",
    ]
    
    # 同名 breach 合併計數
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for e in events:
        content = e.get("content") or {}
        name = content.get("title") or content.get("name") or e.get("event_type") or "Unknown Event"
        groups.setdefault(name, []).append(e)
        
    for name, group in groups.items():
        summaries = []
        for e in group:
            content = e.get("content") or {}
            s = content.get("summary") or content.get("detail") or ""
            if s and s not in summaries:
                summaries.append(s)
        
        count = len(group)
        severity = group[0].get("content", {}).get("severity", "warning")
        sev_emoji = "🔴" if severity == "critical" else "🟡"
        
        lines.append(f"\n{sev_emoji} <b>{name}</b> (共 {count} 次):")
        for s in summaries:
            lines.append(f"  • {s}")
            
    return title, "\n".join(lines)


def suppress_ops_health(events: List[Dict[str, Any]]) -> bool:
    return not bool(events)


ops_health_node = DigestNode(
    name="ops_health",
    selector=ops_selector,
    composer=compose_ops_health,
    category="ops",
    suppress=suppress_ops_health
)


# ── investment_digest Node ────────────────────────────────────────────

def investment_selector(event: Dict[str, Any]) -> bool:
    return not ops_selector(event)


def compose_investment_digest(events: List[Dict[str, Any]]) -> Tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    title = f"📋 Daily Portfolio Digest — {today}"
    
    p0 = [e for e in events if e.get("tier") == "P0"]
    p1 = [e for e in events if e.get("tier") == "P1"]
    p2 = [e for e in events if e.get("tier") == "P2"]
    p3 = [e for e in events if e.get("tier") == "P3"]
    
    lines = [
        f"📋 每日投資摘要 (Daily Digest) — {today}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"今日處理事件共 {len(events)} 件",
        f"  • P0 關鍵/緊急: {len(p0)} 件",
        f"  • P1 重要/操作: {len(p1)} 件",
        f"  • P2 例行/報告: {len(p2)} 件",
        f"  • P3 參考/訊號: {len(p3)} 件",
    ]
    
    if p0:
        lines.append("\n🔴 關鍵與緊急事件 (Critical Events):")
        for e in p0:
            content = e.get("content", {})
            lines.append(f"  • {content.get('source', '?')}: {content.get('topic', '')[:80]}")
    if p1:
        lines.append("\n🟡 重要操作與警報 (Actionable Alerts):")
        for e in p1:
            content = e.get("content", {})
            decision = content.get("decision", content.get("summary", ""))[:150]
            lines.append(f"  • {content.get('source', '?')}: {decision}")
    if p2:
        lines.append("\n⚪ 例行報告與快訊 (Routine Reports):")
        for e in p2:
            content = e.get("content", {})
            t = content.get("title") or content.get("topic") or e.get("event_type") or "Report"
            summary = content.get("summary") or content.get("full_text") or ""
            lines.append(f"\n📄 **{t}**")
            if summary:
                clean_s = summary.strip()
                if len(clean_s) > 1200:
                    clean_s = clean_s[:1200] + "..."
                lines.append(f"{clean_s}\n")
    if p3:
        lines.append("\n🔵 參考訊號與資訊 (Reference Signals):")
        for e in p3:
            content = e.get("content", {})
            t = content.get("title") or content.get("topic") or content.get("summary") or e.get("event_type") or "Reference"
            lines.append(f"  • {t[:80]}")
            
    return title, "\n".join(lines)


def suppress_investment_digest(events: List[Dict[str, Any]]) -> bool:
    # 有 P0/P1、或包含報告 (report)、或 ≥3 筆 P2、或有 >24h 的 P2 才寄；否則不寄。
    has_p0_p1 = any(e.get("tier") in ("P0", "P1") for e in events)
    has_report = any(
        e.get("event_type") == "report" or "report" in str(e.get("content", {})).lower()
        for e in events
    )
    p2_events = [e for e in events if e.get("tier") == "P2"]
    has_old_p2 = False
    
    now = datetime.now(timezone.utc)
    for e in p2_events:
        dt = parse_datetime(e.get("created_at"))
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).total_seconds() > 24 * 3600:
                has_old_p2 = True
                break
                
    return not (has_p0_p1 or has_report or len(p2_events) >= 3 or has_old_p2)


investment_digest_node = DigestNode(
    name="investment_digest",
    selector=investment_selector,
    composer=compose_investment_digest,
    category="daily_digest",
    suppress=suppress_investment_digest
)


# ── Registry ──────────────────────────────────────────────────────────

REGISTRY: List[DigestNode] = [
    ops_health_node,
    investment_digest_node,
]
