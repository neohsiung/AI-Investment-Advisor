"""
Unit tests for StaggeredDipBuyingService
========================================
主力支撐階梯限價吸籌服務單元測試
"""
import asyncio
from datetime import datetime, timezone
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.staggered_dip_buying_service import (
    StaggeredDipBuyingService,
    StaggeredTierPlan,
    TickerStaggeredPlan,
    StaggeredDipDeploymentPlan,
)
from src.services.smart_money_support_service import SmartMoneySupportResult


@pytest.fixture
def mock_support_service():
    svc = MagicMock()
    # Mocking AVWAP=140.0, POC=138.0, VAL=135.0, KeySupport=136.0, current_price=142.0
    svc.calculate_institutional_support.return_value = SmartMoneySupportResult(
        ticker="NVDA",
        current_price=142.0,
        anchored_vwap=140.0,
        point_of_control=138.0,
        value_area_high=145.0,
        value_area_low=135.0,
        high_volume_nodes=[138.0, 140.0],
        key_support_price=136.0,
        recommended_stop_loss=134.0,
        stop_loss_distance_pct=0.056,
        support_type="POC_SUPPORT",
        anchor_date="2026-08-01",
        rationale="AVWAP 140.0, POC 138.0, VAL 135.0",
    )
    return svc


@pytest.fixture
def mock_risk_gateway():
    gateway = AsyncMock()
    eval_res = MagicMock()
    eval_res.allowed = True
    eval_res.severity = "NORMAL"
    eval_res.primary_blocker = None
    eval_res.reasons = []
    gateway.evaluate_trade_risk.return_value = eval_res
    return gateway


@pytest.fixture
def mock_settings_service():
    svc = MagicMock()
    settings_dict = {
        "enable_staggered_dip_buying": True,
        "staggered_tier1_allocation_pct": 0.40,
        "staggered_tier2_allocation_pct": 0.35,
        "staggered_tier3_allocation_pct": 0.25,
        "staggered_tier1_dip_pct": 0.008,
        "staggered_tier2_dip_pct": 0.020,
        "staggered_tier3_dip_pct": 0.038,
        "staggered_auto_cancel_at_market_close": True,
    }
    svc.get_setting.side_effect = lambda k, default=None: settings_dict.get(k, default)
    return svc


@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    broker.place_order.return_value = {"order_id": "broker_ord_123", "status": "open"}
    broker.cancel_order.return_value = {"status": "cancelled"}
    return broker


def test_calculate_staggered_plan_standard_3_tiers(
    mock_support_service, mock_risk_gateway, mock_settings_service, mock_broker
):
    """驗證標準預算 ($30+ USD) 正確展開為 3 檔階梯限價，且價格單調遞減。"""
    async def _test():
        service = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            support_service=mock_support_service,
            risk_gateway=mock_risk_gateway,
            broker=mock_broker,
        )

        plan = await service.calculate_staggered_plan_for_ticker(
            ticker="NVDA",
            target_budget_usd=100.0,
            current_price=142.0,
        )

        assert plan.ticker == "NVDA"
        assert plan.current_price == 142.0
        assert plan.total_budget_usd == 100.0
        assert len(plan.tiers) == 3
        assert plan.is_risk_allowed is True

        t1, t2, t3 = plan.tiers
        assert t1.tier_number == 1
        assert t2.tier_number == 2
        assert t3.tier_number == 3

        # 驗證資金分配比例 (40%, 35%, 25%)
        assert t1.allocation_usd == 40.0
        assert t2.allocation_usd == 35.0
        assert t3.allocation_usd == 25.0
        assert sum(t.allocation_usd for t in plan.tiers) == 100.0

        # 驗證單調遞減：P_t3 < P_t2 < P_t1 < P_current
        assert t3.target_price < t2.target_price < t1.target_price < plan.current_price
        assert t1.discount_pct > 0.0
        assert t2.discount_pct > t1.discount_pct
        assert t3.discount_pct > t2.discount_pct

    asyncio.run(_test())


def test_calculate_staggered_plan_budget_folding(
    mock_support_service, mock_risk_gateway, mock_settings_service, mock_broker
):
    """驗證小預算彈性折疊：<$20 折疊為 1 檔，<$30 折疊為 2 檔，<$10 無法下單。"""
    async def _test():
        service = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            support_service=mock_support_service,
            risk_gateway=mock_risk_gateway,
            broker=mock_broker,
        )

        # 1. 預算 < $10 -> 0 檔
        p_low = await service.calculate_staggered_plan_for_ticker("NVDA", 8.0)
        assert len(p_low.tiers) == 0

        # 2. 預算 $15 (< $20) -> 折疊為 1 檔
        p_1tier = await service.calculate_staggered_plan_for_ticker("NVDA", 15.0)
        assert len(p_1tier.tiers) == 1
        assert p_1tier.tiers[0].allocation_usd == 15.0
        assert p_1tier.tiers[0].target_price < p_1tier.current_price

        # 3. 預算 $25 (< $30) -> 折疊為 2 檔
        p_2tier = await service.calculate_staggered_plan_for_ticker("NVDA", 25.0)
        assert len(p_2tier.tiers) == 2
        assert p_2tier.tiers[0].allocation_usd + p_2tier.tiers[1].allocation_usd == 25.0
        assert p_2tier.tiers[1].target_price < p_2tier.tiers[0].target_price < p_2tier.current_price

    asyncio.run(_test())


def test_calculate_staggered_plan_risk_blocked(
    mock_support_service, mock_settings_service, mock_broker
):
    """驗證 UnifiedRiskGateway 阻斷時，嚴格 Fail-Closed。"""
    async def _test():
        blocked_gateway = AsyncMock()
        eval_res = MagicMock()
        eval_res.allowed = False
        eval_res.severity = "CRITICAL"
        eval_res.primary_blocker = "ConsecutiveLossLockout"
        eval_res.reasons = ["Last 3 decisions all lost alpha"]
        blocked_gateway.evaluate_trade_risk.return_value = eval_res

        service = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            support_service=mock_support_service,
            risk_gateway=blocked_gateway,
            broker=mock_broker,
        )

        plan = await service.calculate_staggered_plan_for_ticker("NVDA", 50.0)
        assert plan.is_risk_allowed is False
        assert plan.risk_blocker == "ConsecutiveLossLockout"
        assert "Last 3 decisions all lost alpha" in plan.risk_reasons

    asyncio.run(_test())


def test_execute_staggered_dip_deployment(
    mock_support_service, mock_risk_gateway, mock_settings_service, mock_broker
):
    """驗證下發階梯掛單流程、券商調用與 Redis 寫入。"""
    async def _test():
        service = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            support_service=mock_support_service,
            risk_gateway=mock_risk_gateway,
            broker=mock_broker,
        )

        fake_plan = StaggeredDipDeploymentPlan(
            batch_number=1,
            total_deployable_cash=500.0,
            total_planned_deployment_usd=100.0,
            plans=[
                TickerStaggeredPlan(
                    ticker="NVDA",
                    current_price=140.0,
                    total_budget_usd=100.0,
                    tiers=[
                        StaggeredTierPlan(1, "Tier 1", 138.0, 0.014, 40.0, 0.40, 0.289, "POC", "POC anchor"),
                        StaggeredTierPlan(2, "Tier 2", 135.0, 0.035, 35.0, 0.35, 0.259, "VAL", "VAL anchor"),
                        StaggeredTierPlan(3, "Tier 3", 132.0, 0.057, 25.0, 0.25, 0.189, "VAL_DEEP", "Deep discount"),
                    ],
                    is_risk_allowed=True,
                )
            ],
            can_execute=True,
        )

        fake_redis = AsyncMock()
        fake_redis.get.return_value = None
        fake_redis.setex = AsyncMock()

        with patch.object(service, "generate_batch_staggered_plan", return_value=fake_plan), \
             patch("src.infrastructure.cache.redis_client.get_redis", return_value=fake_redis), \
             patch.object(service, "dispatch_staggered_deployment_alert", return_value={"success": True}):

            res = await service.execute_staggered_dip_deployment(batch_number=1, force=False)

            assert res["success"] is True
            assert res["status"] == "orders_placed"
            assert res["order_count"] == 3
            assert res["total_planned_usd"] == 100.0
            assert mock_broker.place_order.call_count == 3
            assert fake_redis.setex.call_count == 1

    asyncio.run(_test())


def test_cancel_all_pending_staggered_orders(
    mock_support_service, mock_risk_gateway, mock_settings_service, mock_broker
):
    """驗證收盤前 15:55 EST 自動撤除未成交掛單並正確精算釋放現金。"""
    async def _test():
        service = StaggeredDipBuyingService(
            user_id="test_user",
            settings_service=mock_settings_service,
            support_service=mock_support_service,
            risk_gateway=mock_risk_gateway,
            broker=mock_broker,
        )

        mock_orders = [
            {"order_id": "ord_1", "ticker": "NVDA", "status": "PENDING", "amount_usd": 40.0, "broker_order_id": "b_1"},
            {"order_id": "ord_2", "ticker": "NVDA", "status": "FILLED", "amount_usd": 35.0, "broker_order_id": "b_2"},
            {"order_id": "ord_3", "ticker": "NVDA", "status": "PENDING", "amount_usd": 25.0, "broker_order_id": "b_3"},
        ]

        fake_redis = AsyncMock()
        fake_redis.get.return_value = json.dumps(mock_orders)
        fake_redis.setex = AsyncMock()

        with patch("src.infrastructure.cache.redis_client.get_redis", return_value=fake_redis):
            res = await service.cancel_all_pending_staggered_orders(reason="15:55 EST 收盤前自動撤單")

            assert res["success"] is True
            assert res["cancelled_count"] == 2
            assert res["released_cash_usd"] == 65.0
            assert res["filled_count"] == 1
            assert res["filled_cash_usd"] == 35.0
            assert mock_broker.cancel_order.call_count == 2
            assert fake_redis.setex.call_count == 1

    asyncio.run(_test())


def test_batch_cash_deployment_service_staggered_limit_mode():
    """驗證 BatchCashDeploymentService 透過 deployment_mode='STAGGERED_LIMIT' 正確調用階梯吸籌。"""
    async def _test():
        from src.services.batch_cash_deployment_service import BatchCashDeploymentService

        svc = BatchCashDeploymentService(user_id="test_user")
        mock_stagger = AsyncMock()
        mock_stagger.execute_staggered_dip_deployment.return_value = {
            "success": True,
            "status": "orders_placed",
            "order_count": 3,
        }
        svc.staggered_dip_service = mock_stagger

        res = await svc.execute_batch(batch_number=1, force=True, deployment_mode="STAGGERED_LIMIT")
        assert res["success"] is True
        assert res["status"] == "orders_placed"
        mock_stagger.execute_staggered_dip_deployment.assert_awaited_once_with(batch_number=1, force=True)

    asyncio.run(_test())


def test_conversation_router_dipbuy_commands():
    """驗證 ConversationRouter 的 /dipbuy 快捷指令 (plan, status, run, cancel)。"""
    async def _test():
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()

        # 1. 驗證指令識別
        assert router._is_system_command("/dipbuy") is True
        assert router._is_system_command("/dipbuy plan") is True
        assert router._is_system_command("/dipbuy status") is True
        assert router._is_system_command("/dipbuy cancel") is True
        assert router._is_system_command("階梯掛單") is True

        # 2. 模擬 /dipbuy cancel
        mock_stagger = AsyncMock()
        mock_stagger.cancel_all_pending_staggered_orders.return_value = {
            "success": True,
            "cancelled_count": 3,
            "released_cash_usd": 100.0,
            "filled_count": 1,
            "filled_cash_usd": 35.0,
        }

        with patch("src.services.staggered_dip_buying_service.StaggeredDipBuyingService", return_value=mock_stagger):
            reply = await router._handle_system_command(
                adapter=None,
                channel_user_id="test_channel",
                text="/dipbuy cancel",
                resolved_user_id="test_user",
            )
            assert reply is not None
            assert "主力支撐階梯掛單安全撤除完成" in reply
            assert "3 筆" in reply
            assert "+$100.00 USD" in reply

    asyncio.run(_test())
