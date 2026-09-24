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
    channels=["web"],  # Strict: Ops health internal metrics stay on web, never spam email
    suppress=suppress_ops_health
)


# ── investment_digest Node ────────────────────────────────────────────

def investment_selector(event: Dict[str, Any]) -> bool:
    return not ops_selector(event)


def compose_investment_digest(events: List[Dict[str, Any]]) -> Tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    title = f"🕒 即時市場與事件快訊 (Hourly Market Events) — {today}"
    
    p0 = [e for e in events if e.get("tier") == "P0"]
    p1 = [e for e in events if e.get("tier") == "P1"]
    p2 = [e for e in events if e.get("tier") == "P2"]
    
    lines = [
        f"🕒 即時市場與事件快訊 — {today}",
    ]
    
    # 1. Critical & Actionable Trade Insights (P0/P1)
    actionable_items = []
    import re
    for e in (p0 + p1):
        content = e.get("content", {})
        topic = content.get("topic", "")
        decision = content.get("decision", content.get("summary", ""))
        source = content.get("source")
        if not source or source == "?":
            source = "Sentinel" if str(e.get("event_type", "")).startswith("sentinel") else "市場快訊"
        
        # Clean up decision text and remove any leaked LLM thinking scratchpad
        clean_dec = decision.replace("━━━━━━━━━━━━━━━━━━━━━", "").replace("💰 投資有風險，內容僅供參考，不構成建議。", "")
        clean_dec = re.sub(r'<think>.*?</think>', '', clean_dec, flags=re.DOTALL | re.IGNORECASE)
        clean_dec = re.sub(r"(?i)here['’]?s\s+a\s+thinking\s+process:.*?(?=\n\n\S|##|\d+\.|\Z)", '', clean_dec, flags=re.DOTALL)
        clean_dec = re.sub(r"(?i)^.*?analyze user request:.*?(?=\n\n\S|\d+\.|\Z)", '', clean_dec, flags=re.DOTALL)
        clean_dec = clean_dec.strip()
        if clean_dec:
            # Extract first 2-3 essential lines
            dec_lines = [l.strip() for l in clean_dec.split("\n") if l.strip() and not l.startswith("━")]
            summary_point = "；".join(dec_lines[:2])[:180]
            actionable_items.append(f"• **{source}**: {summary_point}")
            
    if actionable_items:
        lines.append("\n⚡ **重要操作與市場動態 (Key Actions)**:")
        lines.extend(actionable_items[:5])
        
    # 2. Routine Reports / Research Highlights (P2)
    report_items = []
    for e in p2:
        content = e.get("content", {})
        t = content.get("title") or content.get("topic") or e.get("event_type") or "Report"
        # If title is generic default, simplify it
        if "Investment Report" in t or "EventAnalysisWorkflow" in t:
            t = "市場事件快訊"
        summary = content.get("summary") or content.get("full_text") or ""
        if summary:
            clean_s = summary.replace("━━━━━━━━━━━━━━━━━━━━━", "")
            clean_s = re.sub(r'<think>.*?</think>', '', clean_s, flags=re.DOTALL | re.IGNORECASE)
            clean_s = re.sub(r"(?i)here['’]?s\s+a\s+thinking\s+process:.*?(?=\n\n\S|##|\d+\.|\Z)", '', clean_s, flags=re.DOTALL)
            clean_s = re.sub(r"(?i)^.*?analyze user request:.*?(?=\n\n\S|\d+\.|\Z)", '', clean_s, flags=re.DOTALL)
            clean_s = clean_s.strip()
            # Grab concise summary without dumping thousands of characters
            s_lines = [l.strip() for l in clean_s.split("\n") if l.strip() and not l.startswith("━") and not l.startswith("<")]
            brief = " ".join(s_lines[:2])[:200]
            if brief:
                report_items.append(f"• **{t}**: {brief}")
            
    if report_items:
        lines.append("\n📊 **研報與市場動態 (Market Dynamics)**:")
        lines.extend(report_items[:3])
        
    if not actionable_items and not report_items:
        lines.append("\n✅ 今日投資組合維持正常，無重大異常或需干預之操作。")
            
    return title, "\n".join(lines)


def suppress_investment_digest(events: List[Dict[str, Any]]) -> bool:
    # 有 P0/P1、或包含報告 (report)、或 ≥3 筆 P2、或有 >24h 的 P2 才發送至 Web；否則不發送。
    has_actionable = any(e.get("tier") in ("P0", "P1") for e in events)
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
                
    return not (has_actionable or has_report or len(p2_events) >= 3 or has_old_p2)


investment_digest_node = DigestNode(
    name="investment_digest",
    selector=investment_selector,
    composer=compose_investment_digest,
    category="report",
    channels=["web"],  # Strict: Hourly digest belongs EXCLUSIVELY on dashboard, NEVER in email!
    suppress=suppress_investment_digest
)


# ── Registry ──────────────────────────────────────────────────────────

REGISTRY: List[DigestNode] = [
    ops_health_node,
    investment_digest_node,
]
