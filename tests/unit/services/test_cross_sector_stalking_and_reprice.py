"""
Unit Tests for Cross-Sector Momentum Stalking & MOC Prioritization (Phase 54-55)
================================================================================
驗證跨板塊注入標的（如 V、COP、ECL）在主力支撐階梯吸籌架構下的生命週期閉環：
1. TickerStaggeredPlan 與批次生成正確傳遞跨板塊注入標記 (is_cross_sector_injected, injected_sector)。
2. execute_staggered_dip_deployment 將注入標記完整持久化寫入 Redis 掛單記錄。
3. stalk_and_reprice_pending_orders (14:00 EST) 優先排序並對跨板塊注入標的施加自適應積極追單改價。
4. convert_unfilled_dip_orders_to_moc (15:50 EST) 優先挑選跨板塊注入標的進行 MOC 撮合，完成持倉交接與 ATR 停損掛載。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import pytest

from src.services.staggered_dip_buying_service import (
    StaggeredDipBuyingService,
    TickerStaggeredPlan,
    StaggeredTierPlan,
)


@pytest.fixture
def mock_redis():
    r = MagicMock()
    stored = {}

    async def async_get(key):
        return stored.get(key)

    async def async_setex(key, ttl, val):
        stored[key] = val
        return True

    r.get = AsyncMock(side_effect=async_get)
    r.setex = AsyncMock(side_effect=async_setex)
    r._stored = stored
    return r


@pytest.fixture
def mock_settings():
    s = MagicMock()
    settings_dict = {
        "enable_staggered_dip_buying": True,
        "enable_staggered_order_stalking": True,
        "enable_staggered_moc_conversion": True,
        "staggered_tier1_allocation_pct": 0.40,
        "staggered_tier2_allocation_pct": 0.35,
        "staggered_tier3_allocation_pct": 0.25,
        "staggered_tier1_dip_pct": 0.008,
        "staggered_tier2_dip_pct": 0.020,
        "staggered_tier3_dip_pct": 0.038,
    }
    s.get_setting.side_effect = lambda k, default=None: settings_dict.get(k, default)
    return s


@pytest.mark.asyncio
async def test_calculate_staggered_plan_with_cross_sector_injected(mock_settings):
    """驗證單檔標的階梯計畫正確封裝跨板塊注入屬性與 to_dict 輸出。"""
    risk_gw = AsyncMock()
    risk_res = MagicMock()
    risk_res.allowed = True
    risk_res.severity = "NORMAL"
    risk_res.primary_blocker = None
    risk_res.reasons = []
    risk_gw.evaluate_trade_risk.return_value = risk_res

    svc = StaggeredDipBuyingService(
        user_id="test_user",
        settings_service=mock_settings,
        risk_gateway=risk_gw,
    )

    plan = await svc.calculate_staggered_plan_for_ticker(
        ticker="V",
        target_budget_usd=86.45,
        current_price=280.0,
        is_cross_sector_injected=True,
        injected_sector="Financial",
    )

    assert plan.ticker == "V"
    assert plan.is_cross_sector_injected is True
    assert plan.injected_sector == "Financial"
    assert len(plan.tiers) == 3

    d = plan.to_dict()
    assert d["is_cross_sector_injected"] is True
    assert d["injected_sector"] == "Financial"


@pytest.mark.asyncio
async def test_execute_staggered_dip_deployment_persists_cross_sector_fields(mock_redis, mock_settings):
    """驗證階梯限價下單執行時，Redis 中的掛單記錄正確包含跨板塊標記。"""
    risk_gw = AsyncMock()
    risk_res = MagicMock()
    risk_res.allowed = True
    risk_res.severity = "NORMAL"
    risk_res.primary_blocker = None
    risk_res.reasons = []
    risk_gw.evaluate_trade_risk.return_value = risk_res

    svc = StaggeredDipBuyingService(
        user_id="test_user",
        settings_service=mock_settings,
        risk_gateway=risk_gw,
    )

    mock_batch_svc = MagicMock()
    mock_batch_svc.get_active_batch_number = AsyncMock(return_value=2)
    mock_batch_svc.get_deployment_plan = AsyncMock(return_value={
        "portfolio_status": {"deployable_cash": 300.0},
        "items": [
            {
                "ticker": "V",
                "amount_usd": 100.0,
                "is_cross_sector_injected": True,
                "injected_sector": "Financial",
            }
        ]
    })

    with patch("src.infrastructure.cache.redis_client.get_redis", AsyncMock(return_value=mock_redis)), \
         patch("src.services.batch_cash_deployment_service.BatchCashDeploymentService", return_value=mock_batch_svc), \
         patch.object(svc, "dispatch_staggered_deployment_alert", AsyncMock(return_value=True)):

        res = await svc.execute_staggered_dip_deployment(batch_number=2)
        assert res["success"] is True
        assert len(res["orders"]) == 3

        for ord_rec in res["orders"]:
            assert ord_rec["ticker"] == "V"
            assert ord_rec["is_cross_sector_injected"] is True
            assert ord_rec["injected_sector"] == "Financial"


@pytest.mark.asyncio
async def test_stalk_and_reprice_prioritizes_cross_sector_injected(mock_redis, mock_settings):
    """驗證 14:00 盤中追單改價時，跨板塊標的具備優先排序與更積極的貼近限價。"""
    svc = StaggeredDipBuyingService(user_id="test_user", settings_service=mock_settings)

    # Redis 中有 1 筆科技股 (NVDA) 與 1 筆跨板塊注入金融股 (V)
    orders = [
        {
            "ticker": "NVDA",
            "tier_number": 1,
            "tier_name": "Tier 1 (輕度回踩)",
            "limit_price": 100.0,
            "amount_usd": 40.0,
            "discount_pct": 0.015,
            "status": "PENDING",
            "is_cross_sector_injected": False,
            "injected_sector": None,
        },
        {
            "ticker": "V",
            "tier_number": 1,
            "tier_name": "Tier 1 (首檔回踩)",
            "limit_price": 275.0,
            "amount_usd": 86.45,
            "discount_pct": 0.018,
            "status": "PENDING",
            "is_cross_sector_injected": True,
            "injected_sector": "Financial",
        },
    ]

    import pytz
    from datetime import datetime
    now_ny = datetime.now(pytz.timezone("US/Eastern"))
    date_str = now_ny.strftime("%Y-%m-%d")
    r_key = f"{svc.REDIS_KEY_PREFIX}:test_user:{date_str}"
    mock_redis._stored[r_key] = json.dumps(orders)

    # 行情模擬：NVDA 與 V 均微幅上漲
    mkt_mock = MagicMock()
    def get_quote_mock(sym):
        if sym == "V":
            return {"last": 280.0, "close": 280.0}
        return {"last": 102.0, "close": 102.0}
    mkt_mock.get_quote.side_effect = get_quote_mock

    dates = pd.date_range("2026-10-01", periods=5, freq="D")
    df_v = pd.DataFrame({"Open": [278, 278, 279, 279, 280], "Close": [279, 279, 280, 280, 280]}, index=dates)
    df_nvda = pd.DataFrame({"Open": [101, 101, 101, 101, 102], "Close": [101, 101, 102, 102, 102]}, index=dates)

    def get_history_mock(sym, days=5):
        return df_v if sym == "V" else df_nvda
    mkt_mock.get_history_df.side_effect = get_history_mock

    with patch("src.infrastructure.cache.redis_client.get_redis", AsyncMock(return_value=mock_redis)), \
         patch.object(svc, "_get_market_data_service", AsyncMock(return_value=mkt_mock)), \
         patch.object(svc, "dispatch_staggered_stalk_alert", AsyncMock(return_value=True)) as mock_alert:

        res = await svc.stalk_and_reprice_pending_orders()
        assert res["status"] == "success"
        assert res["repriced_count"] == 2

        # 驗證跨板塊標的 V 排在前面追單
        first_repriced = res["orders"][0]
        assert first_repriced["ticker"] == "V"
        assert first_repriced["limit_price"] > 275.0
        assert first_repriced["is_stalked"] is True

        # 驗證推播呼叫
        mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_convert_unfilled_dip_orders_to_moc_prioritizes_cross_sector(mock_redis, mock_settings):
    """驗證 15:50 尾盤 MOC 接管時，跨板塊標的優先於科技股被撮合成交以分散 HHI。"""
    svc = StaggeredDipBuyingService(user_id="test_user", settings_service=mock_settings)

    # 3 筆未成交單：2 筆科技股 (NVDA, TSM)，1 筆跨板塊金融股 (V)
    orders = [
        {
            "ticker": "NVDA",
            "tier_number": 1,
            "tier_name": "Tier 1",
            "limit_price": 100.0,
            "amount_usd": 35.0,
            "status": "PENDING",
            "is_cross_sector_injected": False,
            "injected_sector": None,
        },
        {
            "ticker": "TSM",
            "tier_number": 1,
            "tier_name": "Tier 1",
            "limit_price": 180.0,
            "amount_usd": 40.0,
            "status": "PENDING",
            "is_cross_sector_injected": False,
            "injected_sector": None,
        },
        {
            "ticker": "V",
            "tier_number": 1,
            "tier_name": "Tier 1",
            "limit_price": 275.0,
            "amount_usd": 86.45,
            "status": "PENDING",
            "is_cross_sector_injected": True,
            "injected_sector": "Financial",
        },
    ]

    import pytz
    from datetime import datetime
    now_ny = datetime.now(pytz.timezone("US/Eastern"))
    date_str = now_ny.strftime("%Y-%m-%d")
    r_key = f"{svc.REDIS_KEY_PREFIX}:test_user:{date_str}"
    mock_redis._stored[r_key] = json.dumps(orders)

    mkt_mock = MagicMock()
    mkt_mock.get_quote.return_value = {"last": 282.0, "close": 282.0}

    with patch("src.infrastructure.cache.redis_client.get_redis", AsyncMock(return_value=mock_redis)), \
         patch.object(svc, "_get_market_data_service", AsyncMock(return_value=mkt_mock)), \
         patch.object(svc, "_get_broker", AsyncMock(return_value=None)), \
         patch.object(svc, "_onboard_filled_position", AsyncMock(return_value=270.0)) as mock_onboard, \
         patch.object(svc, "dispatch_staggered_moc_alert", AsyncMock(return_value=True)):

        # 尾盤限制每次最多接管 2 筆
        res = await svc.convert_unfilled_dip_orders_to_moc()
        assert res["status"] == "success"
        assert res["converted_count"] == 2

        converted_tickers = [o["ticker"] for o in res["orders"]]
        # 跨板塊標的 V 必須排在第一順位被接管！
        assert converted_tickers[0] == "V"

        v_order = res["orders"][0]
        assert v_order["status"] == "FILLED"
        assert v_order["fill_mechanism"] == "MOC_CONVERSION"
        assert v_order["fill_price"] == 282.0
        assert v_order["initial_stop_price"] == 270.0

        # 驗證 _onboard_filled_position 呼叫參數完整正確 (5 個參數)
        mock_onboard.assert_any_await(
            ticker="V",
            fill_price=282.0,
            amount_usd=86.45,
            tier_name="Tier 1",
            discount_pct=0.0,
        )
