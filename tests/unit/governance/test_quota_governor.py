import pytest
import time
import asyncio
from src.infrastructure.governance.quota_governor import ExternalQuotaGovernor, QuotaRule


@pytest.fixture
def governor():
    custom_rules = {
        "test_fast": QuotaRule(limit_count=10, window_seconds=1.0, utilization_cap=0.60, min_interval_seconds=0.0),
        "test_slow": QuotaRule(limit_count=5, window_seconds=60.0, utilization_cap=0.60, min_interval_seconds=0.05),
    }
    return ExternalQuotaGovernor(custom_rules=custom_rules)


@pytest.mark.asyncio
async def test_quota_governor_enforces_60_percent_cap(governor):
    # Rule allows 10 calls per sec, capped at 60% -> max 6 calls allowed
    rule = governor.rules["test_fast"]
    assert rule.max_allowed_count == 6

    # First 6 calls succeed
    for i in range(6):
        assert await governor.acquire("test_fast", wait=False) is True

    # 7th call must be blocked immediately because 60% cap is hit
    assert await governor.acquire("test_fast", wait=False) is False
    assert governor.can_acquire("test_fast") is False

    # Check utilization reporting
    status = governor.get_status("test_fast")
    assert status["current_window_usage"] == 6
    assert status["official_utilization"] == 0.6  # 6/10 = 60%
    assert status["capped_utilization"] == 1.0    # 6/6 = 100% of the 60% limit
    assert status["headroom_pct"] == 40.0        # 40% headroom preserved


@pytest.mark.asyncio
async def test_quota_governor_unmanaged_provider(governor):
    # Unmanaged provider should pass through
    assert await governor.acquire("unmanaged_api", wait=False) is True
    assert governor.can_acquire("unmanaged_api") is True


@pytest.mark.asyncio
async def test_quota_governor_sliding_window_expiration(governor):
    # Acquire 6 calls in 1s window
    for _ in range(6):
        await governor.acquire("test_fast", wait=False)
    assert governor.can_acquire("test_fast") is False

    # Sleep slightly over 1s for the window to clear
    await asyncio.sleep(1.05)

    # Now capacity is restored
    assert governor.can_acquire("test_fast") is True
    assert await governor.acquire("test_fast", wait=False) is True


@pytest.mark.asyncio
async def test_quota_governor_min_interval_spacing(governor):
    # test_slow has min_interval_seconds = 0.05
    assert await governor.acquire("test_slow", wait=False) is True
    # Immediate second call fails because spacing < 0.05
    assert await governor.acquire("test_slow", wait=False) is False
    # With wait=True, it waits 0.05s and succeeds
    assert await governor.acquire("test_slow", wait=True, max_wait_seconds=0.5) is True

