"""
Unit tests for TieredApprovalService.
測試分級自動核准服務各項決策邊界與安全護欄。
"""

import pytest
from unittest.mock import MagicMock

from src.services.tiered_approval_service import TieredApprovalService, TieredApprovalResult
from src.domain.trading import Order, OrderAction, OrderType, OrderSizingMode


class MockSettingsRepo:
    def __init__(self, settings=None):
        self.settings = settings or {}

    def get(self, user_id, key):
        return self.settings.get(key)


class MockRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def pipeline(self):
        return self

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, 0)) + 1)
        return self

    def expire(self, key, ttl):
        return self

    def execute(self):
        # Return list of results for incr
        return [int(list(self.store.values())[-1]) if self.store else 1]


@pytest.fixture
def mock_redis():
    return MockRedis()


def test_tiered_approval_success(mock_redis):
    repo = MockSettingsRepo({
        "tiered_approval_enabled": True,
        "tiered_approval_auto_score_min": 6.8,
        "tiered_approval_max_amount_usd": 30.0,
        "tiered_approval_max_daily_count": 3,
    })
    service = TieredApprovalService(user_id="test_user", settings_repo=repo, redis_client=mock_redis)

    order = Order(
        symbol="AAPL",
        action=OrderAction.BUY,
        quantity=25.0,
        amount_usd=25.0,
        sizing_mode=OrderSizingMode.AMOUNT,
        order_type=OrderType.MARKET,
    )

    result = service.evaluate_approval(order=order, confidence_score=7.1, sentinel_status="NORMAL")

    assert result.approved is True
    assert result.tier == "TIER_2_AUTO_APPROVED"
    assert "Score 7.1 >= 6.8" in result.reason
    assert result.order_amount == 25.0


def test_tiered_approval_score_too_low(mock_redis):
    repo = MockSettingsRepo({
        "tiered_approval_enabled": True,
        "tiered_approval_auto_score_min": 6.8,
        "tiered_approval_max_amount_usd": 30.0,
        "tiered_approval_max_daily_count": 3,
    })
    service = TieredApprovalService(user_id="test_user", settings_repo=repo, redis_client=mock_redis)

    order = Order(
        symbol="NVDA",
        action=OrderAction.BUY,
        quantity=20.0,
        amount_usd=20.0,
        sizing_mode=OrderSizingMode.AMOUNT,
        order_type=OrderType.MARKET,
    )

    result = service.evaluate_approval(order=order, confidence_score=6.4, sentinel_status="NORMAL")

    assert result.approved is False
    assert result.tier == "TIER_3_MANUAL_REQUIRED"
    assert "below tiered auto-approval min" in result.reason


def test_tiered_approval_amount_exceeded(mock_redis):
    repo = MockSettingsRepo({
        "tiered_approval_enabled": True,
        "tiered_approval_auto_score_min": 6.8,
        "tiered_approval_max_amount_usd": 30.0,
        "tiered_approval_max_daily_count": 3,
    })
    service = TieredApprovalService(user_id="test_user", settings_repo=repo, redis_client=mock_redis)

    order = Order(
        symbol="MSFT",
        action=OrderAction.BUY,
        quantity=50.0,
        amount_usd=50.0,
        sizing_mode=OrderSizingMode.AMOUNT,
        order_type=OrderType.MARKET,
    )

    result = service.evaluate_approval(order=order, confidence_score=7.3, sentinel_status="NORMAL")

    assert result.approved is False
    assert result.tier == "TIER_3_MANUAL_REQUIRED"
    assert "exceeds tiered auto-approval cap" in result.reason


def test_tiered_approval_daily_quota_reached(mock_redis):
    repo = MockSettingsRepo({
        "tiered_approval_enabled": True,
        "tiered_approval_auto_score_min": 6.8,
        "tiered_approval_max_amount_usd": 30.0,
        "tiered_approval_max_daily_count": 2,
    })
    service = TieredApprovalService(user_id="test_user", settings_repo=repo, redis_client=mock_redis)

    # Record 2 approvals
    service.record_auto_approval()
    service.record_auto_approval()
    assert service.get_daily_approved_count() == 2

    order = Order(
        symbol="GOOGL",
        action=OrderAction.BUY,
        quantity=15.0,
        amount_usd=15.0,
        sizing_mode=OrderSizingMode.AMOUNT,
        order_type=OrderType.MARKET,
    )

    result = service.evaluate_approval(order=order, confidence_score=7.4, sentinel_status="NORMAL")

    assert result.approved is False
    assert result.tier == "TIER_3_MANUAL_REQUIRED"
    assert "Daily auto-approval quota reached" in result.reason


def test_tiered_approval_sentinel_panic_blocks(mock_redis):
    repo = MockSettingsRepo({
        "tiered_approval_enabled": True,
        "tiered_approval_auto_score_min": 6.8,
        "tiered_approval_max_amount_usd": 30.0,
        "tiered_approval_max_daily_count": 3,
    })
    service = TieredApprovalService(user_id="test_user", settings_repo=repo, redis_client=mock_redis)

    order = Order(
        symbol="SPY",
        action=OrderAction.BUY,
        quantity=20.0,
        amount_usd=20.0,
        sizing_mode=OrderSizingMode.AMOUNT,
        order_type=OrderType.MARKET,
    )

    result = service.evaluate_approval(order=order, confidence_score=7.5, sentinel_status="PANIC")

    assert result.approved is False
    assert "Sentinel status is PANIC" in result.reason


def test_tiered_approval_disabled_setting(mock_redis):
    repo = MockSettingsRepo({
        "tiered_approval_enabled": False,
        "tiered_approval_auto_score_min": 6.8,
        "tiered_approval_max_amount_usd": 30.0,
    })
    service = TieredApprovalService(user_id="test_user", settings_repo=repo, redis_client=mock_redis)

    order = Order(
        symbol="AAPL",
        action=OrderAction.BUY,
        quantity=10.0,
        amount_usd=10.0,
        sizing_mode=OrderSizingMode.AMOUNT,
        order_type=OrderType.MARKET,
    )

    result = service.evaluate_approval(order=order, confidence_score=7.2, sentinel_status="NORMAL")

    assert result.approved is False
    assert "disabled in user settings" in result.reason
