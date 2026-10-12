"""
Unit Tests for VPIN & Kyle's Lambda Microstructure Toxicity Guard Service (Phase 34)
===================================================================================
測試成交量時鐘切桶 (Volume Buckets)、Bulk Volume Classification (BVC)、
滾動 VPIN 機率失衡、Kyle's Lambda (λ) 價格衝擊模型、SlippageGuard 整合、
BatchCashDeployment 批次建倉知情交易阻斷、以及 0-LLM 對話路由器指令。
"""
import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.vpin_toxicity_guard_service import (
    VPINToxicityGuardService,
    VPINToxicityRegime,
    VolumeBucketState,
    KylesLambdaMetrics,
    TickerVPINAssessment,
    PortfolioVPINSummary,
)
from src.services.slippage_guard_service import SlippageGuardService, SlippageGuardDecision
from src.services.batch_cash_deployment_service import BatchCashDeploymentService
from src.services.conversation_router import ConversationRouter


class DummySettingsService:
    def __init__(self, settings: dict = None):
        self.settings = settings or {}
        self.settings_repo = self

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def get_all_settings(self):
        return self.settings

    def get(self, user_id: str, key: str, default=None):
        return self.settings.get(key, default)


class TestVPINCoreAlgorithms:
    """測試 BVC、Volume Bucketing、VPIN 與 Kyle's Lambda 核心數學演算法"""

    def test_classify_bvc_balanced(self):
        """對稱波動下，BVC 買賣量比例應趨近 50:50"""
        price_changes = [0.10, -0.10, 0.12, -0.12, 0.05, -0.05]
        volumes = [1000.0] * 6
        vb, vs = VPINToxicityGuardService.classify_bvc(price_changes, volumes)

        assert len(vb) == 6
        assert len(vs) == 6
        tot_buy = sum(vb)
        tot_sell = sum(vs)
        assert abs(tot_buy - tot_sell) < 500.0  # 買賣量平衡
        for b, s in zip(vb, vs):
            assert abs((b + s) - 1000.0) < 1e-4

    def test_classify_bvc_trending_toxic(self):
        """連續單向大漲時，BVC 買方量顯著佔據絕對優勢"""
        price_changes = [0.50, 0.60, 0.45, 0.70, 0.55]
        volumes = [5000.0] * 5
        vb, vs = VPINToxicityGuardService.classify_bvc(price_changes, volumes)

        tot_buy = sum(vb)
        tot_sell = sum(vs)
        # 由於價格單向推升，買單失衡顯著
        assert tot_buy > tot_sell * 1.5

    def test_slice_into_buckets(self):
        """驗證切桶邏輯與桶容量填滿機制"""
        buy_vols = [600.0, 800.0, 700.0]
        sell_vols = [400.0, 200.0, 300.0]
        prices = [100.0, 101.0, 102.0]
        bucket_size = 1000.0

        buckets = VPINToxicityGuardService.slice_into_buckets(
            buy_vols, sell_vols, prices, bucket_size
        )

        # 總成交量 = 3000，每桶 1000，應剛好完整切出 3 個桶
        completed = [b for b in buckets if b.is_complete]
        assert len(completed) >= 2
        for b in completed:
            assert abs(b.total_volume - bucket_size) < 1e-4
            assert b.is_complete is True

    def test_compute_vpin_balanced_vs_toxic(self):
        """驗證平衡流與極端單向流之 VPIN 指標計算"""
        # 平衡桶流
        balanced_buckets = [
            VolumeBucketState(bucket_index=i, target_volume=1000.0, buy_volume=520.0, sell_volume=480.0, is_complete=True)
            for i in range(10)
        ]
        vpin_bal = VPINToxicityGuardService.compute_vpin(balanced_buckets)
        assert vpin_bal < 0.10  # 40 / 1000 = 0.04

        # 極端毒性單向流
        toxic_buckets = [
            VolumeBucketState(bucket_index=i, target_volume=1000.0, buy_volume=900.0, sell_volume=100.0, is_complete=True)
            for i in range(10)
        ]
        vpin_tox = VPINToxicityGuardService.compute_vpin(toxic_buckets)
        assert vpin_tox >= 0.70  # 800 / 1000 = 0.80

    def test_compute_kyles_lambda_positive_impact(self):
        """驗證 Kyle's Lambda 價格衝擊斜率估計與 R^2 計算"""
        buckets = [
            VolumeBucketState(
                bucket_index=i, target_volume=1000.0,
                buy_volume=500.0 + (i * 40.0), sell_volume=500.0 - (i * 40.0),
                start_price=100.0, end_price=100.0 + (i * 0.15),
                is_complete=True,
            )
            for i in range(10)
        ]
        kyle = VPINToxicityGuardService.compute_kyles_lambda(buckets)
        assert kyle.sample_buckets_count == 10
        assert kyle.lambda_coeff > 0.0  # 正向價格衝擊
        assert kyle.r_squared > 0.0
        assert kyle.informed_trader_ratio > 0.0

    def test_compute_kyles_lambda_zero_variance_safe(self):
        """當訂單失衡完全無變異時，Kyle's Lambda 優雅退化回 0.0，不拋除以零異常"""
        buckets = [
            VolumeBucketState(
                bucket_index=i, target_volume=1000.0,
                buy_volume=500.0, sell_volume=500.0,
                start_price=100.0, end_price=100.0,
                is_complete=True,
            )
            for i in range(5)
        ]
        kyle = VPINToxicityGuardService.compute_kyles_lambda(buckets)
        assert kyle.lambda_coeff == 0.0
        assert kyle.r_squared == 0.0


class TestVPINToxicityGuardService:
    """測試 VPINToxicityGuardService 的全生命週期與體制判定"""

    @pytest.mark.asyncio
    async def test_evaluate_ticker_disabled(self):
        """當服務設定為關閉時，回傳 NORMAL 放行且無毒性"""
        settings = DummySettingsService({"enable_vpin_toxicity_guard": False})
        svc = VPINToxicityGuardService(settings_service=settings)

        res = await svc.evaluate_ticker("NVDA")
        assert res.regime == VPINToxicityRegime.NORMAL
        assert res.is_toxic is False
        assert res.recommended_action == "PROCEED"
        assert res.slippage_boost == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_ticker_fail_open_synthetic(self):
        """當完全無外部市場數據時，Fail-Open 合成基準應回傳健康 NORMAL 狀態"""
        settings = DummySettingsService({"enable_vpin_toxicity_guard": True})
        svc = VPINToxicityGuardService(settings_service=settings)

        res = await svc.evaluate_ticker("TSM")
        assert res.regime == VPINToxicityRegime.NORMAL
        assert res.is_toxic is False
        assert 0.10 <= res.vpin <= 0.25
        assert res.recommended_action == "PROCEED"
        assert res.details.get("source") == "fail_open_synthetic_baseline"

    @pytest.mark.asyncio
    async def test_ingest_bars_and_evaluate_toxic_regime(self):
        """批次攝取單向劇烈推升 Bars，觸發 TOXIC 體制與暫緩決策"""
        svc = VPINToxicityGuardService()
        # 構造 40 根劇烈推升且高成交量的 Bar
        bars = [
            {"open": 100.0 + i, "close": 100.8 + i, "high": 101.0 + i, "low": 100.0 + i, "volume": 50000.0}
            for i in range(40)
        ]
        assessment = svc.ingest_bars("NVDA", bars, adv=100000.0)

        assert assessment.symbol == "NVDA"
        assert assessment.vpin >= 0.40
        assert assessment.regime == VPINToxicityRegime.TOXIC
        assert assessment.is_toxic is True
        assert assessment.recommended_action == "DEFER"
        assert assessment.execution_pace_minutes == 5
        assert assessment.slippage_boost == 1.0

    @pytest.mark.asyncio
    async def test_ingest_trade_ticks(self):
        """攝取 Trade Ticks 進入時鐘桶並驗證桶計數遞增"""
        svc = VPINToxicityGuardService()
        for i in range(25):
            svc.ingest_trade_tick("AAPL", price=150.0 + (i * 0.1), volume=2000.0, direction="BUY")

        assert "AAPL" in svc._completed_buckets_map
        completed = svc._completed_buckets_map["AAPL"]
        assert len(completed) >= 1

    @pytest.mark.asyncio
    async def test_portfolio_vpin_assessment(self):
        """測試全組合標的微觀結構毒性評估與市場體制"""
        svc = VPINToxicityGuardService()
        summary = await svc.get_portfolio_vpin_assessment(["NVDA", "AAPL", "MSFT"])

        assert isinstance(summary, PortfolioVPINSummary)
        assert len(summary.assessments) == 3
        assert "NVDA" in summary.assessments
        assert summary.overall_market_toxicity in ("BENIGN", "MODERATE", "ACUTE_TOXICITY")
        assert 0.0 <= summary.mean_vpin <= 1.0


class TestSlippageGuardVPINIntegration:
    """測試 SlippageGuardService 與 VPINToxicityGuardService 的前置閉環阻斷整合"""

    @pytest.mark.asyncio
    async def test_evaluate_trade_passes_when_vpin_normal(self):
        """VPIN 處於 NORMAL 體制時，SlippageGuard 順利放行"""
        mock_vpin = MagicMock()
        mock_vpin.is_enabled = True
        normal_eval = TickerVPINAssessment(
            symbol="NVDA",
            vpin=0.18,
            regime=VPINToxicityRegime.NORMAL,
            kyle_lambda=0.0001,
            kyle_metrics=KylesLambdaMetrics(0.0001, 0.1, 0.15, 50, 0.01, 1000.0),
            adv=1000000.0,
            bucket_size=20000.0,
            completed_buckets=50,
            is_toxic=False,
            recommended_action="PROCEED",
            execution_pace_minutes=0,
            slippage_boost=0.0,
        )
        mock_vpin.evaluate_ticker = AsyncMock(return_value=normal_eval)

        sg = SlippageGuardService(vpin_guard=mock_vpin)
        sg.is_opening_auction_window = MagicMock(return_value=(False, "常規時段"))
        sg.get_ticker_quote = AsyncMock(return_value={
            "bid": 100.0, "ask": 100.05, "mid": 100.025, "last": 100.02, "spread_pct": 0.0005
        })

        decision = await sg.evaluate_trade("NVDA", "BUY", amount_usd=100.0, check_opening_window=False)
        assert decision.passed is True
        assert decision.vpin == 0.18
        assert decision.recommended_action == "PROCEED"

    @pytest.mark.asyncio
    async def test_evaluate_trade_blocks_when_vpin_toxic(self):
        """VPIN 處於 TOXIC 體制 (>= 0.40) 時，SlippageGuard 觸發知情交易熔斷暫緩下單"""
        mock_vpin = MagicMock()
        mock_vpin.is_enabled = True
        toxic_eval = TickerVPINAssessment(
            symbol="NVDA",
            vpin=0.48,
            regime=VPINToxicityRegime.TOXIC,
            kyle_lambda=0.00085,
            kyle_metrics=KylesLambdaMetrics(0.00085, 0.65, 0.32, 50, 0.05, 500.0),
            adv=1000000.0,
            bucket_size=20000.0,
            completed_buckets=50,
            is_toxic=True,
            recommended_action="DEFER",
            execution_pace_minutes=5,
            slippage_boost=1.0,
        )
        mock_vpin.evaluate_ticker = AsyncMock(return_value=toxic_eval)

        sg = SlippageGuardService(vpin_guard=mock_vpin)
        sg.is_opening_auction_window = MagicMock(return_value=(False, "常規時段"))
        sg.get_ticker_quote = AsyncMock(return_value={
            "bid": 100.0, "ask": 100.05, "mid": 100.025, "last": 100.02, "spread_pct": 0.0005
        })

        decision = await sg.evaluate_trade("NVDA", "BUY", amount_usd=100.0, check_opening_window=False)
        assert decision.passed is False
        assert decision.circuit_breaker_triggered is True
        assert "知情交易者訂單流毒性急遽升高" in decision.reason
        assert decision.recommended_action == "DEFER"
        assert decision.vpin == 0.48

    @pytest.mark.asyncio
    async def test_evaluate_trade_elevated_vpin_applies_boost(self):
        """VPIN 處於 ELEVATED 時，SlippageGuard 提高限價緩衝自適應保護乘數"""
        mock_vpin = MagicMock()
        mock_vpin.is_enabled = True
        elev_eval = TickerVPINAssessment(
            symbol="TSM",
            vpin=0.32,
            regime=VPINToxicityRegime.ELEVATED,
            kyle_lambda=0.0003,
            kyle_metrics=KylesLambdaMetrics(0.0003, 0.25, 0.24, 50, 0.02, 800.0),
            adv=1000000.0,
            bucket_size=20000.0,
            completed_buckets=50,
            is_toxic=False,
            recommended_action="THROTTLE",
            execution_pace_minutes=3,
            slippage_boost=0.5,
        )
        mock_vpin.evaluate_ticker = AsyncMock(return_value=elev_eval)

        sg = SlippageGuardService(vpin_guard=mock_vpin)
        sg.is_opening_auction_window = MagicMock(return_value=(False, "常規時段"))
        sg.get_ticker_quote = AsyncMock(return_value={
            "bid": 150.0, "ask": 150.10, "mid": 150.05, "last": 150.05, "spread_pct": 0.0006
        })

        decision = await sg.evaluate_trade("TSM", "BUY", amount_usd=100.0, check_opening_window=False)
        assert decision.passed is True
        # 自適應限價單上限應反映包含 boost 的保護溢價
        assert decision.adaptive_limit_price >= 150.10


class TestBatchCashDeploymentVPINIntegration:
    """測試 BatchCashDeploymentService 整合 VPIN 毒性指標與執行阻斷"""

    @pytest.mark.asyncio
    async def test_get_deployment_plan_includes_vpin_summary(self):
        """驗證 get_deployment_plan 包含 vpin_summary 與標記"""
        broker = MagicMock()
        broker.get_positions = AsyncMock(return_value=[])
        account = MagicMock(total_equity=1700.0, available_cash=1000.0)
        broker.get_account = AsyncMock(return_value=account)

        deploy_svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=DummySettingsService({"enable_vpin_toxicity_guard": True}),
            broker=broker,
        )
        deploy_svc.get_portfolio_status = AsyncMock(return_value={
            "total_equity": 1700.0, "available_cash": 1000.0, "deployable_cash": 600.0,
            "required_reserve_usd": 340.0, "defensive_reserve_pct": 20.0,
        })
        plan = await deploy_svc.get_deployment_plan(batch_number=1)

        assert "vpin_summary" in plan
        assert isinstance(plan["vpin_summary"], dict)

    @pytest.mark.asyncio
    async def test_execute_batch_defers_vpin_toxic_candidate(self):
        """當候選標的觸發 VPIN 毒性熔斷時，標記為 vpin_toxicity_deferred 並保留批次"""
        broker = MagicMock()
        broker.get_positions = AsyncMock(return_value=[])
        account = MagicMock(total_equity=1700.0, available_cash=1000.0)
        broker.get_account = AsyncMock(return_value=account)

        deploy_svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=DummySettingsService({"enable_vpin_toxicity_guard": True}),
            broker=broker,
        )
        deploy_svc.get_portfolio_status = AsyncMock(return_value={
            "total_equity": 1700.0, "available_cash": 1000.0, "deployable_cash": 600.0,
            "required_reserve_usd": 340.0, "defensive_reserve_pct": 20.0,
        })
        deploy_svc.get_active_batch_number = AsyncMock(return_value=1)
        deploy_svc.get_deployment_plan = AsyncMock(return_value={
            "batch_number": 1,
            "can_execute": True,
            "total_batch_amount": 100.0,
            "status": {"deployable_cash": 500.0},
            "items": [
                {"ticker": "NVDA", "amount_usd": 100.0, "confidence_score": 0.85, "role": "alpha_leader", "rationale": "Alpha 1"}
            ],
        })
        deploy_svc.blackout_guard.evaluate_candidate = AsyncMock(return_value=MagicMock(is_blackout=False))

        # 模擬 SlippageGuard 回報 VPIN 毒性熔斷
        toxic_decision = SlippageGuardDecision(
            passed=False,
            reason="⚠️ 標的 NVDA 偵測到知情交易者訂單流毒性急遽升高 (VPIN: 48.0%, 體制: TOXIC)",
            circuit_breaker_triggered=True,
            vpin=0.48,
            kyle_lambda=0.0008,
            recommended_action="DEFER",
        )
        deploy_svc.slippage_guard.evaluate_trade = AsyncMock(return_value=toxic_decision)

        with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_r_factory:
            mock_r = AsyncMock()
            mock_r_factory.return_value = mock_r
            res = await deploy_svc.execute_batch(batch_number=1, force=False, enforce_market_hours=False)

        assert res["success"] is False
        trades = res.get("executed_trades", [])
        assert len(trades) == 1
        assert trades[0]["status"] == "vpin_toxicity_deferred"
        assert trades[0]["vpin"] == 0.48


class TestConversationRouterVPINCommand:
    """測試 ConversationRouter 對 /vpin 系統指令的解析與 HTML 報表卡片渲染"""

    def test_is_system_command_recognizes_vpin_aliases(self):
        """路由器應精確辨識 /vpin, /toxicity, /kyle, 毒性, 知情交易 等別名"""
        router = ConversationRouter()
        aliases = [
            "/vpin", "/toxicity", "/kyle", "/毒性",
            "vpin", "toxicity", "kyle", "毒性", "訂單流毒性", "微觀結構", "知情交易"
        ]
        for alias in aliases:
            assert router._is_system_command(alias) is True, f"Failed to recognize {alias}"

    @pytest.mark.asyncio
    async def test_handle_system_command_vpin_output(self):
        """調用 /vpin 應輸出包含 VPIN、Kyle's Lambda、α 比率與處置矩陣的 HTML 報表"""
        router = ConversationRouter()
        output = await router._handle_system_command(
            adapter=None,
            channel_user_id="U12345",
            text="/vpin",
            resolved_user_id="default_user",
        )

        assert output is not None
        assert "微觀結構訂單流毒性與知情交易者檢定報告" in output
        assert "VPIN" in output
        assert "Kyle's λ" in output
        assert "全市場微觀體制" in output
        assert "處置矩陣" in output
        assert "知情交易者比率 α" in output

    @pytest.mark.asyncio
    async def test_handle_system_command_guard_links_to_vpin(self):
        """/guard 指令輸出應包含導引至 /vpin 的提示連結"""
        router = ConversationRouter()
        output = await router._handle_system_command(
            adapter=None,
            channel_user_id="U12345",
            text="/guard",
            resolved_user_id="default_user",
        )

        assert output is not None
        assert "/vpin" in output
        assert "訂單流毒性" in output or "Kyle" in output
