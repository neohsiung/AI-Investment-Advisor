"""
Sentinel Dimension 6 junk-alert filter (2026-10 audit: Wikipedia/quiz/homepage pages triggered ~all councils).
Sentinel 全球事件垃圾警報過濾測試。
"""
import hashlib
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.global_event_filter import (
    GlobalEventFilter, normalize_url, stable_event_id, domain_of,
)

F = GlobalEventFilter()


@pytest.mark.parametrize("title,url,reason", [
    ("Stock market crash - Wikipedia", "https://en.wikipedia.org/wiki/Stock_market_crash", "blocked_domain"),
    ("Geopolitical Quiz: Your Position in Today's World Conflicts | Ideoradar", "https://ideoradar.org/quiz", "blocked_domain"),
    ("Fox News - Breaking News Updates | Latest", "https://www.foxnews.com/", "homepage"),
    ("BBC Business | Economy, Tech, AI, Work, P", "https://www.bbc.com/business/economy", "title_pattern"),
    ("A Brief History of the 1987 Stock Market Crash", "https://example.com/history-1987", "title_pattern"),
    ("Today's Stock Market News and Breaking Stories", "https://example.com/news/markets", "title_pattern"),
])
def test_known_junk_is_rejected(title, url, reason):
    d = F.check(title, url)
    assert d.accepted is False and d.reason.startswith(reason)


def test_genuine_looking_report_passes_static_rules():
    d = F.check("Fed emergency rate cut as banks fail", "https://www.reuters.com/markets/us/fed-emergency-cut-2026-10-15/")
    assert d.accepted is True


def test_stable_id_is_process_independent_and_url_normalised():
    a = stable_event_id("https://www.Example.com/a/b/?utm=1#x", "t")
    b = stable_event_id("http://example.com/a/b", "other title")
    assert a == b
    assert a.startswith("global_macro_") and len(a) == len("global_macro_") + 16
    # same value in a fresh interpreter with a different hash seed (built-in hash() would differ)
    code = ("from src.services.global_event_filter import stable_event_id;"
            "print(stable_event_id('https://example.com/a/b','t'))")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={"PYTHONHASHSEED": str(seed), "PATH": "/usr/bin:/bin"},
                           cwd=".").stdout.strip() for seed in (1, 2)}
    assert len(outs) == 1


def test_requires_corroboration_from_distinct_domains():
    one = [{"title": "Banks collapse", "url": "https://a.com/x", "weight": 1.0}]
    r = F.filter_scan(one)
    assert r.accepted == [] and r.suppressed_no_corroboration is True
    two = one + [{"title": "Banks collapse worldwide", "url": "https://b.com/y", "weight": 1.2}]
    r = F.filter_scan(two)
    assert len(r.accepted) == 2 and not r.suppressed_no_corroboration
    same_domain = one + [{"title": "More", "url": "https://a.com/z", "weight": 1.1}]
    assert F.filter_scan(same_domain).accepted == []


def test_junk_does_not_count_toward_corroboration():
    items = [
        {"title": "Banks collapse", "url": "https://a.com/x", "weight": 1.0},
        {"title": "Stock market crash - Wikipedia", "url": "https://en.wikipedia.org/wiki/Crash", "weight": 1.6},
    ]
    r = F.filter_scan(items)
    assert r.accepted == []   # only one non-junk domain


@pytest.mark.asyncio
async def test_sentinel_dimension6_uses_filter_and_dedupe():
    from src.services.sentinel_service import SentinelService

    svc = SentinelService.__new__(SentinelService)
    svc.thresholds = {"news_risk_score": 0.6}
    svc.settings_service = MagicMock()
    svc.settings_service.get_setting.side_effect = lambda k, d=None: d
    svc.keyword_service = MagicMock()
    svc.keyword_service.score_text.return_value = (1.5, ["crash"])
    svc.search_service = MagicMock()
    svc.search_service.search_financial_context = AsyncMock(return_value=[
        {"title": "Stock market crash - Wikipedia", "link": "https://en.wikipedia.org/wiki/Crash", "snippet": "crash"},
        {"title": "Banks fail across Europe", "link": "https://www.reuters.com/a", "snippet": "crash"},
        {"title": "Banks fail across Europe as markets fall", "link": "https://www.ft.com/b", "snippet": "crash"},
    ])
    calls = []

    async def cooldown(name, seconds, fail_open):
        calls.append(name)
        return len(calls) == 1   # only the first event is new; the second was seen before

    svc._acquire_cooldown = cooldown
    out = await svc._check_global_macro_events()
    assert len(out) == 1
    assert "wikipedia" not in out[0]["text"].lower()
    assert out[0]["id"].startswith("global_macro_")
    assert all(c.startswith("global_event:") for c in calls)


@pytest.mark.asyncio
async def test_macro_state_alerts_fire_once_per_observation():
    from src.services.sentinel_service import SentinelService

    svc = SentinelService.__new__(SentinelService)
    svc.thresholds = {}
    svc.market_service = MagicMock()
    svc.market_service.get_macro_data.return_value = {
        "economics": {"FedFunds": {"trend": "Up", "value": 3.75, "date": "2026-09-01"},
                      "10Y2Y_Spread": {"value": -0.2}},
        "market_indicators": {},
    }
    seen = set()

    async def cooldown(name, seconds, fail_open):
        if name in seen:
            return False
        seen.add(name)
        return True

    svc._acquire_cooldown = cooldown
    first = await svc._check_macro_shifts()
    second = await svc._check_macro_shifts()
    assert {t["id"] for t in first} == {"macro_fed_rate_up", "macro_yield_inversion"}
    assert second == []
