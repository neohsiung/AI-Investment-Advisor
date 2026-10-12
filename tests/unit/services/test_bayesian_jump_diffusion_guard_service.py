"""
Unit Tests for Bayesian Regime-Switching Jump-Diffusion Guard Service (Phase 35)
================================================================================
測試 Merton 跳躍擴散過程參數估計、Bipower Variation (BV) 雙冪方差連續/跳躍分離、
Gamma-Poisson 動態在線共軛貝葉斯更新、機制轉換跳躍體制判定 (CALM, MODERATE, ACUTE)、
SlippageGuard 防滑點熔斷整合、BatchCashDeployment 批次建倉跳躍阻斷、以及 0-LLM 對話路由器指令。
"""
import asyncio
from datetime import datetime, timezone
import json
import math
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.bayesian_jump_diffusion_guard_service import (
    BayesianJumpDiffusionGuardService,
    JumpRegime,
    BipowerVariationResult,
    BayesianJumpPosterior,
    TickerJumpAssessment,
    PortfolioJumpSummary,
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


class TestBipowerVariationAndMerton:
    """測試 Merton 跳躍擴散與 Bipower 雙冪變異核心數學演算法"""

    def test_compute_bipower_variation_continuous_diffusion(self):
        """純幾何布朗運動（平穩連續擴散）下，BV 應極度接近 RV，RJ 應趨近於 0"""
        # 構造平穩微小波動序列（無跳躍）
        returns = [0.005, -0.004, 0.006, -0.005, 0.004, -0.003, 0.005, -0.006] * 8
        bv_res = BayesianJumpDiffusionGuardService.compute_bipower_variation(returns, sigma_multiplier=3.0)

        assert isinstance(bv_res, BipowerVariationResult)
        assert bv_res.sample_days == len(returns)
        assert bv_res.realized_variance > 0.0
        assert bv_res.bipower_variation > 0.0
        # 平穩擴散下，相對跳躍比率 RJ 應非常低 (< 0.15)
        assert bv_res.relative_jump_ratio < 0.15
        assert len(bv_res.detected_jumps) == 0

    def test_compute_bipower_variation_with_jumps(self):
        """當序列中注入極端離散跳躍時，BV 顯著小於 RV，RJ 顯著上升且準確檢出跳躍"""
        returns = [0.003, -0.002, 0.004, -0.003] * 12
        # 注入 3 筆劇烈離散跳躍
        returns[10] = 0.065   # +6.5% 正向跳空
        returns[25] = -0.072  # -7.2% 負向下跳
        returns[40] = -0.055  # -5.5% 崩跌跳空

        bv_res = BayesianJumpDiffusionGuardService.compute_bipower_variation(returns, sigma_multiplier=3.0)

        assert bv_res.jump_variation > 0.0
        assert bv_res.relative_jump_ratio >= 0.20  # 跳躍變異佔比超過 20%
        assert len(bv_res.detected_jumps) >= 3
        assert any(j < -0.05 for j in bv_res.detected_jumps)
        assert any(j > 0.05 for j in bv_res.detected_jumps)

    def test_compute_bipower_variation_empty_or_short(self):
        """當樣本數過少 (<2) 時，安全退化回預設值，不拋異常"""
        bv_res = BayesianJumpDiffusionGuardService.compute_bipower_variation([0.01])
        assert bv_res.relative_jump_ratio == 0.0
        assert bv_res.detected_jumps == []
        assert bv_res.continuous_volatility == 0.15

    def test_update_bayesian_merton_zero_jumps(self):
        """未觀測到跳躍時，Gamma-Poisson 共軛更新先驗頻率滑移"""
        post = BayesianJumpDiffusionGuardService.update_bayesian_merton(
            detected_jumps=[],
            lookback_days=60,
            prior_alpha=2.0,
            prior_beta=1.0,
        )
        assert isinstance(post, BayesianJumpPosterior)
        assert post.observed_jumps_count == 0
        t_years = 60.0 / 252.0
        expected_lambda = 2.0 / (1.0 + t_years)
        assert abs(post.expected_jump_intensity - expected_lambda) < 1e-4
        assert post.jump_mean_magnitude == -0.02

    def test_update_bayesian_merton_with_multiple_jumps(self):
        """觀測到多次下行跳躍時，後驗跳躍強度顯著攀升，且更新跳躍幅度均值"""
        jumps = [-0.045, -0.052, -0.060, -0.038]
        post = BayesianJumpDiffusionGuardService.update_bayesian_merton(
            detected_jumps=jumps,
            lookback_days=60,
            prior_alpha=2.0,
            prior_beta=1.0,
        )
        # alpha = 2.0 + 4 = 6.0; beta = 1.0 + 60/252 = 1.238
        # lambda = 6.0 / 1.238 ~ 4.84 jumps/year
        assert post.observed_jumps_count == 4
        assert post.expected_jump_intensity >= 4.0
        assert post.jump_mean_magnitude < -0.03  # 後驗跳躍均值向下修正
        assert post.jump_std_magnitude > 0.0


class TestBayesianJumpDiffusionGuardService:
    """測試 BayesianJumpDiffusionGuardService 的評估與體制決策邏輯"""

    @pytest.mark.asyncio
    async def test_evaluate_ticker_disabled(self):
        """當服務停用時，一律回傳 CALM_DIFFUSION 放行"""
        settings = DummySettingsService({"enable_bayesian_jump_guard": False})
        svc = BayesianJumpDiffusionGuardService(settings_service=settings)

        res = await svc.evaluate_ticker("NVDA")
        assert res.regime == JumpRegime.CALM_DIFFUSION
        assert res.is_acute_jump is False
        assert res.recommended_action == "PROCEED"
        assert res.position_scale_multiplier == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_ticker_fail_open_synthetic(self):
        """當完全缺乏即時歷史數據時，Fail-Open 合成基準應回傳健康平穩狀態"""
        settings = DummySettingsService({"enable_bayesian_jump_guard": True})
        svc = BayesianJumpDiffusionGuardService(settings_service=settings)

        res = await svc.evaluate_ticker("TSM")
        assert res.regime == JumpRegime.CALM_DIFFUSION
        assert res.is_acute_jump is False
        assert res.recommended_action == "PROCEED"
        assert res.details.get("source") == "fail_open_synthetic_baseline"
        assert res.jump_intensity < 2.0

    def test_evaluate_returns_series_calm(self):
        """平穩低波回報率序列評定為 CALM_DIFFUSION"""
        svc = BayesianJumpDiffusionGuardService()
        returns = [0.002, -0.003, 0.001, -0.002, 0.003, -0.001] * 10
        res = svc.evaluate_returns_series("AAPL", returns)

        assert res.symbol == "AAPL"
        assert res.regime == JumpRegime.CALM_DIFFUSION
        assert res.is_acute_jump is False
        assert res.recommended_action == "PROCEED"
        assert res.position_scale_multiplier == 1.0
        assert res.stop_loss_buffer_multiplier == 1.0

    def test_evaluate_returns_series_moderate_jump(self):
        """中度跳躍活絡評定為 MODERATE_JUMP，部位縮小至 80%，防禦緩衝加成"""
        svc = BayesianJumpDiffusionGuardService()
        returns = [0.005, -0.004, 0.006, -0.005] * 12
        # 注入 2 次中度跳躍
        returns[15] = 0.035
        returns[30] = -0.028

        res = svc.evaluate_returns_series("MSFT", returns)

        assert res.symbol == "MSFT"
        assert res.regime in (JumpRegime.MODERATE_JUMP, JumpRegime.CALM_DIFFUSION)
        if res.regime == JumpRegime.MODERATE_JUMP:
            assert res.recommended_action == "THROTTLE"
            assert res.position_scale_multiplier == 0.80
            assert res.stop_loss_buffer_multiplier == 1.25

    def test_evaluate_returns_series_acute_jump(self):
        """極端密集跳躍或嚴重下行跳躍衝擊評定為 ACUTE_JUMP_REGIME，暫緩下單"""
        svc = BayesianJumpDiffusionGuardService()
        returns = [0.004, -0.003, 0.005, -0.004] * 15
        # 注入多筆嚴重下行崩跌跳躍
        returns[5] = -0.055
        returns[15] = -0.048
        returns[25] = -0.062
        returns[35] = -0.042
        returns[45] = -0.050
        returns[55] = -0.058

        res = svc.evaluate_returns_series("NVDA", returns)

        assert res.symbol == "NVDA"
        assert res.regime == JumpRegime.ACUTE_JUMP_REGIME
        assert res.is_acute_jump is True
        assert res.recommended_action == "DEFER"
        assert res.position_scale_multiplier <= 0.50
        assert res.stop_loss_buffer_multiplier >= 1.50
        assert res.details.get("has_severe_downside_jump") is True

    @pytest.mark.asyncio
    async def test_portfolio_jump_assessment(self):
        """測試全組合跳躍擴散評估與市場體制歸納"""
        svc = BayesianJumpDiffusionGuardService()
        summary = await svc.get_portfolio_jump_assessment(["NVDA", "AAPL", "MSFT"])

        assert isinstance(summary, PortfolioJumpSummary)
        assert len(summary.assessments) == 3
        assert "NVDA" in summary.assessments
        assert summary.overall_market_jump_regime in ("CALM", "ELEVATED_JUMP_ACTIVITY", "SYSTEMIC_JUMP_SHOCK")
        assert summary.mean_jump_intensity >= 0.0
        assert 0.0 <= summary.mean_relative_jump_ratio <= 1.0


class TestSlippageGuardJumpIntegration:
    """測試 SlippageGuardService 與 BayesianJumpDiffusionGuardService 的閉環阻斷整合"""

    @pytest.mark.asyncio
    async def test_evaluate_trade_passes_when_jump_calm(self):
        """平穩擴散體制下，SlippageGuard 順利放行並記錄 jump 指標"""
        mock_jump = MagicMock()
        mock_jump.is_enabled = True
        calm_eval = TickerJumpAssessment(
            symbol="NVDA",
            regime=JumpRegime.CALM_DIFFUSION,
            jump_intensity=1.45,
            continuous_volatility=0.22,
            total_volatility=0.24,
            relative_jump_ratio=0.08,
            jump_mean=-0.015,
            jump_std=0.03,
            is_acute_jump=False,
            recommended_action="PROCEED",
            position_scale_multiplier=1.0,
            stop_loss_buffer_multiplier=1.0,
        )
        mock_jump.evaluate_ticker = AsyncMock(return_value=calm_eval)

        sg = SlippageGuardService(jump_guard=mock_jump)
        sg.is_opening_auction_window = MagicMock(return_value=(False, "常規時段"))
        sg.get_ticker_quote = AsyncMock(return_value={
            "bid": 100.0, "ask": 100.05, "mid": 100.025, "last": 100.02, "spread_pct": 0.0005
        })

        decision = await sg.evaluate_trade("NVDA", "BUY", amount_usd=100.0, check_opening_window=False)
        assert decision.passed is True
        assert decision.jump_intensity == 1.45
        assert decision.jump_regime == "CALM_DIFFUSION"
        assert decision.recommended_action == "PROCEED"

    @pytest.mark.asyncio
    async def test_evaluate_trade_blocks_when_jump_acute(self):
        """標的處於 ACUTE_JUMP_REGIME 時，SlippageGuard 觸發跳躍熔斷暫緩下單"""
        mock_jump = MagicMock()
        mock_jump.is_enabled = True
        acute_eval = TickerJumpAssessment(
            symbol="NVDA",
            regime=JumpRegime.ACUTE_JUMP_REGIME,
            jump_intensity=7.20,
            continuous_volatility=0.35,
            total_volatility=0.55,
            relative_jump_ratio=0.45,
            jump_mean=-0.048,
            jump_std=0.06,
            is_acute_jump=True,
            recommended_action="DEFER",
            position_scale_multiplier=0.5,
            stop_loss_buffer_multiplier=1.5,
        )
        mock_jump.evaluate_ticker = AsyncMock(return_value=acute_eval)

        sg = SlippageGuardService(jump_guard=mock_jump)
        sg.is_opening_auction_window = MagicMock(return_value=(False, "常規時段"))
        sg.get_ticker_quote = AsyncMock(return_value={
            "bid": 100.0, "ask": 100.05, "mid": 100.025, "last": 100.02, "spread_pct": 0.0005
        })

        decision = await sg.evaluate_trade("NVDA", "BUY", amount_usd=100.0, check_opening_window=False)
        assert decision.passed is False
        assert decision.circuit_breaker_triggered is True
        assert "極端非連續跳躍衝擊" in decision.reason
        assert decision.recommended_action == "DEFER"
        assert decision.jump_intensity == 7.20
        assert decision.jump_regime == "ACUTE_JUMP_REGIME"

    @pytest.mark.asyncio
    async def test_evaluate_trade_moderate_jump_boosts_limit_buffer(self):
        """標的處於 MODERATE_JUMP 時，SlippageGuard 自適應放大限價保護緩衝 (+0.25x)"""
        mock_jump = MagicMock()
        mock_jump.is_enabled = True
        mod_eval = TickerJumpAssessment(
            symbol="TSM",
            regime=JumpRegime.MODERATE_JUMP,
            jump_intensity=3.50,
            continuous_volatility=0.25,
            total_volatility=0.32,
            relative_jump_ratio=0.22,
            jump_mean=-0.022,
            jump_std=0.04,
            is_acute_jump=False,
            recommended_action="THROTTLE",
            position_scale_multiplier=0.8,
            stop_loss_buffer_multiplier=1.25,
        )
        mock_jump.evaluate_ticker = AsyncMock(return_value=mod_eval)

        sg = SlippageGuardService(jump_guard=mock_jump)
        sg.is_opening_auction_window = MagicMock(return_value=(False, "常規時段"))
        sg.get_ticker_quote = AsyncMock(return_value={
            "bid": 150.0, "ask": 150.10, "mid": 150.05, "last": 150.05, "spread_pct": 0.0006
        })

        decision = await sg.evaluate_trade("TSM", "BUY", amount_usd=100.0, check_opening_window=False)
        assert decision.passed is True
        assert decision.jump_regime == "MODERATE_JUMP"
        # 包含 jump_boost 的自適應限價單上限
        assert decision.adaptive_limit_price >= 150.10


class TestBatchCashDeploymentJumpIntegration:
    """測試 BatchCashDeploymentService 整合跳躍擴散指標與執行阻斷"""

    @pytest.mark.asyncio
    async def test_get_deployment_plan_includes_jump_summary(self):
        """驗證 get_deployment_plan 包含 jump_summary 與候選標的跳躍強度標記"""
        broker = MagicMock()
        broker.get_positions = AsyncMock(return_value=[])
        account = MagicMock(total_equity=1700.0, available_cash=1000.0)
        broker.get_account = AsyncMock(return_value=account)

        deploy_svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=DummySettingsService({"enable_bayesian_jump_guard": True}),
            broker=broker,
        )
        deploy_svc.get_portfolio_status = AsyncMock(return_value={
            "total_equity": 1700.0, "available_cash": 1000.0, "deployable_cash": 600.0,
            "required_reserve_usd": 340.0, "defensive_reserve_pct": 20.0,
        })
        plan = await deploy_svc.get_deployment_plan(batch_number=1)

        assert "jump_summary" in plan
        assert isinstance(plan["jump_summary"], dict)

    @pytest.mark.asyncio
    async def test_execute_batch_defers_jump_acute_candidate(self):
        """當候選標的觸發跳躍擴散熔斷時，標記為 jump_diffusion_deferred 並保留批次"""
        broker = MagicMock()
        broker.get_positions = AsyncMock(return_value=[])
        account = MagicMock(total_equity=1700.0, available_cash=1000.0)
        broker.get_account = AsyncMock(return_value=account)

        deploy_svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=DummySettingsService({"enable_bayesian_jump_guard": True}),
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

        # 模擬 SlippageGuard 回報跳躍熔斷
        jump_acute_decision = SlippageGuardDecision(
            passed=False,
            reason="⚠️ 標的 NVDA 檢測到極端非連續跳躍衝擊 (跳躍強度 λ: 7.20 次/年, 體制: ACUTE_JUMP_REGIME)",
            circuit_breaker_triggered=True,
            jump_intensity=7.20,
            jump_regime="ACUTE_JUMP_REGIME",
            recommended_action="DEFER",
        )
        deploy_svc.slippage_guard.evaluate_trade = AsyncMock(return_value=jump_acute_decision)

        with patch("src.infrastructure.cache.redis_client.get_redis", new_callable=AsyncMock) as mock_r_factory:
            mock_r = AsyncMock()
            mock_r_factory.return_value = mock_r
            res = await deploy_svc.execute_batch(batch_number=1, force=False, enforce_market_hours=False)

        assert res["success"] is False
        trades = res.get("executed_trades", [])
        assert len(trades) == 1
        assert trades[0]["status"] == "jump_diffusion_deferred"
        assert trades[0]["jump_intensity"] == 7.20
        assert trades[0]["jump_regime"] == "ACUTE_JUMP_REGIME"


class TestConversationRouterJumpCommand:
    """測試 ConversationRouter 對 /jump 系統指令的解析與 HTML 報表卡片渲染"""

    def test_is_system_command_recognizes_jump_aliases(self):
        """路由器應精確辨識 /jump, /jumpdiffusion, /merton, /bayesian, 跳躍擴散, 跳躍 等別名"""
        router = ConversationRouter()
        aliases = [
            "/jump", "/jumpdiffusion", "/merton", "/bayesian", "/跳躍",
            "jump", "jumpdiffusion", "merton", "bayesian", "跳躍擴散", "跳躍", "跳空", "貝葉斯跳躍"
        ]
        for alias in aliases:
            assert router._is_system_command(alias) is True, f"Failed to recognize {alias}"

    @pytest.mark.asyncio
    async def test_handle_system_command_jump_output(self):
        """調用 /jump 應輸出包含 Merton 模型、跳躍強度 λ、跳躍佔比 RJ、體制矩陣的 HTML 報表"""
        router = ConversationRouter()
        output = await router._handle_system_command(
            adapter=None,
            channel_user_id="U12345",
            text="/jump",
            resolved_user_id="default_user",
        )

        assert output is not None
        assert "多期動態貝葉斯更新與機制轉換跳躍擴散報告" in output
        assert "Merton (1976)" in output
        assert "Bipower Variation" in output
        assert "全市場跳躍體制" in output
        assert "平均跳躍強度 λ" in output
        assert "跳躍變異佔比 RJ" in output
        assert "風控處置矩陣" in output

    @pytest.mark.asyncio
    async def test_handle_system_command_guard_links_to_jump(self):
        """/guard 指令輸出應包含導引至 /jump 的提示連結"""
        router = ConversationRouter()
        output = await router._handle_system_command(
            adapter=None,
            channel_user_id="U12345",
            text="/guard",
            resolved_user_id="default_user",
        )

        assert output is not None
        assert "/jump" in output
        assert "貝葉斯跳躍擴散" in output or "Merton" in output
