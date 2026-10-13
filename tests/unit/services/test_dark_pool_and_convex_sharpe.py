"""
Unit Tests for Cross-Market Dark Pool Pricing & Convex Sharpe Frontier Optimizer (Phase 60)
=============================================================================================
測試涵蓋：
1. DarkPoolTickerSummary 序列化與反序列化 (to_dict, from_dict)
2. CrossMarketDarkPoolPricingService 4 級暗池體制判定：
   - INSTITUTIONAL_ACCUMULATION (Buy Ratio >= 65%, 錨定 Block VWAP)
   - BLOCK_DISTRIBUTION_FLUSH (Sell Ratio >= 65%, 向下防禦平移 50~80 bps)
   - BALANCED_DARK_LIQUIDITY (買賣均衡, 0 bps 平移)
   - INSUFFICIENT_DARK_PRINTS (缺乏大宗印痕, 維持基準)
3. 報價特徵代理推導 (Proxy synthesis via market_data_service)
4. Redis 快取機制 (讀取與過期寫入)
5. 雙渠道暗池戰報生成 (format_dark_pool_report)
6. ConvexOptimalWeight 與 ConvexOptimizationResult 序列化/反序列化 (to_dict, from_dict)
7. 有界單體投影 (Bounded Simplex Projection) 數理性質驗證：
   - 總和 ∑ w_i = 1.0
   - 上界 0 <= w_i <= cap
   - 自適應鬆弛 cap = max(cap, 1/N)
8. MultiFactorConvexSharpeOptimizerService 梯度上升收斂、夏普最大化與起投門檻 ($10.00 USD)
9. 雙渠道夏普邊界戰報生成 (format_convex_sharpe_report)
10. StaggeredDipBuyingService 整合暗池底價校準與出貨防禦平移
11. BatchCashDeploymentService 整合利差回流最優夏普邊界二次規劃
12. ConversationRouter 0-LLM /darkpool 與 /convex 指令直通
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from src.services.cross_market_dark_pool_pricing_service import (
    CrossMarketDarkPoolPricingService,
    DarkPoolTickerSummary,
)
from src.services.multi_factor_convex_sharpe_optimizer_service import (
    ConvexOptimizationResult,
    ConvexOptimalWeight,
    MultiFactorConvexSharpeOptimizerService,
)


# ═══════════════════════════════════════════════════════════════════════════
# Part 1: Phase 60A - CrossMarketDarkPoolPricingService Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_dark_pool_summary_serialization():
    """驗證暗池指標資料模型之序列化與反序列化一致性"""
    summary = DarkPoolTickerSummary(
        ticker="NVDA",
        regime="INSTITUTIONAL_ACCUMULATION",
        block_vwap=124.50,
        reference_price=125.00,
        total_dark_volume=50000.0,
        total_dark_notional_usd=6225000.0,
        dark_pool_buy_ratio=0.7250,
        dark_pool_discount_pct=-0.0040,
        recommended_limit_shift_pct=-0.0040,
        calibrated_anchor_price=124.50,
        rationale="大宗折價吸籌",
    )
    d = summary.to_dict()
    assert d["ticker"] == "NVDA"
    assert d["regime"] == "INSTITUTIONAL_ACCUMULATION"
    assert d["block_vwap"] == 124.50
    assert d["dark_pool_buy_ratio"] == 0.7250
    assert d["calibrated_anchor_price"] == 124.50

    restored = DarkPoolTickerSummary.from_dict(d)
    assert restored.ticker == "NVDA"
    assert restored.regime == "INSTITUTIONAL_ACCUMULATION"
    assert restored.block_vwap == 124.50
    assert restored.dark_pool_buy_ratio == 0.7250
    assert restored.calibrated_anchor_price == 124.50


@pytest.mark.asyncio
async def test_dark_pool_pricing_service_disabled():
    """驗證暗池定價服務停用時之安全回退"""
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "enable_dark_pool_pricing": False,
    }.get(k, default)

    svc = CrossMarketDarkPoolPricingService(user_id="test_user", settings_service=settings)
    assert svc.is_enabled is False

    summary = await svc.evaluate_dark_pool_activity("NVDA", reference_price=125.0)
    assert summary.regime == "BALANCED_DARK_LIQUIDITY"
    assert summary.calibrated_anchor_price == 125.0
    assert "已停用" in summary.rationale


@pytest.mark.asyncio
async def test_dark_pool_regime_institutional_accumulation():
    """驗證機構暗池吸籌體制 (Buy Ratio >= 65%) 錨定 Block VWAP"""
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "enable_dark_pool_pricing": True,
        "dark_pool_accumulation_threshold": 0.65,
        "dark_pool_distribution_threshold": 0.65,
        "dark_pool_max_limit_shift_pct": 0.008,
    }.get(k, default)

    svc = CrossMarketDarkPoolPricingService(user_id="test_user", settings_service=settings)

    # 模擬大宗印痕：70% 買方，均價 124.00 (折價於 125.00)
    prints = [
        {"size": 7000, "price": 124.00, "side": "BUY"},
        {"size": 3000, "price": 124.00, "side": "SELL"},
    ]

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        summary = await svc.evaluate_dark_pool_activity("NVDA", reference_price=125.0, dark_prints=prints)

        assert summary.regime == "INSTITUTIONAL_ACCUMULATION"
        assert summary.dark_pool_buy_ratio == 0.70
        assert summary.block_vwap == 124.00
        assert summary.calibrated_anchor_price == 124.00
        assert "搶先截擊真實主力底價" in summary.rationale
        assert mock_redis.setex.called


@pytest.mark.asyncio
async def test_dark_pool_regime_distribution_flush():
    """驗證機構暗池出貨拋售體制 (Sell Ratio >= 65%) 向下平移防禦"""
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "enable_dark_pool_pricing": True,
        "dark_pool_accumulation_threshold": 0.65,
        "dark_pool_distribution_threshold": 0.65,
        "dark_pool_max_limit_shift_pct": 0.008,
    }.get(k, default)

    svc = CrossMarketDarkPoolPricingService(user_id="test_user", settings_service=settings)

    # 模擬大宗印痕：80% 賣方 (出貨拋售)
    prints = [
        {"size": 2000, "price": 123.00, "side": "BUY"},
        {"size": 8000, "price": 123.00, "side": "SELL"},
    ]

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        summary = await svc.evaluate_dark_pool_activity("NVDA", reference_price=125.0, dark_prints=prints)

        assert summary.regime == "BLOCK_DISTRIBUTION_FLUSH"
        assert summary.dark_pool_buy_ratio == 0.20
        assert summary.recommended_limit_shift_pct < 0
        assert summary.calibrated_anchor_price < 125.00
        assert "規避承接拋售潮" in summary.rationale


@pytest.mark.asyncio
async def test_dark_pool_regime_balanced_and_insufficient():
    """驗證暗池平衡流動性與缺乏印痕體制"""
    svc = CrossMarketDarkPoolPricingService(user_id="test_user")

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        # 1. 平衡流動性 (50% 買方)
        balanced_prints = [
            {"size": 5000, "price": 125.00, "side": "BUY"},
            {"size": 5000, "price": 125.00, "side": "SELL"},
        ]
        s_balanced = await svc.evaluate_dark_pool_activity("NVDA", reference_price=125.0, dark_prints=balanced_prints)
        assert s_balanced.regime == "BALANCED_DARK_LIQUIDITY"
        assert s_balanced.calibrated_anchor_price == 125.00

        # 2. 缺乏印痕 (無 prints 且無報價)
        s_insufficient = await svc.evaluate_dark_pool_activity("NVDA", reference_price=125.0, dark_prints=[])
        assert s_insufficient.regime == "INSUFFICIENT_DARK_PRINTS"
        assert s_insufficient.calibrated_anchor_price == 125.00


@pytest.mark.asyncio
async def test_dark_pool_redis_cache_hit():
    """驗證暗池 Redis 快取命中與自適應點位重算"""
    svc = CrossMarketDarkPoolPricingService(user_id="test_user")

    cached_data = {
        "ticker": "NVDA",
        "regime": "INSTITUTIONAL_ACCUMULATION",
        "block_vwap": 123.50,
        "reference_price": 125.00,
        "total_dark_volume": 10000.0,
        "total_dark_notional_usd": 1235000.0,
        "dark_pool_buy_ratio": 0.70,
        "dark_pool_discount_pct": -0.012,
        "recommended_limit_shift_pct": -0.008,
        "calibrated_anchor_price": 123.50,
        "rationale": "快取吸籌",
        "updated_at": "2026-10-13T10:00:00Z",
    }

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(cached_data)
        mock_get_redis.return_value = mock_redis

        summary = await svc.evaluate_dark_pool_activity("NVDA", reference_price=126.0)
        assert summary.regime == "INSTITUTIONAL_ACCUMULATION"
        assert summary.block_vwap == 123.50
        assert summary.calibrated_anchor_price == 123.50


def test_dark_pool_report_formatting():
    """驗證雙渠道暗池戰報產出"""
    svc = CrossMarketDarkPoolPricingService(user_id="test_user")

    # 1. 空清單
    empty_rep = svc.format_dark_pool_report([])
    assert "跨市場暗池大宗換手與隔夜掛單校準儀表" in empty_rep
    assert "目前暫無暗池大宗換手監控數據" in empty_rep

    # 2. 有數據清單
    s = DarkPoolTickerSummary(
        ticker="NVDA",
        regime="INSTITUTIONAL_ACCUMULATION",
        block_vwap=124.20,
        reference_price=125.00,
        total_dark_volume=20000.0,
        total_dark_notional_usd=2484000.0,
        dark_pool_buy_ratio=0.75,
        dark_pool_discount_pct=-0.0064,
        recommended_limit_shift_pct=-0.0064,
        calibrated_anchor_price=124.20,
        rationale="主力吸籌校準測試",
    )
    rep = svc.format_dark_pool_report([s])
    assert "NVDA" in rep
    assert "機構吸籌換手" in rep
    assert "$124.20" in rep
    assert "75.0%" in rep


# ═══════════════════════════════════════════════════════════════════════════
# Part 2: Phase 60B - MultiFactorConvexSharpeOptimizerService Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_convex_optimization_result_serialization():
    """驗證最優夏普二次規劃資料模型序列化與反序列化"""
    w1 = ConvexOptimalWeight(
        ticker="NVDA",
        target_weight=0.25,
        allocated_usd=350.0,
        expected_return_annual=0.155,
        marginal_sharpe_contribution=0.45,
    )
    res = ConvexOptimizationResult(
        expected_portfolio_return=0.142,
        portfolio_volatility=0.185,
        portfolio_sharpe_ratio=0.524,
        weights=[w1],
        recirculated_cash_allocated_usd=350.0,
        optimization_status="OPTIMAL",
    )
    d = res.to_dict()
    assert d["expected_portfolio_return"] == 0.142
    assert d["portfolio_sharpe_ratio"] == 0.524
    assert len(d["weights"]) == 1
    assert d["weights"][0]["ticker"] == "NVDA"

    restored = ConvexOptimizationResult.from_dict(d)
    assert restored.expected_portfolio_return == 0.142
    assert restored.portfolio_sharpe_ratio == 0.524
    assert len(restored.weights) == 1
    assert restored.weights[0].ticker == "NVDA"


def test_bounded_simplex_projection_mathematical_properties():
    """驗證有界單體投影之數學保證 (和為 1.0，嚴格介於 0 與 cap 之間)"""
    # 測試向量：5 維
    v = np.array([2.5, 1.2, -0.5, 0.8, 3.0])
    cap = 0.25

    w = MultiFactorConvexSharpeOptimizerService.project_bounded_simplex(v, cap=cap)

    # 1. 總和必須嚴格為 1.0 (容差 1e-5)
    assert abs(np.sum(w) - 1.0) < 1e-5

    # 2. 每個權重均在 [0, cap] 內
    assert np.all(w >= -1e-6)
    assert np.all(w <= cap + 1e-6)

    # 3. 測試 N=2 時，cap=0.25 不可行邊界自動鬆弛至 0.50
    v2 = np.array([1.0, 2.0])
    w2 = MultiFactorConvexSharpeOptimizerService.project_bounded_simplex(v2, cap=0.25)
    assert abs(np.sum(w2) - 1.0) < 1e-5
    assert np.all(w2 <= 0.50001)


@pytest.mark.asyncio
async def test_convex_sharpe_optimizer_disabled():
    """驗證二次規劃停用時安全回退均分配置"""
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None: {
        "enable_convex_sharpe_optimization": False,
    }.get(k, default)

    svc = MultiFactorConvexSharpeOptimizerService(user_id="test_user", settings_service=settings)
    assert svc.is_enabled is False

    res = await svc.optimize_recirculated_capital_allocation(
        candidate_tickers=["NVDA", "V", "COP"],
        available_capital_usd=300.0,
    )
    assert res.optimization_status == "FALLBACK_EQUAL_WEIGHT"
    assert len(res.weights) == 3
    for w in res.weights:
        assert round(w.target_weight, 2) == 0.33
        assert w.allocated_usd == 100.0


@pytest.mark.asyncio
async def test_convex_sharpe_optimizer_convergence():
    """驗證投影梯度上升法求解最優夏普邊界收斂性與起投門檻分配"""
    svc = MultiFactorConvexSharpeOptimizerService(user_id="test_user")

    candidates = ["NVDA", "TSM", "AAPL", "V", "COP"]
    total_capital = 500.0

    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        res = await svc.optimize_recirculated_capital_allocation(
            candidate_tickers=candidates,
            available_capital_usd=total_capital,
        )

        assert res.optimization_status in ("OPTIMAL", "APPROXIMATE_CONVERGED")
        assert res.portfolio_sharpe_ratio > 0.0
        assert len(res.weights) == 5

        # 驗證總權重和約為 1.0
        total_w = sum(w.target_weight for w in res.weights)
        assert abs(total_w - 1.0) < 0.01

        # 驗證單一標的上限約束 (cap = 0.25)
        for w in res.weights:
            assert w.target_weight <= 0.2501
            # 每筆分配金額若大於 0 需符合起投門檻 >= $10.00
            if w.allocated_usd > 0:
                assert w.allocated_usd >= 10.0

        # 總分配額應等於可用資本 (在數美分捨入容差內)
        assert abs(res.recirculated_cash_allocated_usd - total_capital) < 1.0
        assert mock_redis.setex.called


def test_convex_sharpe_report_formatting():
    """驗證夏普邊界戰報產出"""
    svc = MultiFactorConvexSharpeOptimizerService(user_id="test_user")

    w1 = ConvexOptimalWeight(
        ticker="NVDA",
        target_weight=0.25,
        allocated_usd=250.0,
        expected_return_annual=0.155,
        marginal_sharpe_contribution=0.42,
    )
    w2 = ConvexOptimalWeight(
        ticker="V",
        target_weight=0.20,
        allocated_usd=200.0,
        expected_return_annual=0.125,
        marginal_sharpe_contribution=0.35,
    )
    res = ConvexOptimizationResult(
        expected_portfolio_return=0.141,
        portfolio_volatility=0.178,
        portfolio_sharpe_ratio=0.539,
        weights=[w1, w2],
        recirculated_cash_allocated_usd=450.0,
        optimization_status="OPTIMAL",
    )

    rep = svc.format_convex_sharpe_report(res)
    assert "利差回流資本最優夏普邊界二次規劃儀表" in rep
    assert "0.54" in rep or "0.539" in rep or "0.5" in rep
    assert "NVDA" in rep
    assert "25.0%" in rep
    assert "V" in rep


# ═══════════════════════════════════════════════════════════════════════════
# Part 3: Integration Tests (StaggeredDipBuying & BatchCashDeployment)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_staggered_dip_buying_dark_pool_calibration():
    """驗證 StaggeredDipBuyingService 整合暗池底價校準與拋售平移"""
    from src.services.staggered_dip_buying_service import StaggeredDipBuyingService

    mock_dark_svc = MagicMock()
    mock_dark_svc.is_enabled = True

    # 1. 測試吸籌體制：Block VWAP 校準 Tier 1
    mock_dark_svc.evaluate_dark_pool_activity = AsyncMock(return_value=DarkPoolTickerSummary(
        ticker="NVDA",
        regime="INSTITUTIONAL_ACCUMULATION",
        block_vwap=123.50,
        reference_price=125.00,
        total_dark_volume=10000.0,
        total_dark_notional_usd=1235000.0,
        dark_pool_buy_ratio=0.75,
        dark_pool_discount_pct=-0.012,
        recommended_limit_shift_pct=-0.008,
        calibrated_anchor_price=123.50,
        rationale="機構大宗吸籌校準",
    ))

    dip_svc = StaggeredDipBuyingService(
        user_id="test_user",
        dark_pool_service=mock_dark_svc,
    )

    plan = await dip_svc.calculate_staggered_plan_for_ticker("NVDA", target_budget_usd=100.0, current_price=125.0)
    assert plan.dark_pool_regime == "INSTITUTIONAL_ACCUMULATION"
    # Tier 1 應被校準為 123.50
    assert plan.tiers[0].target_price == 123.50
    assert "暗池大宗底價校準" in plan.tiers[0].rationale

    # 2. 測試出貨拋售體制：所有 Tier 防禦性向下平移
    mock_dark_svc.evaluate_dark_pool_activity = AsyncMock(return_value=DarkPoolTickerSummary(
        ticker="NVDA",
        regime="BLOCK_DISTRIBUTION_FLUSH",
        block_vwap=123.00,
        reference_price=125.00,
        total_dark_volume=10000.0,
        total_dark_notional_usd=1230000.0,
        dark_pool_buy_ratio=0.15,
        dark_pool_discount_pct=-0.016,
        recommended_limit_shift_pct=-0.006,  # 下移 60 bps
        calibrated_anchor_price=124.25,
        rationale="機構出貨拋售",
    ))

    plan_flush = await dip_svc.calculate_staggered_plan_for_ticker("NVDA", target_budget_usd=100.0, current_price=125.0)
    assert plan_flush.dark_pool_regime == "BLOCK_DISTRIBUTION_FLUSH"
    assert plan_flush.dark_pool_shift_pct == -0.006
    for t in plan_flush.tiers:
        assert "暗池拋售防禦平移" in t.rationale


@pytest.mark.asyncio
async def test_batch_cash_deployment_convex_sharpe_integration():
    """驗證 BatchCashDeploymentService 整合最優夏普邊界二次規劃"""
    from src.services.batch_cash_deployment_service import BatchCashDeploymentService

    mock_convex_svc = MagicMock()
    mock_convex_svc.is_enabled = True

    opt_result = ConvexOptimizationResult(
        expected_portfolio_return=0.145,
        portfolio_volatility=0.18,
        portfolio_sharpe_ratio=0.555,
        weights=[
            ConvexOptimalWeight("NVDA", 0.25, 250.0, 0.155, 0.45),
            ConvexOptimalWeight("TSM", 0.20, 200.0, 0.125, 0.35),
            ConvexOptimalWeight("AAPL", 0.15, 150.0, 0.115, 0.25),
        ],
        recirculated_cash_allocated_usd=600.0,
        optimization_status="OPTIMAL",
    )
    mock_convex_svc.optimize_recirculated_capital_allocation = AsyncMock(return_value=opt_result)

    batch_svc = BatchCashDeploymentService(
        user_id="test_user",
        convex_optimizer=mock_convex_svc,
    )
    # 關閉或 mock 外部遠端守衛避免網路 I/O
    batch_svc.blackout_guard = MagicMock()
    batch_svc.blackout_guard.evaluate_candidate = AsyncMock(return_value=MagicMock(is_blackout=False))
    batch_svc.blackout_guard.get_upcoming_calendar_summary = AsyncMock(return_value={})
    batch_svc.risk_gateway = None
    batch_svc.jump_guard = None
    batch_svc.event_graph = None

    with patch.object(batch_svc, "get_portfolio_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = {
            "deployable_cash": 1000.0,
            "total_equity": 1685.0,
            "available_cash": 1200.0,
            "required_reserve_usd": 337.0,
        }
        with patch.object(batch_svc, "_get_broker", new_callable=AsyncMock) as mock_broker:
            mock_b = MagicMock()
            mock_b.get_positions = AsyncMock(return_value=[])
            mock_broker.return_value = mock_b

            plan = await batch_svc.get_deployment_plan(batch_number=1)
            assert plan["convex_sharpe_summary"] is not None
            assert plan["convex_sharpe_summary"]["portfolio_sharpe_ratio"] == 0.555
            # 檢查 items 標記有最優夏普權重
            for it in plan["items"]:
                if it["ticker"] == "NVDA":
                    assert it.get("convex_optimal_weight") == 0.25
                elif it["ticker"] == "TSM":
                    assert it.get("convex_optimal_weight") == 0.20


# ═══════════════════════════════════════════════════════════════════════════
# Part 4: ConversationRouter 0-LLM Command Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_conversation_router_darkpool_and_convex_commands():
    """驗證對話路由器 0-LLM /darkpool 與 /convex 指令直通"""
    from src.services.conversation_router import ConversationRouter

    router = ConversationRouter()

    # 1. 驗證 exact_keywords
    for kw in ["/darkpool", "/prints", "/blocktrades", "/暗池", "/大宗", "/暗池定價"]:
        assert router._is_system_command(kw) is True

    for kw in ["/convex", "/sharpe", "/qp", "/mvo", "/凸規劃", "/夏普邊界", "/最優配置"]:
        assert router._is_system_command(kw) is True

    # 2. 測試 /darkpool 執行 (無掛單走預設展示)
    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        resp_dp = await router._handle_system_command(
            adapter=MagicMock(),
            channel_user_id="tg_123",
            text="/darkpool",
            resolved_user_id="user_123",
        )
        assert resp_dp is not None
        assert "跨市場暗池大宗換手與隔夜掛單校準儀表" in resp_dp
        assert "NVDA" in resp_dp

    # 3. 測試 /convex 執行
    with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        resp_cv = await router._handle_system_command(
            adapter=MagicMock(),
            channel_user_id="tg_123",
            text="/convex",
            resolved_user_id="user_123",
        )
        assert resp_cv is not None
        assert "利差回流資本最優夏普邊界二次規劃儀表" in resp_cv
        assert "邊界夏普比率" in resp_cv
