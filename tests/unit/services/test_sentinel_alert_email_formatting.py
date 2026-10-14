import pytest
from unittest.mock import MagicMock
from src.services.sentinel_service import SentinelService

def test_format_sentinel_email_report_structure():
    mock_repo = MagicMock()
    mock_settings = MagicMock()
    mock_settings.user_id = "test_user"

    service = SentinelService(
        user_id="test_user",
        council_service=MagicMock(),
        settings_service=mock_settings,
        repo=mock_repo,
        snapshot_repo=mock_repo
    )
    service.current_vix = 26.5

    triggers = [
        {
            "id": "drop_NVDA",
            "level": "CRITICAL",
            "value": "-5.8%",
            "threshold": "-4.0%",
            "text": "📉 NVDA 跌 -5.8% (231.43 → 218.00)"
        },
        {
            "id": "vix_spike",
            "level": "WARNING",
            "value": "26.5",
            "threshold": "25.0",
            "text": "⚠️ VIX Spike: 26.5 > 25.0"
        }
    ]

    # Test 1: Fail-safe mode
    decision_failsafe = "⚠️ **系統運行於安全模式 (Council Deliberation Timeout)**"
    title, content = service._format_sentinel_email_report(
        topic="SENTINEL P1 ALERT: NVDA drop",
        decision=decision_failsafe,
        filtered_triggers=triggers,
        source="Sentinel",
        max_priority=1,
        is_extreme=True
    )

    # Verification: Title
    assert "🔴 Sentinel 風控警報" in title
    assert "NVDA" in title
    assert "VIX: 26.5" in title
    assert "CRITICAL" in title or "關鍵警戒" in title

    # Verification: Content Executive Summary Card
    assert "## 🛡️ Sentinel 風控執行摘要 (Executive Summary)" in content
    assert "VIX 26.50" in content
    assert "波動加劇 (High Volatility)" in content
    assert "數理自主安全防禦模式" in content

    # Verification: Table
    assert "| 觸發指標 ID | 等級 | 數值 / 狀態 | 參考門檻 | 說明明細 |" in content
    assert "`drop_NVDA`" in content
    assert "CRITICAL" in content
    assert "-5.8%" in content

    # Verification: Safety defenses
    assert "反向進出冷卻鎖 (24h Flip-Flop Lockout Guard)" in content
    assert "做市商 Gamma 與微觀流動性真空守衛" in content

    # Test 2: Council consensus mode
    decision_council = "📊 **投資委員會決議**：建議暫行觀望，維持現有持倉。"
    title_council, content_council = service._format_sentinel_email_report(
        topic="SENTINEL P2 ALERT: NVDA drop",
        decision=decision_council,
        filtered_triggers=triggers,
        source="Sentinel",
        max_priority=2,
        is_extreme=False
    )
    assert "P2" in title_council
    assert "投資委員會研議核定" in content_council
    assert "建議暫行觀望，維持現有持倉。" in content_council
