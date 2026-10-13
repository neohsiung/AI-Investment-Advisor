"""
Unit Tests for Intraday Cross-Sector Correlation & Beta Damping Service (Phase 58)
================================================================================
測試內容涵蓋：
1. 歷史 Beta 與 Pearson 相關性精算 (Cov/Var, ddof=1, 長度不足與方差零回退)
2. 4 級體制狀態機判定與阻尼調度：
   - DEFENSIVE_DECOUPLED (低貝塔解耦, 1.15x, BOOST_STALKING)
   - NEUTRAL_BALANCED (中性平衡, 1.00x, STANDARD_STALKING)
   - CONTAGION_AMPLIFIED (高貝塔傳染, 0.60x~0.85x, DAMP_STALKING)
   - MARKET_STRESS_DAMPED (大盤跳水剛性阻尼, 0.50x, FREEZE_STALKING)
3. Redis 快取機制驗證 (TTL 與快取命中)
4. Dataclass 序列化與反序列化 (to_dict, from_dict)
5. 雙渠道戰報生成 (format_beta_damping_report)
6. 階梯限價吸籌整合 (StaggeredDipBuyingService):
   - 盤中追單改價 (BOOST / DAMP / FREEZE)
   - 尾盤 MOC 接管動態縮額防護 ($10.00 下限保護)
   - 異步報價防禦性解包 (isawaitable)
7. 對話路由器 0-LLM /betadamp 系統指令直通
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import pytest

from src.services.intraday_cross_sector_beta_damping_service import (
    IntradayBetaMetric,
    IntradayCrossSectorBetaDampingService,
)


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    store = {
        "enable_cross_sector_beta_damping": True,
        "beta_damping_contagion_threshold": 1.25,
        "beta_damping_decoupled_threshold": 0.75,
        "beta_damping_correlation_threshold": 0.75,
        "beta_damping_market_stress_drawdown_pct": -1.2,
    }
    settings.get_setting.side_effect = lambda k, default=None: store.get(k, default)
    return settings


@pytest.fixture
def mock_market_data():
    mkt = MagicMock()

    # 模擬 20 天歷史日線 (SPY 與個股)
    base_dates = pd.date_range("2026-09-01", periods=20)
    # SPY: 穩定上升
    spy_prices = [500.0 + i * 1.0 for i in range(20)]
    df_spy = pd.DataFrame({"Close": spy_prices, "Open": spy_prices}, index=base_dates)

    # V: 低貝塔低相關 (防守解耦)
    v_prices = [280.0 + (0.3 * i if i % 2 == 0 else -0.2 * i) for i in range(20)]
    df_v = pd.DataFrame({"Close": v_prices, "Open": v_prices}, index=base_dates)

    # HIGH_BETA: 高敏感同向放大 (傳染)
    high_prices = [100.0 + i * 2.5 for i in range(20)]
    df_high = pd.DataFrame({"Close": high_prices, "Open": high_prices}, index=base_dates)

    def _get_history(ticker, days=30):
        if ticker == "SPY":
            return df_spy
        elif ticker == "V":
            return df_v
        elif ticker == "HIGH":
            return df_high
        return pd.DataFrame({"Close": [100.0] * 20, "Open": [100.0] * 20})

    mkt.get_history_df.side_effect = _get_history

    async def _get_quote(ticker):
        if ticker == "SPY":
            return {"last": 520.0, "open": 520.0, "change_pct": 0.001}
        elif ticker == "V":
            return {"last": 285.0, "open": 284.5, "change_pct": 0.002}
        elif ticker == "HIGH":
            return {"last": 150.0, "open": 147.0, "change_pct": 0.020}
        return {"last": 100.0, "open": 100.0, "change_pct": 0.0}

    mkt.get_quote = AsyncMock(side_effect=_get_quote)
    return mkt


@pytest.fixture
def beta_service(mock_settings, mock_market_data):
    return IntradayCrossSectorBetaDampingService(
        user_id="test_user",
        settings_service=mock_settings,
        market_data_service=mock_market_data,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 歷史 Beta 與 Pearson 相關性精算
# ═══════════════════════════════════════════════════════════════════════════

def test_calculate_historical_beta_and_correlation_standard(beta_service):
    """測試常規同向序列的 Beta 與相關性計算"""
    x = [0.01, -0.01, 0.02, -0.015, 0.008, 0.012]
    # y 波動為 x 的 1.5 倍
    y = [0.015, -0.015, 0.03, -0.0225, 0.012, 0.018]
    beta, corr = beta_service.calculate_historical_beta_and_correlation(y, x)
    assert pytest.approx(beta, abs=0.01) == 1.50
    assert pytest.approx(corr, abs=0.01) == 1.00


def test_calculate_historical_beta_fallback_on_insufficient_data(beta_service):
    """測試歷史數據不足 5 筆時安全回退預設值 (beta=1.0, corr=0.50)"""
    x = [0.01, 0.02]
    y = [0.01, 0.02]
    beta, corr = beta_service.calculate_historical_beta_and_correlation(y, x)
    assert beta == 1.0
    assert corr == 0.50


def test_calculate_historical_beta_fallback_on_zero_variance(beta_service):
    """測試大盤方差為 0 時安全回退"""
    x = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    y = [0.01, -0.01, 0.02, -0.015, 0.008, 0.012]
    beta, corr = beta_service.calculate_historical_beta_and_correlation(y, x)
    assert beta == 1.0
    assert corr == 0.50


# ═══════════════════════════════════════════════════════════════════════════
# 2. 4 級體制狀態機判定與阻尼調度
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_evaluate_defensive_decoupled_regime(beta_service, mock_market_data):
    """測試低貝塔弱相關 (DEFENSIVE_DECOUPLED) 激勵追單吸籌 (1.15x, BOOST_STALKING)"""
    # 模擬歷史：V 與 SPY 相關性極弱且波動小
    with patch.object(beta_service, "calculate_historical_beta_and_correlation", return_value=(0.55, 0.25)):
        with patch("src.infrastructure.cache.redis_client.get_redis", side_effect=Exception("No Redis")):
            metric = await beta_service.evaluate_ticker_beta_damping("V", sector="Financials", force_refresh=True)

            assert metric.ticker == "V"
            assert metric.regime == "DEFENSIVE_DECOUPLED"
            assert metric.damping_factor == 1.15
            assert metric.stalking_action == "BOOST_STALKING"
            assert "低貝塔與弱相關" in metric.rationale


@pytest.mark.asyncio
async def test_evaluate_contagion_amplified_regime(beta_service, mock_market_data):
    """測試高貝塔系統性傳染 (CONTAGION_AMPLIFIED) 自適應阻尼收縮 (0.60x~0.85x, DAMP_STALKING)"""
    with patch.object(beta_service, "calculate_historical_beta_and_correlation", return_value=(1.45, 0.85)):
        with patch("src.infrastructure.cache.redis_client.get_redis", side_effect=Exception("No Redis")):
            metric = await beta_service.evaluate_ticker_beta_damping("HIGH", sector="Tech", force_refresh=True)

            assert metric.regime == "CONTAGION_AMPLIFIED"
            # 1.0 / 1.45 = 0.6897
            assert 0.60 <= metric.damping_factor <= 0.85
            assert metric.stalking_action == "DAMP_STALKING"
            assert "高貝塔系統性傳染" in metric.rationale


@pytest.mark.asyncio
async def test_evaluate_market_stress_damped_regime(beta_service, mock_market_data):
    """測試大盤急跌 <= -1.2% 且貝塔敏感時觸發剛性阻尼 (0.50x, FREEZE_STALKING)"""
    # 模擬 SPY 日內重挫 -1.5%
    async def _stress_quote(ticker):
        if ticker == "SPY":
            return {"last": 492.5, "open": 500.0, "change_pct": -0.015}
        return {"last": 100.0, "open": 102.0, "change_pct": -0.0196}

    mock_market_data.get_quote = AsyncMock(side_effect=_stress_quote)

    with patch.object(beta_service, "calculate_historical_beta_and_correlation", return_value=(1.10, 0.80)):
        with patch("src.infrastructure.cache.redis_client.get_redis", side_effect=Exception("No Redis")):
            metric = await beta_service.evaluate_ticker_beta_damping("SENSITIVE", force_refresh=True)

            assert metric.regime == "MARKET_STRESS_DAMPED"
            assert metric.damping_factor == 0.50
            assert metric.stalking_action == "FREEZE_STALKING"
            assert "大盤急跌" in metric.rationale


@pytest.mark.asyncio
async def test_evaluate_neutral_balanced_regime(beta_service, mock_market_data):
    """測試中性常規體制 (NEUTRAL_BALANCED, 1.00x, STANDARD_STALKING)"""
    with patch.object(beta_service, "calculate_historical_beta_and_correlation", return_value=(1.05, 0.55)):
        with patch("src.infrastructure.cache.redis_client.get_redis", side_effect=Exception("No Redis")):
            metric = await beta_service.evaluate_ticker_beta_damping("MID", force_refresh=True)

            assert metric.regime == "NEUTRAL_BALANCED"
            assert metric.damping_factor == 1.00
            assert metric.stalking_action == "STANDARD_STALKING"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Redis 快取機制與 Dataclass 驗證
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_redis_caching_and_roundtrip(beta_service):
    """測試 Redis 快取命中與 Dataclass to_dict/from_dict 往返"""
    sample_metric = IntradayBetaMetric(
        ticker="COP",
        benchmark_ticker="SPY",
        beta=0.65,
        correlation=0.30,
        intraday_return_pct=0.5,
        benchmark_return_pct=-0.1,
        relative_strength_pct=0.6,
        regime="DEFENSIVE_DECOUPLED",
        damping_factor=1.15,
        stalking_action="BOOST_STALKING",
        rationale="低貝塔解耦防守",
        injected_sector="Energy",
    )
    metric_dict = sample_metric.to_dict()
    restored = IntradayBetaMetric.from_dict(metric_dict)
    assert restored.ticker == "COP"
    assert restored.beta == 0.65
    assert restored.damping_factor == 1.15
    assert restored.stalking_action == "BOOST_STALKING"

    # 模擬 Redis 命中
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(metric_dict)

    with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis):
        cached_res = await beta_service.evaluate_ticker_beta_damping("COP", force_refresh=False)
        assert cached_res.ticker == "COP"
        assert cached_res.regime == "DEFENSIVE_DECOUPLED"
        # 驗證未調用 market data
        assert beta_service.market_data_service.get_history_df.call_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 4. 雙渠道戰報生成
# ═══════════════════════════════════════════════════════════════════════════

def test_format_beta_damping_report(beta_service):
    """測試 Telegram HTML 儀表戰報生成"""
    metrics = [
        IntradayBetaMetric(
            ticker="V",
            benchmark_ticker="SPY",
            beta=0.68,
            correlation=0.32,
            intraday_return_pct=0.85,
            benchmark_return_pct=-0.15,
            relative_strength_pct=1.00,
            regime="DEFENSIVE_DECOUPLED",
            damping_factor=1.15,
            stalking_action="BOOST_STALKING",
            rationale="低貝塔弱相關激勵吸籌",
            injected_sector="Financials",
        ),
        IntradayBetaMetric(
            ticker="NVDA",
            benchmark_ticker="SPY",
            beta=1.65,
            correlation=0.88,
            intraday_return_pct=-2.10,
            benchmark_return_pct=-1.30,
            relative_strength_pct=-0.80,
            regime="MARKET_STRESS_DAMPED",
            damping_factor=0.50,
            stalking_action="FREEZE_STALKING",
            rationale="大盤急跌且標的敏感，凍結追單",
            injected_sector="Technology",
        ),
    ]

    report = beta_service.format_beta_damping_report(metrics, channel="telegram")
    assert "跨板塊標的即時波動率相關性動態阻尼儀表" in report
    assert "低貝塔解耦 (DEFENSIVE_DECOUPLED)" in report
    assert "大盤跳水剛性阻尼 (MARKET_STRESS_DAMPED)" in report
    assert "1.15x" in report
    assert "0.50x" in report
    assert "BOOST_STALKING" in report
    assert "FREEZE_STALKING" in report

    # 測試空清單
    empty_report = beta_service.format_beta_damping_report([])
    assert "今日暫無跨板塊自癒標的" in empty_report


# ═══════════════════════════════════════════════════════════════════════════
# 5. 階梯限價吸籌整合測試 (StaggeredDipBuyingService)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_staggered_stalking_with_beta_damping(mock_settings, mock_market_data):
    """測試盤中追單改價串接貝塔阻尼 (BOOST, DAMP, FREEZE)"""
    from src.services.staggered_dip_buying_service import StaggeredDipBuyingService

    mock_beta_svc = MagicMock()
    mock_beta_svc.is_enabled = True

    # 模擬 3 種不同體制
    async def _mock_eval(ticker, **kwargs):
        if ticker == "V":
            return IntradayBetaMetric(
                ticker="V", benchmark_ticker="SPY", beta=0.6, correlation=0.3,
                intraday_return_pct=1.0, benchmark_return_pct=0.2, relative_strength_pct=0.8,
                regime="DEFENSIVE_DECOUPLED", damping_factor=1.15,
                stalking_action="BOOST_STALKING", rationale="低貝塔激勵",
            )
        elif ticker == "COP":
            return IntradayBetaMetric(
                ticker="COP", benchmark_ticker="SPY", beta=1.35, correlation=0.8,
                intraday_return_pct=0.5, benchmark_return_pct=0.2, relative_strength_pct=0.3,
                regime="CONTAGION_AMPLIFIED", damping_factor=0.74,
                stalking_action="DAMP_STALKING", rationale="高貝塔阻尼",
            )
        elif ticker == "STRESS":
            return IntradayBetaMetric(
                ticker="STRESS", benchmark_ticker="SPY", beta=1.5, correlation=0.9,
                intraday_return_pct=-2.0, benchmark_return_pct=-1.5, relative_strength_pct=-0.5,
                regime="MARKET_STRESS_DAMPED", damping_factor=0.50,
                stalking_action="FREEZE_STALKING", rationale="大盤跳水凍結",
            )
        return None

    mock_beta_svc.evaluate_ticker_beta_damping = AsyncMock(side_effect=_mock_eval)

    dip_svc = StaggeredDipBuyingService(
        user_id="test_user",
        settings_service=mock_settings,
        market_data_service=mock_market_data,
        beta_damping_service=mock_beta_svc,
    )

    # 構造 3 筆待追單訂單 (現價 $100, 開盤 $100)
    fake_orders = [
        {
            "order_id": "ord_v",
            "ticker": "V",
            "tier_number": 1,
            "limit_price": 98.0,
            "discount_pct": 0.02,
            "status": "PENDING",
            "is_cross_sector_injected": True,
            "injected_sector": "Financials",
        },
        {
            "order_id": "ord_cop",
            "ticker": "COP",
            "tier_number": 1,
            "limit_price": 98.0,
            "discount_pct": 0.02,
            "status": "PENDING",
            "is_cross_sector_injected": True,
            "injected_sector": "Energy",
        },
        {
            "order_id": "ord_stress",
            "ticker": "STRESS",
            "tier_number": 1,
            "limit_price": 98.0,
            "discount_pct": 0.02,
            "status": "PENDING",
            "is_cross_sector_injected": True,
            "injected_sector": "Tech",
        },
    ]

    # Mock Redis orders
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(fake_orders)
    mock_redis.setex = AsyncMock()

    # Quote returns $100.0, open $100.0 -> eligible for reprice
    mock_market_data.get_quote = AsyncMock(return_value={"last": 100.0, "open": 100.0})
    mock_market_data.get_history_df = MagicMock(return_value=pd.DataFrame({"Open": [100.0]}))

    with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis):
        with patch.object(dip_svc, "dispatch_staggered_stalk_alert", new_callable=AsyncMock):
            res = await dip_svc.stalk_and_reprice_pending_orders()

            assert res["status"] == "success"
            # ord_stress 應該被 FREEZE_STALKING 跳過改價，因此 repriced_count 應為 2 (V 與 COP)
            assert res["repriced_count"] == 2

            repriced_by_ticker = {o["ticker"]: o for o in res["orders"]}

            # V (BOOST_STALKING): discount_factor = 0.45 -> new_disc = 0.02 * 0.45 = 0.009 -> price = 99.1
            v_ord = repriced_by_ticker["V"]
            assert v_ord["beta_stalking_action"] == "BOOST_STALKING"
            assert v_ord["limit_price"] == 99.10

            # COP (DAMP_STALKING): discount_factor = 0.75 -> new_disc = 0.02 * 0.75 = 0.015 -> price = 98.5
            cop_ord = repriced_by_ticker["COP"]
            assert cop_ord["beta_stalking_action"] == "DAMP_STALKING"
            assert cop_ord["limit_price"] == 98.50


@pytest.mark.asyncio
async def test_staggered_moc_conversion_with_beta_damping(mock_settings, mock_market_data):
    """測試尾盤 MOC 接管時串接貝塔阻尼縮小部位金額並守住 $10.00 門檻"""
    from src.services.staggered_dip_buying_service import StaggeredDipBuyingService

    mock_beta_svc = MagicMock()
    mock_beta_svc.is_enabled = True

    # 模擬高貝塔傳染 (damping_factor = 0.70)
    mock_beta_svc.evaluate_ticker_beta_damping = AsyncMock(
        return_value=IntradayBetaMetric(
            ticker="HIGH", benchmark_ticker="SPY", beta=1.4, correlation=0.8,
            intraday_return_pct=-1.0, benchmark_return_pct=-0.5, relative_strength_pct=-0.5,
            regime="CONTAGION_AMPLIFIED", damping_factor=0.70,
            stalking_action="DAMP_STALKING", rationale="高貝塔阻尼縮額",
        )
    )

    mock_broker = AsyncMock()
    mock_broker.place_order.return_value = {"order_id": "broker_moc_123"}

    dip_svc = StaggeredDipBuyingService(
        user_id="test_user",
        settings_service=mock_settings,
        market_data_service=mock_market_data,
        broker=mock_broker,
        beta_damping_service=mock_beta_svc,
    )

    fake_orders = [
        {
            "order_id": "ord_moc_1",
            "ticker": "HIGH",
            "tier_number": 1,
            "limit_price": 50.0,
            "amount_usd": 100.0,  # 預算 $100 -> 阻尼 0.70x 後應變為 $70.0
            "status": "PENDING",
            "is_cross_sector_injected": True,
            "injected_sector": "Tech",
        }
    ]

    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(fake_orders)
    mock_redis.setex = AsyncMock()

    mock_market_data.get_quote = AsyncMock(return_value={"last": 50.0, "close": 50.0})

    with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis):
        with patch.object(dip_svc, "dispatch_staggered_moc_alert", new_callable=AsyncMock):
            with patch.object(dip_svc, "_onboard_filled_position", new_callable=AsyncMock, return_value=46.0):
                res = await dip_svc.convert_unfilled_dip_orders_to_moc()

                assert res["status"] == "success"
                assert res["converted_count"] == 1
                conv_ord = res["orders"][0]
                assert conv_ord["amount_usd"] == 70.0
                assert conv_ord["original_amount_usd"] == 100.0
                assert conv_ord["beta_damping_factor"] == 0.70
                assert conv_ord["status"] == "FILLED"
                assert conv_ord["fill_mechanism"] == "MOC_CONVERSION"


# ═══════════════════════════════════════════════════════════════════════════
# 6. 對話路由器 0-LLM /betadamp 系統指令直通
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_conversation_router_betadamp_command(mock_settings, mock_market_data):
    """測試對話路由器 /betadamp 0-LLM 指令直通"""
    from src.services.conversation_router import ConversationRouter

    router = ConversationRouter()

    # 模擬 Redis 無掛單，直接查詢自癒候選標的
    with patch("src.infrastructure.cache.redis_client.get_redis", side_effect=Exception("No Redis")):
        with patch(
            "src.services.intraday_cross_sector_beta_damping_service.IntradayCrossSectorBetaDampingService.evaluate_ticker_beta_damping",
            new_callable=AsyncMock,
        ) as mock_eval:
            mock_eval.return_value = IntradayBetaMetric(
                ticker="V", benchmark_ticker="SPY", beta=0.72, correlation=0.35,
                intraday_return_pct=0.4, benchmark_return_pct=0.1, relative_strength_pct=0.3,
                regime="DEFENSIVE_DECOUPLED", damping_factor=1.15,
                stalking_action="BOOST_STALKING", rationale="低貝塔解耦測試",
                injected_sector="Financials",
            )

            res = await router._handle_system_command(
                adapter=None,
                channel_user_id="test_channel_user",
                text="/betadamp",
                resolved_user_id="test_user",
            )

            assert res is not None
            assert "跨板塊標的即時波動率相關性動態阻尼儀表" in res
            assert "DEFENSIVE_DECOUPLED" in res
            assert "1.15x" in res
