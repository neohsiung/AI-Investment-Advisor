"""
Unit Tests for Phase 39:
Unified Risk Gateway, Circuit Breaker Grace Window & Universe Telemetry
========================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from src.services.actionable_alert_service import ActionableAlertHubService
from src.services.conversation_router import ConversationRouter
from src.services.inference_hurdle_gate_service import InferenceHurdleGateService
from src.services.trading_protections_service import TradingProtectionsService
from src.services.unified_risk_gateway_service import (
    RiskSeverity,
    UnifiedRiskGatewayService,
)
from src.services.universe_lifecycle_service import UniverseLifecycleService


@pytest.fixture
def mock_db_engine():
    """In-memory SQLite engine simulating decision_outcomes."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE decision_outcomes (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                ticker TEXT,
                signal TEXT,
                alpha_pct REAL,
                resolved_at TIMESTAMP,
                created_at TIMESTAMP
            )
        """))
        conn.commit()
    return engine


class TestTradingProtectionsResetWatermark:
    """Test circuit breaker lockout reset watermark and grace window."""

    def test_consecutive_loss_lockout_and_reset(self, mock_db_engine):
        user_id = "test-user-p39"
        prot = TradingProtectionsService(user_id=user_id)
        prot.engine = mock_db_engine

        # Mock settings repo
        stored_settings = {
            "protection_consecutive_loss_lockout_n": 3,
            "protection_ticker_cooldown_days": 1,
            "protection_lockout_reset_at": None,
        }

        with patch("src.services.settings_service.SettingsService.get_all_settings", return_value=stored_settings), \
             patch("src.services.settings_service.SettingsService.save_setting") as mock_save:

            # 1. Insert 3 consecutive losing BUY decisions from 2 hours ago
            now = datetime.now(timezone.utc)
            t1 = now - timedelta(hours=3)
            t2 = now - timedelta(hours=2)
            t3 = now - timedelta(hours=1)

            with mock_db_engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO decision_outcomes (id, user_id, ticker, signal, alpha_pct, resolved_at, created_at)
                    VALUES
                    ('1', :uid, 'AMD', 'BUY', -4.2, :t1, :t1),
                    ('2', :uid, 'META', 'BUY', -2.9, :t2, :t2),
                    ('3', :uid, 'SPCX', 'BUY', -0.9, :t3, :t3)
                """), {"uid": user_id, "t1": t1, "t2": t2, "t3": t3})
                conn.commit()

            # Verify consecutive loss lockout fires
            check_res = prot.check("MSFT", "BUY")
            assert check_res is not None
            assert "Consecutive-loss lockout" in check_res

            # 2. Perform reset_lockout
            reset_ts = prot.reset_lockout()
            assert reset_ts is not None
            mock_save.assert_any_call("protection_lockout_reset_at", reset_ts)
            mock_save.assert_any_call("ai_trading_enabled", "true")

            # 3. Simulate stored setting updated with reset_ts
            stored_settings["protection_lockout_reset_at"] = reset_ts
            prot._cfg = None  # clear cache

            # Now check again: decisions resolved before reset_ts are archived!
            check_res_after = prot.check("MSFT", "BUY")
            assert check_res_after is None, "Lockout should be cleared after reset watermark"


class TestActionableAlertResetProtection:
    """Test interactive alert callback action=reset_protection calls reset_lockout."""

    @pytest.mark.asyncio
    async def test_execute_action_reset_protection(self):
        user_id = "test-user-alert"
        hub = ActionableAlertHubService(user_id=user_id)

        with patch("src.services.trading_protections_service.TradingProtectionsService.reset_lockout", return_value="2026-10-13T00:00:00Z") as mock_reset:
            res = await hub.execute_action("reset_protection")
            assert res["ok"] is True
            assert "reset_at" in res
            assert "風控保護機制已手動重設" in res["message"]
            mock_reset.assert_called_once()


class TestInferenceHurdleGate:
    """Test inference cost-to-alpha hurdle gate and mathematical routing."""

    def test_small_order_routes_to_0_llm(self):
        gate = InferenceHurdleGateService(user_id="test-hurdle-user")
        
        # Small routine rebalance ($89 order)
        eval_res = gate.evaluate_task_hurdle(
            task_type="batch_cash_deployment",
            order_amount_usd=89.0,
            estimated_llm_cost_usd=0.25,
        )
        assert eval_res.allow_llm is False
        assert eval_res.routing_mode == "0_LLM_MATH_ENGINE"
        assert eval_res.estimated_alpha_saved_bps > 0
        assert "0-LLM mathematical engine" in eval_res.reason

    def test_breaking_news_allows_llm(self):
        gate = InferenceHurdleGateService(user_id="test-hurdle-user")

        eval_res = gate.evaluate_task_hurdle(
            task_type="breaking_news_analysis",
            order_amount_usd=0.0,
            is_breaking_news=True,
        )
        assert eval_res.allow_llm is True
        assert eval_res.routing_mode == "FULL_LLM_COUNCIL"

    def test_telemetry_metrics(self):
        gate = InferenceHurdleGateService(user_id="test-hurdle-user")
        with patch.object(gate, "_get_redis", return_value=None):
            telemetry = gate.get_cost_to_alpha_telemetry()
            assert "alpha_preservation_status" in telemetry
            assert telemetry["target_net_alpha_pct"] == 10.0


class TestUnifiedRiskGateway:
    """Test Unified Risk Gateway consolidating pre-trade checks."""

    @pytest.mark.asyncio
    async def test_blocked_by_trading_protections(self):
        gateway = UnifiedRiskGatewayService(user_id="test-gateway-user")

        with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value="Consecutive loss lockout"):
            res = await gateway.evaluate_trade_risk(ticker="AAPL", action="BUY", amount_usd=100.0)
            assert res.allowed is False
            assert res.severity == RiskSeverity.BLOCKED
            assert res.primary_blocker == "TradingProtections"

    @pytest.mark.asyncio
    async def test_blocked_by_calendar_blackout(self):
        gateway = UnifiedRiskGatewayService(user_id="test-gateway-user")

        with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
             patch("src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate", new_callable=AsyncMock) as mock_cal:
            mock_cal.return_value = MagicMock(is_blackout=True, reason="TSM earnings within 48h", event_type="earnings")
            res = await gateway.evaluate_trade_risk(ticker="TSM", action="BUY", amount_usd=100.0)
            assert res.allowed is False
            assert res.severity == RiskSeverity.BLOCKED
            assert res.primary_blocker == "CalendarBlackout"

    @pytest.mark.asyncio
    async def test_sell_order_fails_open(self):
        gateway = UnifiedRiskGatewayService(user_id="test-gateway-user")

        with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None):
            res = await gateway.evaluate_trade_risk(ticker="META", action="SELL", amount_usd=100.0)
            assert res.allowed is True
            assert res.severity == RiskSeverity.NORMAL

    def test_reset_all_protections(self):
        gateway = UnifiedRiskGatewayService(user_id="test-gateway-user")
        with patch("src.services.trading_protections_service.TradingProtectionsService.reset_lockout", return_value="2026-10-13T12:00:00Z"):
            res = gateway.reset_all_protections()
            assert res["success"] is True
            assert res["reset_watermark"] == "2026-10-13T12:00:00Z"


class TestUniverseLifecycleNotificationAndCommand:
    """Test Universe Lifecycle notification dispatch and ConversationRouter /universe command."""

    @pytest.mark.asyncio
    async def test_dispatch_lifecycle_notification(self):
        uni = UniverseLifecycleService(user_id="test-uni-user")
        fake_result = {
            "success": True,
            "regime": {"regime": "BULL_GROWTH", "vix": 16.5},
            "active_count": 8,
            "candidate_count": 30,
            "shadow_count": 2,
            "evicted": ["DUMMY_OLD"],
            "admitted": ["DUMMY_NEW"],
            "rotations": [{"old_ticker": "OLD_TICK", "new_ticker": "NEW_TICK"}],
            "candidate_evolution": {"admitted_new_tickers": ["CAND_1"]},
            "shadow_evolution": {"graduated_tickers": ["GRAD_1"]},
            "sector_drift_report": {"status": "BALANCED", "distribution": {"hhi_index": 0.18}},
        }

        with patch("src.services.notification_service.NotificationService.notify_all", new_callable=AsyncMock) as mock_notify:
            mock_notify.return_value = {"telegram": True}
            res = await uni.dispatch_lifecycle_notification(fake_result)
            assert res is not None
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args.kwargs
            assert "標的池週度演化簡報" in call_kwargs["title"]
            assert "DUMMY_OLD" in call_kwargs["content"]
            assert "DUMMY_NEW" in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_conversation_router_guard_reset(self):
        router = ConversationRouter()
        with patch("src.services.trading_protections_service.TradingProtectionsService.reset_lockout", return_value="2026-10-13T07:00:00Z"):
            resp = await router._handle_system_command(
                adapter=MagicMock(),
                channel_user_id="chan-1",
                text="/guard reset",
                resolved_user_id="test-user",
            )
            assert resp is not None
            assert "風控熔斷與連續虧損鎖定已手動重設" in resp
            assert "2026-10-13T07:00:00Z" in resp

    @pytest.mark.asyncio
    async def test_conversation_router_universe_command(self):
        router = ConversationRouter()
        
        # Test status query
        with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository.get_all") as mock_get_all, \
             patch("src.services.universe_lifecycle_service.UniverseLifecycleService.detect_macro_regime") as mock_regime:
            
            mock_get_all.side_effect = lambda uid, status: [
                {"ticker": "NVDA", "sector": "Technology", "is_pinned": True}
            ] if status == "active" else [
                {"ticker": "COP"}, {"ticker": "ECL"}
            ] if status == "candidate" else []
            
            mock_regime.return_value = MagicMock(
                regime="BULL_GROWTH", vix=17.5, quality_score_adjustment=0.0
            )

            resp = await router._handle_system_command(
                adapter=MagicMock(),
                channel_user_id="chan-1",
                text="/universe",
                resolved_user_id="test-user",
            )
            assert resp is not None
            assert "投資顧問標的池即時架構狀態" in resp
            assert "NVDA" in resp
            assert "COP" in resp

        # Test scan subcommand
        with patch("src.infrastructure.tasks.run_universe_lifecycle.delay") as mock_delay, \
             patch("src.services.universe_lifecycle_service.UniverseLifecycleService.run_lifecycle_cycle", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"success": True}
            resp_scan = await router._handle_system_command(
                adapter=MagicMock(),
                channel_user_id="chan-1",
                text="/universe scan",
                resolved_user_id="test-user",
            )
            assert resp_scan is not None
            assert "標的池背景生命週期演化掃描已啟動" in resp_scan
            mock_delay.assert_called_once_with(user_id="test-user", force=True)
