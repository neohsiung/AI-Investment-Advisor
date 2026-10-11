"""
Unit Tests for Dynamic Fill-Quality Tracking & Adaptive Slippage Compensator (Phase 29)
========================================================================================
涵蓋：
1. AdaptiveExecutionSlippageCompensator 之 Redis 跨進程快取與 EWMA 模型閉環校準
2. 標的成交品質評級 (A+ ~ F) 與流動性黑洞 (Liquidity Black Hole) 偵測
3. SlippageGuardService 整合：動態自適應限價緩衝調整 (0.8x ~ 1.5x) 與黑洞熔斷防線
4. BatchCashDeploymentService 整合：候選標的流動性審查、黑洞標的暫緩下單、保留批次指針不跳號、推播通知獨立顯示
5. ConversationRouter 整合：0-LLM 快速指令 /quality (及別名) 與 /guard 擴充輸出
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.adaptive_execution_slippage_compensator import (
    AdaptiveExecutionSlippageCompensator,
    SlippageCompensationMetrics,
)
from src.services.slippage_guard_service import (
    SlippageGuardService,
    SlippageGuardDecision,
)
from src.services.batch_cash_deployment_service import (
    BatchCashDeploymentService,
)
from src.services.conversation_router import ConversationRouter
from src.services.order_execution_feedback_service import ExecutionVenue, OrderAction


class DummySettingsService:
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        self.settings_repo = self

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def get_all_settings(self) -> Dict[str, Any]:
        return self.settings


class DummyRedis:
    def __init__(self):
        self.store = {}

    def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self.store[key] = value
        return True

    async def aget(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def aset(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self.store[key] = value
        return True


# ═══════════════════════════════════════════════════════════════════════════
# 1. AdaptiveExecutionSlippageCompensator Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAdaptiveExecutionSlippageCompensator:
    @pytest.fixture
    def settings(self):
        return DummySettingsService({
            "enable_dynamic_fill_quality_tracking": True,
            "slippage_compensator_enabled": True,
            "slippage_ewma_alpha": 0.20,
            "slippage_min_multiplier": 0.50,
            "slippage_max_multiplier": 3.00,
            "slippage_adverse_penalty_bps": 5.0,
            "slippage_baseline_bps": 5.0,
            "liquidity_black_hole_multiplier_threshold": 2.50,
            "max_slippage_compensation_buffer": 0.0025,
        })

    @pytest.fixture
    def compensator(self, settings):
        return AdaptiveExecutionSlippageCompensator(
            user_id="test_user_p29",
            settings_repo=settings,
        )

    def test_redis_persistence_and_restore(self, compensator):
        mock_redis = DummyRedis()
        metrics = SlippageCompensationMetrics(
            symbol="NVDA",
            realized_slippage_bps_mean=8.5,
            expected_slippage_bps_mean=5.0,
            slippage_multiplier=1.70,
            adverse_selection_count=1,
            adverse_penalty_bps=5.0,
            calibrated_effective_slippage_bps=13.5,
            calibrated_effective_slippage_pct=0.00135,
            sample_count=3,
        )

        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=mock_redis):
            compensator._save_metrics_to_redis(metrics)

            # 驗證 Redis 存入 key
            expected_key = f"fill_quality:metrics:test_user_p29:NVDA"
            assert expected_key in mock_redis.store
            saved_data = json.loads(mock_redis.store[expected_key])
            assert saved_data["symbol"] == "NVDA"
            assert saved_data["slippage_multiplier"] == 1.70

            # 驗證還原讀取
            loaded = compensator._load_metrics_from_redis("NVDA")
            assert loaded is not None
            assert loaded.symbol == "NVDA"
            assert loaded.realized_slippage_bps_mean == 8.5
            assert loaded.sample_count == 3
            assert loaded.adverse_selection_count == 1

    def test_get_metrics_cache_fallback(self, compensator):
        mock_redis = DummyRedis()
        metrics = SlippageCompensationMetrics(
            symbol="MSFT",
            realized_slippage_bps_mean=4.0,
            expected_slippage_bps_mean=5.0,
            slippage_multiplier=0.90,
            adverse_selection_count=0,
            adverse_penalty_bps=0.0,
            calibrated_effective_slippage_bps=4.5,
            calibrated_effective_slippage_pct=0.00045,
            sample_count=2,
        )
        mock_redis.store["fill_quality:metrics:test_user_p29:MSFT"] = json.dumps(metrics.to_dict())

        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=mock_redis):
            # 確保記憶體字典為空
            compensator._metrics_map.clear()
            m = compensator.get_metrics("MSFT")

            assert m.symbol == "MSFT"
            assert m.realized_slippage_bps_mean == 4.0
            assert m.slippage_multiplier == 0.90
            assert "MSFT" in compensator._metrics_map

    def test_record_fill_and_ewma_update(self, compensator):
        mock_redis = DummyRedis()
        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=mock_redis):
            # 模擬第 1 筆正常成交：預期 100.00，成交 100.04 (4 bps 滑點)
            fill1 = compensator.record_fill(
                order_id="ord_1",
                symbol="AAPL",
                action=OrderAction.BUY,
                venue=ExecutionVenue.IBKR,
                fill_price=100.04,
                fill_quantity=1.0,
                arrival_price=100.00,
            )
            m1 = compensator.get_metrics("AAPL")
            assert m1.sample_count == 1
            assert m1.adverse_selection_count == 0

            # 模擬第 2 筆嚴重不利滑點 (逆向選擇)：預期 100.00，成交 100.30 (30 bps 滑點，為基準 5 bps 之 6 倍)
            fill2 = compensator.record_fill(
                order_id="ord_2",
                symbol="AAPL",
                action=OrderAction.BUY,
                venue=ExecutionVenue.IBKR,
                fill_price=100.30,
                fill_quantity=1.0,
                arrival_price=100.00,
            )
            m2 = compensator.get_metrics("AAPL")
            assert m2.sample_count == 2
            assert m2.slippage_multiplier > 1.0

    def test_get_fill_quality_summary(self, compensator):
        # 植入不同等級的標的指標
        compensator._metrics_map["NVDA"] = SlippageCompensationMetrics(
            symbol="NVDA",
            realized_slippage_bps_mean=2.5,
            expected_slippage_bps_mean=5.0,
            slippage_multiplier=0.85,
            adverse_selection_count=0,
            adverse_penalty_bps=0.0,
            calibrated_effective_slippage_bps=4.25,
            calibrated_effective_slippage_pct=0.000425,
            sample_count=5,
        )
        compensator._metrics_map["MU"] = SlippageCompensationMetrics(
            symbol="MU",
            realized_slippage_bps_mean=35.0,
            expected_slippage_bps_mean=5.0,
            slippage_multiplier=2.80,
            adverse_selection_count=3,
            adverse_penalty_bps=15.0,
            calibrated_effective_slippage_bps=29.0,
            calibrated_effective_slippage_pct=0.0029,
            sample_count=4,
        )

        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=None):
            summary = compensator.get_fill_quality_summary(["NVDA", "MU", "AAPL"])

            symbols = summary["symbols"]
            assert symbols["NVDA"]["grade"] == "A+"
            assert symbols["NVDA"]["liquidity_status"] == "DEEP"
            assert symbols["NVDA"]["dynamic_buffer_factor"] == 0.85

            assert symbols["MU"]["grade"] == "F"
            assert symbols["MU"]["liquidity_status"] == "BLACK_HOLE"
            assert symbols["MU"]["dynamic_buffer_factor"] == 1.50

            assert symbols["AAPL"]["sample_count"] == 0
            assert symbols["AAPL"]["grade"] == "A"
            assert symbols["AAPL"]["liquidity_status"] == "NORMAL"

            assert summary["overall_liquidity_health"] == "DEGRADED"


# ═══════════════════════════════════════════════════════════════════════════
# 2. SlippageGuardService & Dynamic Compensation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSlippageGuardWithCompensator:
    @pytest.fixture
    def settings(self):
        return DummySettingsService({
            "enable_slippage_guard": True,
            "max_allowed_spread_pct": 0.0015,
            "market_open_delay_minutes": 5,
            "enable_dynamic_fill_quality_tracking": True,
            "slippage_compensator_enabled": True,
            "liquidity_black_hole_multiplier_threshold": 2.50,
            "max_slippage_compensation_buffer": 0.0025,
        })

    @pytest.fixture
    def guard(self, settings):
        compensator = AdaptiveExecutionSlippageCompensator(
            user_id="test_user_p29",
            settings_repo=settings,
        )
        guard_svc = SlippageGuardService(
            user_id="test_user_p29",
            settings_service=settings,
            compensator=compensator,
        )
        return guard_svc

    @pytest.mark.asyncio
    async def test_evaluate_trade_normal_fill_quality(self, guard):
        # 報價：bid=100.00, ask=100.10, mid=100.05, spread_pct=0.0010 (10 bps <= 15 bps)
        quote = {
            "bid": 100.00,
            "ask": 100.10,
            "last": 100.05,
            "mid": 100.05,
            "spread_pct": 0.0010,
        }
        guard.get_ticker_quote = AsyncMock(return_value=quote)
        guard.is_opening_auction_window = MagicMock(return_value=(False, ""))

        decision = await guard.evaluate_trade("AAPL", "BUY", amount_usd=100.0, check_opening_window=False)

        assert decision.passed is True
        assert decision.recommended_action == "PROCEED"
        assert decision.fill_quality_grade in ("A", "A+")
        assert decision.adaptive_limit_price is not None
        assert decision.adaptive_limit_price >= 100.10

    @pytest.mark.asyncio
    async def test_evaluate_trade_liquidity_black_hole_breaker(self, guard):
        # 設定 MU 為黑洞狀態
        guard.compensator._metrics_map["MU"] = SlippageCompensationMetrics(
            symbol="MU",
            realized_slippage_bps_mean=40.0,
            expected_slippage_bps_mean=5.0,
            slippage_multiplier=3.0,
            adverse_selection_count=3,
            adverse_penalty_bps=15.0,
            calibrated_effective_slippage_bps=30.0,
            calibrated_effective_slippage_pct=0.0030,
            sample_count=3,
        )

        quote = {
            "bid": 80.00,
            "ask": 80.08,
            "last": 80.04,
            "mid": 80.04,
            "spread_pct": 0.0010,  # 即使當前價差 10 bps 看似正常
        }
        guard.get_ticker_quote = AsyncMock(return_value=quote)
        guard.is_opening_auction_window = MagicMock(return_value=(False, ""))

        decision = await guard.evaluate_trade("MU", "BUY", amount_usd=80.0, check_opening_window=False)

        # 必須觸發黑洞熔斷
        assert decision.passed is False
        assert decision.circuit_breaker_triggered is True
        assert decision.fill_quality_grade == "F"
        assert decision.recommended_action == "DEFER"
        assert "流動性黑洞熔斷" in decision.reason

    def test_record_realized_slippage_closed_loop(self, guard):
        guard.compensator.record_fill = MagicMock()
        mock_redis = DummyRedis()
        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=mock_redis):
            slip = guard.record_realized_slippage(
                ticker="TSM",
                action="BUY",
                expected_price=100.00,
                fill_price=100.20,
                order_id="test_ord_123",
            )
            assert slip == pytest.approx(0.0020, rel=1e-3)
            # 確認閉環反饋呼叫
            guard.compensator.record_fill.assert_called_once()
            args, kwargs = guard.compensator.record_fill.call_args
            assert kwargs["symbol"] == "TSM"
            assert kwargs["fill_price"] == 100.20
            assert kwargs["arrival_price"] == 100.00


# ═══════════════════════════════════════════════════════════════════════════
# 3. BatchCashDeploymentService Fill Quality & Black Hole Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestBatchCashDeploymentFillQuality:
    @pytest.fixture
    def settings(self):
        return DummySettingsService({
            "enable_market_open_cash_deployment": True,
            "batch_cash_deployment_portion": 0.33,
            "enable_slippage_guard": True,
            "max_allowed_spread_pct": 0.0015,
            "enable_dynamic_fill_quality_tracking": True,
            "slippage_compensator_enabled": True,
            "liquidity_black_hole_multiplier_threshold": 2.50,
        })

    @pytest.fixture
    def deploy_service(self, settings):
        service = BatchCashDeploymentService(
            user_id="test_user_p29",
            settings_service=settings,
        )
        return service

    @pytest.mark.asyncio
    async def test_get_deployment_plan_defers_black_hole_candidate(self, deploy_service):
        port_status = {
            "total_equity": 1687.95,
            "available_cash": 1000.0,
            "required_reserve_usd": 337.59,
            "deployable_cash": 662.41,
            "positions_count": 3,
        }
        deploy_service.get_portfolio_status = AsyncMock(return_value=port_status)
        deploy_service._get_active_positions = AsyncMock(return_value=[])
        deploy_service._get_broker = AsyncMock(return_value=None)

        # 設定 MU 為黑洞
        deploy_service.slippage_guard.compensator._metrics_map["MU"] = SlippageCompensationMetrics(
            symbol="MU",
            realized_slippage_bps_mean=45.0,
            expected_slippage_bps_mean=5.0,
            slippage_multiplier=2.90,
            adverse_selection_count=3,
            adverse_penalty_bps=15.0,
            calibrated_effective_slippage_bps=35.0,
            calibrated_effective_slippage_pct=0.0035,
            sample_count=4,
        )

        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=None):
            plan = await deploy_service.get_deployment_plan(batch_number=2)

            assert "fill_quality_summary" in plan
            summary = plan["fill_quality_summary"]
            assert summary["symbols"]["MU"]["grade"] == "F"

            # 檢查 MU 在 all_candidates 中被標記為黑洞且 amount_usd == 0.0，但 planned_amount_usd 有保留
            mu_cand = next(c for c in plan["all_candidates"] if c["ticker"] == "MU")
            assert mu_cand["liquidity_black_hole"] is True
            assert mu_cand["amount_usd"] == 0.0
            assert mu_cand["planned_amount_usd"] > 10.0

            # 檢查 MU 不存在於直接執行的 items 清單中
            assert not any(i["ticker"] == "MU" for i in plan["items"])

    @pytest.mark.asyncio
    async def test_execute_batch_defers_black_hole_and_retains_batch(self, deploy_service):
        deploy_service.get_active_batch_number = AsyncMock(return_value=2)
        deploy_service.market_clock.is_market_open = MagicMock(return_value=True)
        deploy_service.slippage_guard.is_opening_auction_window = MagicMock(return_value=(False, ""))
        deploy_service.blackout_guard.evaluate_macro_blackout = MagicMock(
            return_value=MagicMock(is_blackout=False, reason="Safe")
        )
        deploy_service.blackout_guard.evaluate_candidate = AsyncMock(
            return_value=MagicMock(is_blackout=False, reason="Safe")
        )

        # 模擬 plan: MSFT 可下單，MU 處於黑洞 (事前被排除出 items)
        mock_plan = {
            "batch_number": 2,
            "can_execute": True,
            "total_batch_amount": 91.0,
            "items": [
                {
                    "ticker": "MSFT",
                    "amount_usd": 91.0,
                    "confidence_score": 0.85,
                    "role": "Core Growth",
                    "rationale": "Test MSFT",
                }
            ],
            "all_candidates": [
                {
                    "ticker": "MSFT",
                    "amount_usd": 91.0,
                    "planned_amount_usd": 91.0,
                    "liquidity_black_hole": False,
                    "blackout_active": False,
                },
                {
                    "ticker": "MU",
                    "amount_usd": 0.0,
                    "planned_amount_usd": 79.0,
                    "liquidity_black_hole": True,
                    "slippage_multiplier": 2.80,
                    "blackout_active": False,
                }
            ],
            "status": {"deployable_cash": 600.0, "available_cash": 900.0, "required_reserve_usd": 300.0},
        }
        deploy_service.get_deployment_plan = AsyncMock(return_value=mock_plan)
        deploy_service.get_portfolio_status = AsyncMock(
            return_value={"total_equity": 1680.0, "available_cash": 809.0, "deployable_cash": 509.0, "required_reserve_usd": 300.0}
        )
        deploy_service._get_broker = AsyncMock(return_value=None)
        deploy_service._send_deployment_notification = AsyncMock()

        # Mock trading execution for MSFT
        mock_trade_svc = MagicMock()
        mock_trade_svc.evaluate_and_execute_trade = AsyncMock(return_value={"status": "executed", "order_id": "ord_msft_1"})

        # Mock slippage guard evaluate_trade for MSFT
        deploy_service.slippage_guard.evaluate_trade = AsyncMock(
            return_value=SlippageGuardDecision(
                passed=True,
                reason="Pass",
                spread_pct=0.0008,
                fill_quality_grade="A",
                fill_quality_multiplier=1.0,
            )
        )

        mock_redis = DummyRedis()
        with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis), \
             patch("src.services.automated_trading_service.AutomatedTradingService", return_value=mock_trade_svc):

            result = await deploy_service.execute_batch(batch_number=2, enforce_market_hours=False)

            # 驗證執行結果中包含 MU 的黑洞暫緩紀錄
            executed = result["executed_trades"]
            mu_rec = next((t for t in executed if t["ticker"] == "MU"), None)
            assert mu_rec is not None
            assert mu_rec["status"] == "liquidity_black_hole_deferred"
            assert mu_rec["amount_usd"] == 79.0

            # 驗證因 MU 暫緩，批次不跳號推進，仍然保留批次 2 (未被寫入 3)
            current_batch_in_redis = mock_redis.store.get(f"batch_deployment:current_batch:test_user_p29")
            assert current_batch_in_redis != "3"


# ═══════════════════════════════════════════════════════════════════════════
# 4. ConversationRouter Tests (/quality & /guard)
# ═══════════════════════════════════════════════════════════════════════════

class TestConversationRouterQualityCommand:
    @pytest.fixture
    def router(self):
        return ConversationRouter()

    def test_is_system_command_recognizes_quality_aliases(self, router):
        aliases = ["/quality", "quality", "/fills", "fills", "成交品質", "滑點統計", "流動性", "/slippage", "slippage"]
        for cmd in aliases:
            assert router._is_system_command(cmd) is True

    @pytest.mark.asyncio
    async def test_handle_system_command_quality_output(self, router):
        mock_summary = {
            "portfolio_avg_slippage_bps": 4.8,
            "portfolio_avg_multiplier": 1.05,
            "overall_liquidity_health": "OPTIMAL",
            "symbols": {
                "MSFT": {
                    "symbol": "MSFT",
                    "realized_slippage_bps": 3.2,
                    "slippage_multiplier": 0.95,
                    "adverse_selection_count": 0,
                    "sample_count": 3,
                    "grade": "A+",
                    "liquidity_status": "DEEP",
                    "dynamic_buffer_factor": 0.95,
                    "description": "極佳成交品質",
                }
            },
        }

        with patch("src.services.adaptive_execution_slippage_compensator.AdaptiveExecutionSlippageCompensator.get_fill_quality_summary", return_value=mock_summary):
            res = await router._handle_system_command(
                adapter=MagicMock(),
                channel_user_id="telegram_123",
                text="/quality",
                resolved_user_id="test_user_p29",
            )

            assert res is not None
            assert "標的成交品質與動態滑點補償追蹤" in res
            assert "MSFT" in res
            assert "A+" in res
            assert "4.8 bps" in res
            assert "1.05x" in res

    @pytest.mark.asyncio
    async def test_handle_system_command_guard_includes_fill_quality(self, router):
        res = await router._handle_system_command(
            adapter=MagicMock(),
            channel_user_id="telegram_123",
            text="/guard",
            resolved_user_id="test_user_p29",
        )

        assert res is not None
        assert "開盤防滑點守衛與價差熔斷狀態" in res
        assert "動態成交品質追蹤" in res
        assert "流動性黑洞熔斷 (Black Hole)" in res
