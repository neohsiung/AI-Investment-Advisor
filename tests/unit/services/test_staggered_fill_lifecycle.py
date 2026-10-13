"""
Unit tests for Staggered Limit Fills Reconciliation & Position Onboarding Lifecycle
測試盤中階梯限價撮合對帳與持倉自動接管 (Phase 45)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.staggered_dip_buying_service import StaggeredDipBuyingService


@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    broker.place_order.return_value = {"order_id": "broker_order_123", "status": "PENDING"}
    return broker


@pytest.fixture
def mock_settings_service():
    settings = MagicMock()
    settings.get_setting.side_effect = lambda key, default=None: {
        "enable_staggered_dip_buying": True,
        "enable_staggered_fills_reconciliation": True,
    }.get(key, default)
    return settings


@pytest.fixture
def mock_market_data_service():
    mkt = AsyncMock()
    # 模擬即時報價，Low 觸及限價點位
    mkt.get_quote.return_value = {
        "ticker": "MSFT",
        "last": 498.00,
        "low": 495.00,
        "bid": 497.50,
        "ask": 498.50,
    }
    mkt.get_history_df = MagicMock(return_value=None)
    return mkt


def test_reconcile_staggered_order_fills_success(
    mock_broker, mock_settings_service, mock_market_data_service
):
    """驗證當市場低點觸及 Target Price 時，成功觸發撮合、更新狀態並自動交接持倉"""
    async def _test():
        svc = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            broker=mock_broker,
            market_data_service=mock_market_data_service,
        )

        mock_redis = AsyncMock()
        orders_data = [
            {
                "order_id": "dip_MSFT_1_abc123",
                "user_id": "test_user",
                "ticker": "MSFT",
                "tier_number": 1,
                "tier_name": "Tier 1 (輕度回踩)",
                "limit_price": 498.10,
                "amount_usd": 36.40,
                "discount_pct": 0.08,
                "status": "PENDING",
            }
        ]
        mock_redis.get.return_value = json.dumps(orders_data)

        with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis), \
             patch.object(svc, "dispatch_staggered_fill_alert", new_callable=AsyncMock) as mock_alert:

            res = await svc.reconcile_staggered_order_fills()

            assert res["status"] == "reconciled"
            assert res["filled_count"] == 1
            assert res["remaining_pending_count"] == 0

            filled = res["filled_orders"][0]
            assert filled["status"] == "FILLED"
            assert filled["fill_price"] == 498.10
            assert "filled_at" in filled
            assert filled["initial_stop_price"] < 498.10

            # 驗證補單下單被呼叫 (市價買入 $36.40)
            mock_broker.place_order.assert_awaited_once()

            # 驗證通知被分派
            mock_alert.assert_awaited_once()

            # 驗證 Redis 寫入最高價與停損線
            assert mock_redis.setex.call_count >= 2

    asyncio.run(_test())


def test_reconcile_staggered_order_fills_no_trigger(
    mock_broker, mock_settings_service
):
    """驗證市場低點高於限價目標時，維持 PENDING 繼續監控"""
    async def _test():
        mkt = AsyncMock()
        # 當日最低點 520.00，高於限價 498.10，未觸及
        mkt.get_quote.return_value = {
            "ticker": "MSFT",
            "last": 530.00,
            "low": 520.00,
        }

        svc = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            broker=mock_broker,
            market_data_service=mkt,
        )

        mock_redis = AsyncMock()
        orders_data = [
            {
                "order_id": "dip_MSFT_1_abc123",
                "ticker": "MSFT",
                "tier_number": 1,
                "limit_price": 498.10,
                "amount_usd": 36.40,
                "status": "PENDING",
            }
        ]
        mock_redis.get.return_value = json.dumps(orders_data)

        with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis):
            res = await svc.reconcile_staggered_order_fills()

            assert res["status"] == "reconciled"
            assert res["filled_count"] == 0
            assert res["remaining_pending_count"] == 1
            mock_broker.place_order.assert_not_awaited()

    asyncio.run(_test())


def test_onboard_filled_position_atr_protection(
    mock_settings_service, mock_market_data_service
):
    """驗證持倉接管時，強制至少 4.5% 防禦停損緩衝空間"""
    async def _test():
        svc = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            market_data_service=mock_market_data_service,
        )

        mock_redis = AsyncMock()
        with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis):
            stop_price = await svc._onboard_filled_position(
                ticker="MSFT",
                fill_price=500.0,
                amount_usd=50.0,
                tier_name="Tier 1",
                discount_pct=0.05,
            )

            # 500 * (1 - 0.045) = 477.5
            assert stop_price <= 477.5
            mock_redis.setex.assert_any_call("sentinel:highest_price:test_user:MSFT", 2592000, "500.0")
            mock_redis.setex.assert_any_call("sentinel:trailing_stop:test_user:MSFT", 2592000, str(stop_price))

    asyncio.run(_test())


def test_conversation_router_dipbuy_reconcile():
    """驗證 /dipbuy reconcile 對話指令交互"""
    async def _test():
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()

        mock_stagger = AsyncMock()
        mock_stagger.reconcile_staggered_order_fills.return_value = {
            "status": "reconciled",
            "filled_count": 2,
            "remaining_pending_count": 1,
        }

        with patch("src.services.staggered_dip_buying_service.StaggeredDipBuyingService", return_value=mock_stagger):
            reply = await router._handle_system_command(
                adapter=None,
                channel_user_id="test_channel",
                text="/dipbuy reconcile",
                resolved_user_id="test_user",
            )
            assert "階梯限價吸籌撮合對帳完成" in reply
            assert "2 筆" in reply
            assert "1 筆" in reply
            mock_stagger.reconcile_staggered_order_fills.assert_awaited_once()

    asyncio.run(_test())
