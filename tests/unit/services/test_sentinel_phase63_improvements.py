import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.sentinel_service import SentinelService

@pytest.fixture
def anyio_backend():
    return "asyncio"

def create_mock_sentinel():
    mock_repo = MagicMock()
    mock_settings = MagicMock()
    mock_settings.user_id = "test_user"

    service = SentinelService(
        user_id="test_user",
        council_service=MagicMock(),
        settings_service=mock_settings,
        repo=mock_repo,
        snapshot_repo=mock_repo,
    )
    service.current_vix = 22.0
    return service

@pytest.mark.asyncio
async def test_sentinel_email_report_autonomous_and_operator_sections():
    service = create_mock_sentinel()
    triggers = [
        {
            "id": "drop_NVDA",
            "level": "CRITICAL",
            "value": "-5.2%",
            "threshold": "-4.0%",
            "text": "📉 NVDA 跌 -5.2% (135.00 → 128.00)",
        }
    ]
    decision = "📊 **投資委員會決議**：建議觀望，大趨勢多頭未變。"
    title, content = service._format_sentinel_email_report(
        topic="SENTINEL P1 ALERT: NVDA drop",
        decision=decision,
        filtered_triggers=triggers,
        source="Sentinel",
        max_priority=1,
        is_extreme=False,
    )

    # Verify sections exist
    assert "### 🛡️ 【系統已自主完成之防守處置】(Autonomous System Defense)" in content
    assert "### 🧭 【用戶手動介入指南】(Operator Action Directives)" in content
    assert "遲滯回差帶過濾器 (Schmitt Trigger Hysteresis)" in content
    assert "大趨勢多頭單向鎖定 (Macro Long-Only Lock)" in content
    assert "做市商摩擦成本感知 (Turnover Friction Hurdle)" in content
    assert "系統狀態安全，無需人工干預" in content

@pytest.mark.asyncio
async def test_sentinel_email_report_actionable_operator_guidance():
    service = create_mock_sentinel()
    triggers = [
        {
            "id": "drop_NVDA",
            "level": "CRITICAL",
            "value": "-8.5%",
            "threshold": "-4.0%",
            "text": "📉 NVDA 跌 -8.5%",
        }
    ]
    # Decision contains actionable word "sell"
    decision = "🚨 **決議**：破位觸發停損，建議適度 trim 或 exit。"
    title, content = service._format_sentinel_email_report(
        topic="SENTINEL P1 ALERT: NVDA critical drop",
        decision=decision,
        filtered_triggers=triggers,
        source="Sentinel",
        max_priority=1,
        is_extreme=True,
    )

    assert "用戶手動介入指南" in content
    assert "建議審閱處置" in content

@pytest.mark.asyncio
async def test_sliding_window_debounce_behavior():
    service = create_mock_sentinel()
    # Mock redis buffer try_acquire
    service._redis_buffer.try_acquire = AsyncMock()

    # Case 1: First trigger (lock acquired) -> not debounced
    service._redis_buffer.try_acquire.return_value = True
    trig1 = {"id": "drop_NVDA", "ticker": "NVDA", "priority": 2, "level": "WARNING"}
    debounced = await service._is_trigger_debounced(trig1, default_debounce_seconds=300)
    assert debounced is False

    # Case 2: Second trigger within 300s (lock already held) -> debounced
    service._redis_buffer.try_acquire.return_value = False
    debounced_second = await service._is_trigger_debounced(trig1, default_debounce_seconds=300)
    assert debounced_second is True

    # Case 3: Emergency / P0 trigger -> bypasses debounce unconditionally
    trig_p0 = {"id": "crash_NVDA", "ticker": "NVDA", "priority": 0, "level": "EMERGENCY"}
    debounced_p0 = await service._is_trigger_debounced(trig_p0, default_debounce_seconds=300)
    assert debounced_p0 is False
