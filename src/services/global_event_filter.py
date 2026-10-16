"""
Global-event quality filter for Sentinel Dimension 6.
Sentinel 第 6 維度（全球重大事件）的來源品質過濾器。

Why (2026-10 audit): ~1,270 of 1,277 council sessions were triggered by Sentinel "global event"
alerts, and most were evergreen/junk pages returned by a generic web search — the Wikipedia
"Stock market crash" article (15x in 14 days), quizzes, news-site homepages, clickbait. Three
defects fed this: (1) the dedupe id used Python's per-process-randomised hash(), so the same
page looked "new" in every worker; (2) the scan read `content`/`url` while the search service
returns `snippet`/`link`; (3) nothing checked source quality or corroboration.
This module is deterministic and 0-LLM: stable ids, domain/title/homepage rules, and a
corroboration requirement (several independent domains must flag the same scan).
原因：約 1,270/1,277 場議事由此類警報觸發，多為維基百科、測驗、首頁、標題黨等常青頁面。
缺陷：(1) 去重 id 用每行程隨機的 hash()；(2) 讀錯欄位名；(3) 無來源品質與佐證檢查。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

# Evergreen reference / explainer / quiz domains: never a breaking event.
# 常青參考、教學、測驗網域：不可能是即時事件。
DEFAULT_BLOCKED_DOMAINS: Tuple[str, ...] = (
    "wikipedia.org", "wikimedia.org", "britannica.com", "investopedia.com",
    "ideoradar.org", "ideoradar.com", "quizlet.com", "quora.com", "reddit.com",
    "youtube.com", "facebook.com", "pinterest.com", "medium.com",
)

# Titles that describe a section/home page, a quiz, or a history piece rather than an event.
# 描述首頁/分區/測驗/歷史回顧而非事件的標題樣式。
_TITLE_PATTERNS = [
    r"\bquiz\b", r"\bwikipedia\b", r"breaking news updates", r"latest (news|headlines)",
    r"today'?s? (stock )?market news", r"^[\w .&'-]+ \| (economy|business|finance|news|markets?)\b",
    r"\ba (brief )?history of\b", r"\bwhat is a (stock )?market crash\b", r"\bfaq\b",
]


@dataclass
class FilterDecision:
    accepted: bool
    reason: str
    event_id: str
    domain: str = ""


@dataclass
class FilterReport:
    accepted: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Tuple[str, str]] = field(default_factory=list)   # (title, reason)
    suppressed_no_corroboration: bool = False


def normalize_url(url: str) -> str:
    """Lower-case host + path without query/fragment/trailing slash. / 正規化網址。"""
    try:
        p = urlparse((url or "").strip())
        host = (p.netloc or "").lower().removeprefix("www.")
        return f"{host}{p.path.rstrip('/')}"
    except Exception:
        return (url or "").strip().lower()


def domain_of(url: str) -> str:
    try:
        return (urlparse((url or "").strip()).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def stable_event_id(url: str, title: str) -> str:
    """Process-independent id (sha256). Python's built-in hash() is salted per process.
    跨行程穩定的 id（sha256）；內建 hash() 每個行程不同。"""
    basis = normalize_url(url) if url else (title or "").strip().lower()
    return "global_macro_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _is_homepage(url: str) -> bool:
    try:
        p = urlparse((url or "").strip())
        return bool(p.netloc) and p.path.strip("/") == ""
    except Exception:
        return False


class GlobalEventFilter:
    def __init__(self, blocked_domains: Optional[Iterable[str]] = None, min_sources: int = 2):
        self.blocked_domains = tuple(d.lower() for d in (blocked_domains or DEFAULT_BLOCKED_DOMAINS))
        self.min_sources = max(1, int(min_sources))
        self._title_res = [re.compile(p, re.I) for p in _TITLE_PATTERNS]

    def _domain_blocked(self, domain: str) -> bool:
        return any(domain == d or domain.endswith("." + d) for d in self.blocked_domains)

    def check(self, title: str, url: str) -> FilterDecision:
        """Static (single-item) rules. / 單筆靜態規則。"""
        eid = stable_event_id(url, title)
        dom = domain_of(url)
        if dom and self._domain_blocked(dom):
            return FilterDecision(False, f"blocked_domain:{dom}", eid, dom)
        if url and _is_homepage(url):
            return FilterDecision(False, "homepage", eid, dom)
        for rx in self._title_res:
            if rx.search(title or ""):
                return FilterDecision(False, f"title_pattern:{rx.pattern}", eid, dom)
        return FilterDecision(True, "ok", eid, dom)

    def filter_scan(self, scored_items: List[Dict[str, Any]]) -> FilterReport:
        """scored_items: dicts with title, url, weight (already >= risk threshold).
        Applies static rules, then requires >= min_sources distinct domains in the same scan.
        對已達風險門檻的項目套用靜態規則，並要求同一次掃描中至少 min_sources 個不同網域佐證。"""
        report = FilterReport()
        passed: List[Dict[str, Any]] = []
        for it in scored_items:
            d = self.check(it.get("title", ""), it.get("url", ""))
            if d.accepted:
                passed.append({**it, "event_id": d.event_id, "domain": d.domain})
            else:
                report.rejected.append((it.get("title", ""), d.reason))
        domains = {p["domain"] or p["event_id"] for p in passed}
        if passed and len(domains) < self.min_sources:
            report.suppressed_no_corroboration = True
            for p in passed:
                report.rejected.append((p.get("title", ""), f"no_corroboration:{len(domains)}<{self.min_sources}"))
            return report
        report.accepted = passed
        return report
