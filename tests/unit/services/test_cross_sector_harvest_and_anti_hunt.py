"""
Unit Tests for Cross-Sector Dynamic Harvest & Microstructure Anti-Hunt Detector (Phase 59)
==========================================================================================
測試涵蓋：
1. HarvestCandidateMetric 與 HarvestAssessmentResult 序列化/反序列化 (to_dict, from_dict)
2. CrossSectorHarvestRebalanceService 4 級體制狀態機：
   - HARVEST_ELIGIBLE (HHI 自癒且利潤 >= 10.0%, 減碼 50% 鎖利回流)
   - RUNNER_PRESERVE (利潤 >= 15.0%, 減碼 50% 鎖利，剩餘掛載移動停利)
   - HOLDING_STABILIZING (HHI 未自癒或利潤未達標，維持持倉平抑波動)
   - NORMAL (科技股不予跨板塊收割)
   - 暴利防禦減碼 (即使 HHI 未達標，個股 >= 20.0% 亦減碼 30%)
3. execute_harvest_orders 委託執行與 UnifiedRiskGatewayService 風控審核 (Fail-Open)
4. Redis 持久化快取 (portfolio:recirculated_cash)
5. 雙渠道收割戰報生成 (format_harvest_report)
6. SpoofingMetric 序列化/反序列化 (to_dict, from_dict)
7. MicrostructureSpoofingDetectorService 4 級反欺詐嗅探體制：
   - SPOOF_HUNT_DETECTED (CFR >= 3.0 或存續 < 2.0s -> 向下平移 0.40%)
   - PHANTOM_LIQUIDITY_WARNING (2.0 <= CFR < 3.0 -> 向下平移 0.20%)
   - CLEAN_ORDER_FLOW (CFR < 2.0 -> 0.0% 平移)
   - 點差擴大特徵推導 (spread >= 0.25% -> 假單獵殺)
8. 微觀嗅探 Redis 快取與自適應目標價重新映射
9. 雙渠道反欺詐嗅探戰報生成 (format_spoofing_report)
10. StaggeredDipBuyingService 整合微觀反獵殺平移 (階梯吸籌與盤中追單)
11. 對話路由器 0-LLM 指令直通 (/harvest, /spoof 及別名)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import pytest

from src.services.cross_sector_harvest_rebalance_service import (
    CrossSectorHarvestRebalanceService,
    HarvestAssessmentResult,
    HarvestCandidateMetric,
)
from src.services.microstructure_spoofing_detector_service import (
    MicrostructureSpoofingDetectorService,
    SpoofingMetric,
)
from src.services.sector_drift_guard_service import PortfolioSectorReport, SectorDriftStatus


# ═══════════════════════════════════════════════════════════════════════════
# Part 1: Phase 59A - CrossSectorHarvestRebalanceService Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_harvest_metric_and_assessment_serialization():
    """驗證收割指標與評估成果之序列化與反序列化一致性"""
    metric = HarvestCandidateMetric(
        ticker="V",
        sector="Financials",
        shares=10.0,
        current_price=280.0,
        market_value=2800.0,
        cost_basis=2500.0,
        unrealized_pnl_usd=300.0,
        unrealized_pnl_pct=12.0,
        status="HARVEST_ELIGIBLE",
        recommended_harvest_shares=5.0,
        recirculated_usd=1400.0,
        rationale="HHI 自癒且獲利達標",
        is_cross_sector_contender=True,
    )
    d = metric.to_dict()
    assert d["ticker"] == "V"
    assert d["recommended_harvest_shares"] == 5.0
    assert d["recirculated_usd"] == 1400.0

    restored = HarvestCandidateMetric.from_dict(d)
    assert restored.ticker == "V"
    assert restored.status == "HARVEST_ELIGIBLE"
    assert restored.shares == 10.0

    assessment = HarvestAssessmentResult(
        portfolio_hhi=0.175,
        is_hhi_healthy=True,
        total_recirculated_cash_usd=1400.0,
        candidates=[metric],
        can_execute_harvest=True,
    )
    ad = assessment.to_dict()
    assert ad["portfolio_hhi"] == 0.175
    assert ad["can_execute_harvest"] is True
    assert len(ad["candidates"]) == 1

    restored_ass = HarvestAssessmentResult.from_dict(ad)
    assert restored_ass.portfolio_hhi == 0.175
    assert restored_ass.is_hhi_healthy is True
    assert len(restored_ass.candidates) == 1
    assert restored_ass.candidates[0].ticker == "V"


@pytest.mark.asyncio
async def test_harvest_evaluation_state_machine():
    """驗證動態收割評估狀態機之判定邏輯"""
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "enable_cross_sector_harvest_rebalance": True,
        "cross_sector_harvest_safe_hhi_threshold": 0.18,
        "cross_sector_harvest_min_profit_pct": 10.0,
    }.get(k, default)

    drift_guard = MagicMock()
    # 模擬 HHI 健康自癒 (0.16 <= 0.18, 科技股 25% <= 28%)
    drift_guard.analyze_portfolio_holdings.return_value = PortfolioSectorReport(
        status=SectorDriftStatus.BALANCED,
        hhi_index=0.16,
        max_limit_pct=0.30,
        warning_limit_pct=0.25,
        sector_weights={"Technology": 0.25, "Financials": 0.35, "Energy": 0.40},
        nlv_sector_weights={"Technology": 0.25, "Financials": 0.35, "Energy": 0.40},
        sector_values={"Technology": 400.0, "Financials": 600.0, "Energy": 685.0},
    )
    drift_guard.get_stock_sector.side_effect = lambda sym: {
        "V": "Financials",
        "COP": "Energy",
        "NVDA": "Technology",
        "ECL": "Materials",
    }.get(sym, "Unknown")

    svc = CrossSectorHarvestRebalanceService(
        user_id="user_123",
        settings_service=settings,
        sector_drift_guard=drift_guard,
    )

    positions = [
        # V: 獲利 12% (HARVEST_ELIGIBLE)
        {"symbol": "V", "quantity": 10.0, "current_price": 280.0, "average_entry_price": 250.0},
        # COP: 獲利 16% (RUNNER_PRESERVE)
        {"symbol": "COP", "quantity": 20.0, "current_price": 116.0, "average_entry_price": 100.0},
        # NVDA: 科技股 (NORMAL)
        {"symbol": "NVDA", "quantity": 4.0, "current_price": 130.0, "average_entry_price": 110.0},
        # ECL: 獲利 4% (HOLDING_STABILIZING)
        {"symbol": "ECL", "quantity": 5.0, "current_price": 208.0, "average_entry_price": 200.0},
    ]

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        result = await svc.evaluate_portfolio_harvest(positions=positions, total_equity=1685.0)

        assert result.portfolio_hhi == 0.16
        assert result.is_hhi_healthy is True
        assert result.can_execute_harvest is True

        cand_map = {c.ticker: c for c in result.candidates}
        assert cand_map["V"].status == "HARVEST_ELIGIBLE"
        assert cand_map["V"].recommended_harvest_shares == 5.0
        assert cand_map["V"].recirculated_usd == 1400.0

        assert cand_map["COP"].status == "RUNNER_PRESERVE"
        assert cand_map["COP"].recommended_harvest_shares == 10.0
        assert cand_map["COP"].recirculated_usd == 1160.0

        assert cand_map["NVDA"].status == "NORMAL"
        assert cand_map["NVDA"].recommended_harvest_shares == 0.0

        assert cand_map["ECL"].status == "HOLDING_STABILIZING"
        assert cand_map["ECL"].recommended_harvest_shares == 0.0

        assert result.total_recirculated_cash_usd == 2560.0
        mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_harvest_evaluation_hhi_unhealthy_extreme_profit():
    """驗證 HHI 仍偏高時，個股若達到 +20% 暴利則觸發 30% 減碼"""
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "enable_cross_sector_harvest_rebalance": True,
        "cross_sector_harvest_safe_hhi_threshold": 0.18,
        "cross_sector_harvest_min_profit_pct": 10.0,
    }.get(k, default)

    drift_guard = MagicMock()
    # 模擬 HHI 未自癒 (0.28 > 0.18, 科技股 40% > 28%)
    drift_guard.analyze_portfolio_holdings.return_value = PortfolioSectorReport(
        status=SectorDriftStatus.DRIFT_BREACH,
        hhi_index=0.28,
        max_limit_pct=0.30,
        warning_limit_pct=0.25,
        sector_weights={"Technology": 0.40, "Energy": 0.60},
        nlv_sector_weights={"Technology": 0.40, "Energy": 0.60},
        sector_values={"Technology": 600.0, "Energy": 900.0},
    )
    drift_guard.get_stock_sector.side_effect = lambda sym: "Energy" if sym == "COP" else "Technology"

    svc = CrossSectorHarvestRebalanceService(
        user_id="user_123",
        settings_service=settings,
        sector_drift_guard=drift_guard,
    )

    positions = [
        # COP: 獲利 +25% (>= 20.0%) -> 減碼 30%
        {"symbol": "COP", "quantity": 10.0, "current_price": 125.0, "average_entry_price": 100.0},
    ]

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        result = await svc.evaluate_portfolio_harvest(positions=positions, total_equity=1500.0)
        assert result.is_hhi_healthy is False
        cand = result.candidates[0]
        assert cand.ticker == "COP"
        assert cand.status == "HARVEST_ELIGIBLE"
        assert cand.recommended_harvest_shares == 3.0  # 10.0 * 0.30
        assert cand.recirculated_usd == 375.0          # 3.0 * 125.0


@pytest.mark.asyncio
async def test_execute_harvest_orders_with_risk_gateway():
    """驗證收割訂單執行、UnifiedRiskGatewayService 風控審核與券商調用"""
    risk_gateway = MagicMock()
    # 模擬風控審核通過
    risk_res = MagicMock()
    risk_res.is_allowed = True
    risk_res.reasons = []
    risk_gateway.evaluate_trade_risk = AsyncMock(return_value=risk_res)

    broker = MagicMock()
    broker.place_order = AsyncMock(return_value={"order_id": "ord_harvest_123", "status": "submitted"})

    svc = CrossSectorHarvestRebalanceService(
        user_id="user_123",
        risk_gateway=risk_gateway,
        broker=broker,
    )

    metric = HarvestCandidateMetric(
        ticker="V",
        sector="Financials",
        shares=10.0,
        current_price=280.0,
        market_value=2800.0,
        cost_basis=2500.0,
        unrealized_pnl_usd=300.0,
        unrealized_pnl_pct=12.0,
        status="HARVEST_ELIGIBLE",
        recommended_harvest_shares=5.0,
        recirculated_usd=1400.0,
        rationale="收割鎖利",
    )
    assessment = HarvestAssessmentResult(
        portfolio_hhi=0.17,
        is_hhi_healthy=True,
        total_recirculated_cash_usd=1400.0,
        candidates=[metric],
        can_execute_harvest=True,
    )

    res = await svc.execute_harvest_orders(assessment)
    assert res["status"] == "success"
    assert res["executed_count"] == 1
    assert res["total_recirculated_usd"] == 1400.0
    risk_gateway.evaluate_trade_risk.assert_called_once_with(
        ticker="V",
        action="SELL",
        shares=5.0,
        price=280.0,
        order_type="MARKET",
    )
    broker.place_order.assert_called_once_with(
        symbol="V",
        action="SELL",
        shares=5.0,
        order_type="MARKET",
    )


def test_format_harvest_report():
    """驗證收割雙渠道 HTML 戰報排版格式"""
    svc = CrossSectorHarvestRebalanceService(user_id="user_123")
    metric = HarvestCandidateMetric(
        ticker="V",
        sector="Financials",
        shares=10.0,
        current_price=280.0,
        market_value=2800.0,
        cost_basis=2500.0,
        unrealized_pnl_usd=300.0,
        unrealized_pnl_pct=12.0,
        status="HARVEST_ELIGIBLE",
        recommended_harvest_shares=5.0,
        recirculated_usd=1400.0,
        rationale="HHI 自癒且獲利達標",
    )
    assessment = HarvestAssessmentResult(
        portfolio_hhi=0.165,
        is_hhi_healthy=True,
        total_recirculated_cash_usd=1400.0,
        candidates=[metric],
        can_execute_harvest=True,
    )

    report = svc.format_harvest_report(assessment, channel="telegram")
    assert "跨板塊注入標的動態收割與利差回流儀表" in report
    assert "0.1650" in report
    assert "$1,400.00 USD" in report
    assert "HARVEST_ELIGIBLE" in report
    assert "V" in report
    assert "Financials" in report


# ═══════════════════════════════════════════════════════════════════════════
# Part 2: Phase 59B - MicrostructureSpoofingDetectorService Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_spoofing_metric_serialization():
    """驗證微觀欺詐指標序列化與反序列化"""
    metric = SpoofingMetric(
        ticker="NVDA",
        regime="SPOOF_HUNT_DETECTED",
        cancel_to_fill_ratio=3.5,
        depth_persistence_seconds=1.2,
        anti_hunt_downward_offset_pct=0.004,
        original_target_price=120.0,
        adjusted_target_price=119.52,
        rationale="偵測到假單誘多",
    )
    d = metric.to_dict()
    assert d["ticker"] == "NVDA"
    assert d["cancel_to_fill_ratio"] == 3.5
    assert d["anti_hunt_downward_offset_pct"] == 0.004
    assert d["adjusted_target_price"] == 119.52

    restored = SpoofingMetric.from_dict(d)
    assert restored.ticker == "NVDA"
    assert restored.regime == "SPOOF_HUNT_DETECTED"
    assert restored.adjusted_target_price == 119.52


@pytest.mark.asyncio
async def test_spoofing_evaluation_state_machine():
    """驗證 4 級反欺詐嗅探體制判定與階梯目標價向下平移計算"""
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "enable_microstructure_spoofing_shield": True,
        "spoofing_cancel_to_fill_ratio_threshold": 3.0,
        "spoofing_anti_hunt_downward_offset_pct": 0.004,
    }.get(k, default)

    svc = MicrostructureSpoofingDetectorService(
        user_id="user_123",
        settings_service=settings,
    )

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # 無快取
        mock_get_redis.return_value = mock_redis

        # 1. SPOOF_HUNT_DETECTED: CFR = 3.6 (>= 3.0) 或 存續 = 1.1s (< 2.0s)
        m1 = await svc.evaluate_spoofing_risk(
            ticker="NVDA",
            current_price=125.0,
            target_price=120.0,
            tick_data={"cancel_to_fill_ratio": 3.6, "depth_persistence_seconds": 1.1},
        )
        assert m1.regime == "SPOOF_HUNT_DETECTED"
        assert m1.anti_hunt_downward_offset_pct == 0.004
        # 120.0 * (1 - 0.004) = 119.52
        assert m1.adjusted_target_price == 119.52

        # 2. PHANTOM_LIQUIDITY_WARNING: 2.0 <= CFR < 3.0
        m2 = await svc.evaluate_spoofing_risk(
            ticker="V",
            current_price=280.0,
            target_price=275.0,
            tick_data={"cancel_to_fill_ratio": 2.4, "depth_persistence_seconds": 3.0},
        )
        assert m2.regime == "PHANTOM_LIQUIDITY_WARNING"
        assert m2.anti_hunt_downward_offset_pct == 0.002
        # 275.0 * (1 - 0.002) = 274.45
        assert m2.adjusted_target_price == 274.45

        # 3. CLEAN_ORDER_FLOW: CFR < 2.0, 存續 >= 2.0s
        m3 = await svc.evaluate_spoofing_risk(
            ticker="COP",
            current_price=118.0,
            target_price=115.0,
            tick_data={"cancel_to_fill_ratio": 1.2, "depth_persistence_seconds": 6.5},
        )
        assert m3.regime == "CLEAN_ORDER_FLOW"
        assert m3.anti_hunt_downward_offset_pct == 0.0
        assert m3.adjusted_target_price == 115.0


@pytest.mark.asyncio
async def test_spoofing_detector_spread_fallback():
    """驗證無微觀 tick 數據時，從買賣價差推導微觀風險"""
    mkt = MagicMock()
    # 點差擴大 >= 0.25% (0.0030)
    mkt.get_quote = AsyncMock(return_value={"spread_pct": 0.0030, "price": 100.0})

    svc = MicrostructureSpoofingDetectorService(
        user_id="user_123",
        market_data_service=mkt,
    )

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        m = await svc.evaluate_spoofing_risk(
            ticker="TEST",
            current_price=100.0,
            target_price=98.0,
            tick_data=None,
        )
        assert m.regime == "SPOOF_HUNT_DETECTED"
        assert m.anti_hunt_downward_offset_pct == 0.004
        assert m.adjusted_target_price == round(98.0 * (1.0 - 0.004), 2)


def test_format_spoofing_report():
    """驗證反欺詐嗅探 Telegram 戰報排版"""
    svc = MicrostructureSpoofingDetectorService(user_id="user_123")
    metric = SpoofingMetric(
        ticker="NVDA",
        regime="SPOOF_HUNT_DETECTED",
        cancel_to_fill_ratio=3.5,
        depth_persistence_seconds=1.2,
        anti_hunt_downward_offset_pct=0.004,
        original_target_price=120.0,
        adjusted_target_price=119.52,
        rationale="做市商假單撤單誘多",
    )
    report = svc.format_spoofing_report([metric], channel="telegram")
    assert "盤中微觀獵殺與反欺詐訂單簿嗅探儀表" in report
    assert "NVDA" in report
    assert "SPOOF_HUNT_DETECTED" in report
    assert "-0.40%" in report
    assert "$119.52" in report


# ═══════════════════════════════════════════════════════════════════════════
# Part 3: StaggeredDipBuyingService Anti-Hunt Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_staggered_dip_buying_anti_hunt_plan_shift():
    """驗證階梯限價吸籌計畫整合微觀反獵殺向下平移"""
    from src.services.staggered_dip_buying_service import StaggeredDipBuyingService

    spoof_detector = MagicMock()
    spoof_metric = SpoofingMetric(
        ticker="NVDA",
        regime="SPOOF_HUNT_DETECTED",
        cancel_to_fill_ratio=3.5,
        depth_persistence_seconds=1.2,
        anti_hunt_downward_offset_pct=0.004,
        original_target_price=123.0,
        adjusted_target_price=122.51,
        rationale="偵測到獵殺假單",
    )
    spoof_detector.evaluate_spoofing_risk = AsyncMock(return_value=spoof_metric)
    spoof_detector.is_enabled = True

    svc = StaggeredDipBuyingService(
        user_id="user_123",
        spoofing_detector=spoof_detector,
    )

    plan = await svc.calculate_staggered_plan_for_ticker(
        ticker="NVDA",
        target_budget_usd=100.0,
        current_price=125.0,
    )

    assert plan.spoof_regime == "SPOOF_HUNT_DETECTED"
    assert plan.anti_hunt_offset_pct == 0.004
    assert len(plan.tiers) == 3
    # 驗證所有 Tier 都包含反獵殺平移說明，且保持單調遞減
    p1 = plan.tiers[0].target_price
    p2 = plan.tiers[1].target_price
    p3 = plan.tiers[2].target_price
    assert p1 > p2 > p3
    assert "[微觀反獵殺平移: -0.40% (SPOOF_HUNT_DETECTED)]" in plan.tiers[0].rationale


@pytest.mark.asyncio
async def test_staggered_dip_buying_stalking_with_anti_hunt():
    """驗證盤中追單改價時套用微觀反獵殺安全邊際"""
    from src.services.staggered_dip_buying_service import StaggeredDipBuyingService

    spoof_detector = MagicMock()
    # 模擬追單時偵測到假單，要求向下偏移 40 bps
    spoof_metric = SpoofingMetric(
        ticker="NVDA",
        regime="SPOOF_HUNT_DETECTED",
        cancel_to_fill_ratio=3.2,
        depth_persistence_seconds=1.5,
        anti_hunt_downward_offset_pct=0.004,
        original_target_price=124.0,
        adjusted_target_price=123.50,
        rationale="追單時獵殺防護",
    )
    spoof_detector.evaluate_spoofing_risk = AsyncMock(return_value=spoof_metric)
    spoof_detector.is_enabled = True

    mkt = MagicMock()
    mkt.get_quote = AsyncMock(return_value={"last": 125.0, "price": 125.0})
    mkt.get_history_df = MagicMock(return_value=pd.DataFrame({"Open": [124.0]}))

    svc = StaggeredDipBuyingService(
        user_id="user_123",
        market_data_service=mkt,
        spoofing_detector=spoof_detector,
    )

    pending_orders = [
        {
            "ticker": "NVDA",
            "tier_number": 1,
            "limit_price": 121.0,  # 原始掛單
            "discount_pct": 0.032,
            "shares": 0.5,
            "order_id": "ord_pending_1",
            "status": "PENDING",
            "is_cross_sector_injected": False,
        }
    ]

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(pending_orders)
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        repriced_res = await svc.stalk_and_reprice_pending_orders()
        assert repriced_res["status"] == "success"
        assert repriced_res["repriced_count"] == 1
        rep = repriced_res["orders"][0]
        assert rep["ticker"] == "NVDA"
        # 價格向上貼近，但經過了反獵殺向下偏移
        assert rep["spoof_regime"] == "SPOOF_HUNT_DETECTED"
        assert rep["anti_hunt_offset_pct"] == 0.004
        assert rep["limit_price"] > 121.0


# ═══════════════════════════════════════════════════════════════════════════
# Part 4: ConversationRouter Direct 0-LLM Command Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_conversation_router_harvest_and_spoof_commands():
    """驗證對話路由器 0-LLM /harvest 與 /spoof 指令直通"""
    from src.services.conversation_router import ConversationRouter

    router = ConversationRouter()

    # 1. 驗證 exact_keywords 匹配
    assert router._is_system_command("/harvest") is True
    assert router._is_system_command("/rebalance") is True
    assert router._is_system_command("/recirculate") is True
    assert router._is_system_command("/收割") is True
    assert router._is_system_command("/spoof") is True
    assert router._is_system_command("/antihunt") is True
    assert router._is_system_command("/orderbook") is True
    assert router._is_system_command("/假單") is True

    # 2. 測試 /harvest 執行
    with patch("src.services.broker_factory.BrokerFactory.get_broker") as mock_gb:
        mock_broker = MagicMock()
        mock_broker.get_positions = AsyncMock(return_value=[
            {"symbol": "V", "quantity": 10.0, "current_price": 280.0, "average_entry_price": 250.0}
        ])
        mock_account = MagicMock()
        mock_account.total_equity = 1685.0
        mock_broker.get_account = AsyncMock(return_value=mock_account)
        mock_gb.return_value = mock_broker

        with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.setex = AsyncMock()
            mock_get_redis.return_value = mock_redis

            resp = await router._handle_system_command(
                adapter=MagicMock(),
                channel_user_id="tg_123",
                text="/harvest",
                resolved_user_id="user_123",
            )
            assert resp is not None
            assert "跨板塊注入標的動態收割與利差回流儀表" in resp

    # 3. 測試 /spoof 執行 (當日無掛單時走預設焦點標的展示)
    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # 無活躍階梯單
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        resp_spoof = await router._handle_system_command(
            adapter=MagicMock(),
            channel_user_id="tg_123",
            text="/spoof",
            resolved_user_id="user_123",
        )
        assert resp_spoof is not None
        assert "盤中微觀獵殺與反欺詐訂單簿嗅探儀表" in resp_spoof
        assert "NVDA" in resp_spoof
