import pytest
from datetime import datetime, timedelta, timezone
from src.services.digest_nodes import (
    ops_selector,
    investment_selector,
    compose_ops_health,
    suppress_ops_health,
    compose_investment_digest,
    suppress_investment_digest,
    parse_datetime
)

def test_selectors():
    event_ops = {"event_type": "self_ops_alert"}
    event_ops_2 = {"event_type": "ops_check"}
    event_inv = {"event_type": "sentinel_alert"}
    event_inv_2 = {"event_type": "report"}

    assert ops_selector(event_ops) is True
    assert ops_selector(event_ops_2) is True
    assert ops_selector(event_inv) is False
    assert ops_selector(event_inv_2) is False

    assert investment_selector(event_ops) is False
    assert investment_selector(event_ops_2) is False
    assert investment_selector(event_inv) is True
    assert investment_selector(event_inv_2) is True


def test_compose_ops_health_merging():
    events = [
        {
            "event_type": "self_ops_alert",
            "content": {"title": "cost:daily_spike", "detail": "yesterday $35.00 vs prior mean $10.00", "severity": "warning"}
        },
        {
            "event_type": "self_ops_alert",
            "content": {"title": "cost:daily_spike", "detail": "spike in LLM cost detected", "severity": "warning"}
        },
        {
            "event_type": "self_ops_alert",
            "content": {"title": "heartbeat:failure", "detail": "celery worker unresponsive", "severity": "critical"}
        }
    ]

    title, content = compose_ops_health(events)
    assert "Ops Health" in title
    assert "今日系統事件共 3 件" in content
    assert "cost:daily_spike" in content
    assert "(共 2 次)" in content
    assert "heartbeat:failure" in content
    assert "(共 1 次)" in content
    assert "celery worker unresponsive" in content


def test_suppress_ops_health():
    assert suppress_ops_health([]) is True
    assert suppress_ops_health([{"id": "1"}]) is False


def test_suppress_investment_digest_p0_p1():
    # Has P1, should not suppress (returns False)
    events = [
        {"tier": "P1", "created_at": datetime.now(timezone.utc).isoformat()}
    ]
    assert suppress_investment_digest(events) is False

    # Has P0, should not suppress (returns False)
    events_p0 = [
        {"tier": "P0", "created_at": datetime.now(timezone.utc).isoformat()}
    ]
    assert suppress_investment_digest(events_p0) is False


def test_suppress_investment_digest_p2_count():
    # Only 2 P2 events, should suppress (returns True)
    events_2 = [
        {"tier": "P2", "created_at": datetime.now(timezone.utc).isoformat()},
        {"tier": "P2", "created_at": datetime.now(timezone.utc).isoformat()}
    ]
    assert suppress_investment_digest(events_2) is True

    # 3 P2 events, should not suppress (returns False)
    events_3 = [
        {"tier": "P2", "created_at": datetime.now(timezone.utc).isoformat()},
        {"tier": "P2", "created_at": datetime.now(timezone.utc).isoformat()},
        {"tier": "P2", "created_at": datetime.now(timezone.utc).isoformat()}
    ]
    assert suppress_investment_digest(events_3) is False


def test_suppress_investment_digest_old_p2():
    # 1 P2 event, but >24h old, should not suppress (returns False)
    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    events = [
        {"tier": "P2", "created_at": old_time}
    ]
    assert suppress_investment_digest(events) is False


def test_parse_datetime():
    assert parse_datetime(None) is None
    assert parse_datetime("") is None
    
    dt_now = datetime.now(timezone.utc)
    assert parse_datetime(dt_now) == dt_now
    
    iso_str = "2026-07-19T11:25:34+08:00"
    parsed = parse_datetime(iso_str)
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 7
    assert parsed.day == 19
    assert parsed.hour == 11
    
    utc_z_str = "2026-07-19T11:25:34Z"
    parsed_utc = parse_datetime(utc_z_str)
    assert parsed_utc is not None
    assert parsed_utc.tzinfo == timezone.utc


def test_compose_investment_digest_with_report():
    events = [
        {
            "event_type": "report",
            "tier": "P2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "content": {
                "title": "每日委員會投資報告",
                "summary": "【核心結論】巨集觀指標 Risk-On，建議加碼科技股，CIO 建議調高 NVDA/AAPL 權重。",
                "full_text": "【核心結論】巨集觀指標 Risk-On，建議加碼科技股，CIO 建議調高 NVDA/AAPL 權重。"
            }
        }
    ]
    title, content = compose_investment_digest(events)
    assert "Daily Portfolio Digest" in title
    assert "每日委員會投資報告" in content
    assert "核心結論" in content
    assert "NVDA/AAPL" in content


def test_suppress_investment_digest_report():
    events = [
        {
            "event_type": "report",
            "tier": "P2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "content": {"title": "每日委員會投資報告"}
        }
    ]
    assert suppress_investment_digest(events) is False
