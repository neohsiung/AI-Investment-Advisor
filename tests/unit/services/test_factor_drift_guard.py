"""
Unit Tests for Factor Drift & Concept Drift Auto-Healing Guard (Phase 30)
========================================================================
驗證：
1. Spearman Rank IC 計算 (Rank IC, 邊界條件, NaN/少於3筆防護)
2. 因子特徵漂移偵測 (HEALTHY, DRIFTING, INVERTED) 與健康評級 (OPTIMAL, MODERATE, DEGRADED)
3. 閉環自癒重平衡引擎 (Simplex Normalization 嚴格收斂為 1.0, 阻尼懲罰, 防禦/流動性錨點注入)
4. Redis 跨進程狀態快取持久化與讀取 (Redis cache, clear_drift_cache)
5. TacticalFactorRotationService 動態透明接入自癒權重矩陣
6. SentinelService Dimension 11.4 哨兵非阻塞監控與告警防抖
7. 0-LLM 對話指令 /factor 即時輸出與 /guard 狀態整合
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.factor_drift_guard_service import (
    FACTOR_NAMES,
    FactorDriftGuardService,
    FactorDriftReport,
    FactorHealthMetrics,
)
from src.services.tactical_factor_rotation_service import (
    TacticalFactorRotationService,
    TacticalMarketPhase,
)


class TestFactorDriftGuardService:
    @pytest.fixture
    def mock_settings_service(self):
        settings = MagicMock()
        config_map = {
            "enable_factor_drift_guard": True,
            "enable_factor_auto_healing": True,
            "factor_ic_decay_threshold": 0.00,
            "factor_ic_lookback_days": 30,
            "factor_healing_defense_bias": 0.60,
        }
        settings.get_setting.side_effect = lambda k, default=None, user_id=None: config_map.get(k, default)
        return settings

    @pytest.fixture
    def service(self, mock_settings_service):
        svc = FactorDriftGuardService(user_id="test_user", settings_service=mock_settings_service)
        svc.clear_drift_cache()
        return svc

    def test_calculate_rank_ic_perfect_positive(self):
        """驗證完全正相關之 Rank IC 應接近 +1.0"""
        scores = {"AAPL": 1.0, "MSFT": 2.0, "NVDA": 3.0, "GOOG": 4.0}
        returns = {"AAPL": 0.01, "MSFT": 0.02, "NVDA": 0.03, "GOOG": 0.04}
        ic = FactorDriftGuardService.calculate_rank_ic(scores, returns)
        assert pytest.approx(ic, 0.001) == 1.0

    def test_calculate_rank_ic_perfect_negative(self):
        """驗證完全負相關之 Rank IC 應接近 -1.0"""
        scores = {"AAPL": 1.0, "MSFT": 2.0, "NVDA": 3.0, "GOOG": 4.0}
        returns = {"AAPL": 0.04, "MSFT": 0.03, "NVDA": 0.02, "GOOG": 0.01}
        ic = FactorDriftGuardService.calculate_rank_ic(scores, returns)
        assert pytest.approx(ic, 0.001) == -1.0

    def test_calculate_rank_ic_insufficient_samples(self):
        """驗證重疊標的少於 3 檔時返回 0.0 避免無效推論"""
        scores = {"AAPL": 1.0, "MSFT": 2.0}
        returns = {"AAPL": 0.01, "MSFT": 0.02}
        ic = FactorDriftGuardService.calculate_rank_ic(scores, returns)
        assert ic == 0.0

    def test_evaluate_factor_health_default_healthy(self, service):
        """在基準無漂移狀態下，所有因子應評估為 HEALTHY，整體健康度 OPTIMAL"""
        report = service.evaluate_factor_health(TacticalMarketPhase.BULL_ACCELERATION)
        assert report.phase == TacticalMarketPhase.BULL_ACCELERATION.value
        assert report.overall_factor_health == "OPTIMAL"
        assert not report.has_inverted_factors
        assert report.healed_count == 0
        for fn in FACTOR_NAMES:
            assert fn in report.factors
            assert report.factors[fn].status == "HEALTHY"
            assert report.factors[fn].decay_penalty == 0.0

    def test_evaluate_factor_health_with_inversion_and_auto_healing(self, service):
        """
        當動能因子發生負向反轉 (IC = -0.08) 時：
        1. 因子狀態標記為 INVERTED -> AUTO_HEALED
        2. 動能因子權重遭受阻尼衰減 (decay_penalty > 0)
        3. 釋放出的權重注入防禦因子 (quality, liquidity_premium / low_vol)
        4. 總權重嚴格單體投影為 1.0000
        """
        service.inject_factor_drift("momentum", -0.08)
        report = service.evaluate_factor_health(TacticalMarketPhase.BULL_ACCELERATION)

        assert report.has_inverted_factors
        assert report.overall_factor_health == "DEGRADED"
        assert report.healed_count >= 1

        mom_metric = report.factors["momentum"]
        assert mom_metric.status == "AUTO_HEALED"
        assert mom_metric.decay_penalty > 0.0
        assert mom_metric.effective_weight < mom_metric.baseline_weight

        # 驗證總權重精確為 1.0000 且無負值
        total_w = sum(report.active_weights.values())
        assert pytest.approx(total_w, 0.0001) == 1.0000
        for fn, w in report.active_weights.items():
            assert w >= 0.0

    def test_defensive_consolidation_healing_split(self, service):
        """
        在防禦震盪體制 (DEFENSIVE_CONSOLIDATION) 下，自癒權重應優先注入 low_vol (60%) 與 quality (40%)
        """
        service.inject_factor_drift("smart_money", -0.05)
        base_weights = {
            "low_vol": 0.35,
            "quality": 0.35,
            "value": 0.15,
            "liquidity_premium": 0.10,
            "smart_money": 0.05,
            "momentum": 0.00,
        }
        report = service.evaluate_factor_health(
            TacticalMarketPhase.DEFENSIVE_CONSOLIDATION,
            base_weights=base_weights,
        )

        assert report.healed_count >= 1
        assert report.active_weights["smart_money"] < base_weights["smart_money"]
        assert report.active_weights["low_vol"] > base_weights["low_vol"]
        assert report.active_weights["quality"] > base_weights["quality"]
        assert pytest.approx(sum(report.active_weights.values()), 0.0001) == 1.0000

    def test_auto_healing_disabled(self, service):
        """當 auto_healing_enabled 設為 False 時，不修改權重矩陣"""
        service.inject_factor_drift("momentum", -0.09)
        with patch.object(FactorDriftGuardService, "auto_healing_enabled", False):
            report = service.evaluate_factor_health(TacticalMarketPhase.BULL_ACCELERATION)
            assert report.healed_count == 0
            assert report.active_weights == report.original_weights

    def test_simplex_normalization_corner_cases(self):
        """驗證單體投影在極端零總和與負值輸入時之健壯性"""
        zeros = {"a": 0.0, "b": 0.0, "c": 0.0}
        norm_zeros = FactorDriftGuardService._simplex_normalize(zeros)
        assert pytest.approx(sum(norm_zeros.values()), 0.0001) == 1.0
        assert max(norm_zeros.values()) - min(norm_zeros.values()) <= 0.0002

        negs = {"a": -0.5, "b": 0.4, "c": 0.6}
        norm_negs = FactorDriftGuardService._simplex_normalize(negs)
        assert pytest.approx(sum(norm_negs.values()), 0.0001) == 1.0
        assert norm_negs["a"] == 0.0

    def test_redis_persistence_and_clear_cache(self, service):
        """驗證 Redis 快取存取與清除機制"""
        mock_redis = MagicMock()
        mock_redis.get.return_value = '{"momentum": -0.05}'

        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=mock_redis):
            service.inject_factor_drift("momentum", -0.05)
            assert mock_redis.set.called

            service.clear_drift_cache()
            assert mock_redis.delete.called


class TestFactorDriftIntegration:
    @pytest.mark.asyncio
    async def test_tactical_rotation_service_effective_weights(self):
        """驗證 TacticalFactorRotationService 在有漂移時透明傳回自癒權重"""
        settings = MagicMock()
        cfg = {
            "enable_factor_drift_guard": True,
            "enable_factor_auto_healing": True,
        }
        settings.get_setting.side_effect = lambda k, default=None, **kw: cfg.get(k, default)

        t_service = TacticalFactorRotationService(user_id="test_user", settings_service=settings)

        drift_service = FactorDriftGuardService(user_id="test_user", settings_service=settings)
        drift_service.inject_factor_drift("momentum", -0.06)

        # apply_auto_healing=False 回傳基準
        base_w = t_service.get_phase_factor_weights(TacticalMarketPhase.BULL_ACCELERATION, apply_auto_healing=False)
        assert base_w["momentum"] == 0.35

        # apply_auto_healing=True 回傳自癒權重
        healed_w = t_service.get_phase_factor_weights(TacticalMarketPhase.BULL_ACCELERATION, apply_auto_healing=True)
        assert healed_w["momentum"] < 0.35
        assert pytest.approx(sum(healed_w.values()), 0.0001) == 1.0000

        drift_service.clear_drift_cache()

    @pytest.mark.asyncio
    async def test_sentinel_dimension_11_4_check_and_handle(self):
        """驗證 SentinelService Dimension 11.4 哨兵觸發與非阻塞日誌"""
        from src.services.sentinel_service import SentinelService

        sentinel = SentinelService(user_id="test_user")

        drift_service = FactorDriftGuardService(user_id="test_user", settings_service=sentinel.settings_service)
        drift_service.inject_factor_drift("smart_money", -0.07)

        triggers = await sentinel._check_factor_drift_health()
        assert len(triggers) == 1
        assert triggers[0]["dimension"] == "11.4"
        assert triggers[0]["type"] == "FACTOR_DRIFT_AUTO_HEALED"
        assert triggers[0]["priority"] == "P3"

        # 驗證 _handle_factor_drift_health 成功防抖處理
        with patch.object(sentinel, "_acquire_cooldown", AsyncMock(return_value=True)):
            await sentinel._handle_factor_drift_health(triggers)

        drift_service.clear_drift_cache()

    @pytest.mark.asyncio
    async def test_conversation_router_factor_command(self):
        """驗證 ConversationRouter 0-LLM 指令 /factor 與 /guard 整合"""
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()

        # 1. 驗證指令識別
        for cmd in ("/factor", "/factors", "/ic", "因子", "特徵漂移", "因子自癒", "因子監控"):
            assert router._is_system_command(cmd)

        # 2. 驗證 /factor 輸出內容
        adapter = MagicMock()
        resp = await router._handle_system_command(
            adapter=adapter,
            channel_user_id="U123",
            text="/factor",
            resolved_user_id="test_user",
        )
        assert resp is not None
        assert "全自動機器學習因子特徵漂移與失效自癒" in resp
        assert "當前市場週期體制" in resp
        assert "動能趨勢 (Momentum)" in resp
        assert "Rank IC" in resp
        assert "Simplex Normalization" in resp

        # 3. 驗證 /guard 輸出中包含因子特徵漂移防線 (P30)
        guard_resp = await router._handle_system_command(
            adapter=adapter,
            channel_user_id="U123",
            text="/guard",
            resolved_user_id="test_user",
        )
        assert guard_resp is not None
        assert "因子特徵漂移與自癒 (P30)" in guard_resp
