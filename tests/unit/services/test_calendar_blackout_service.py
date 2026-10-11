"""
Unit Tests for CalendarBlackoutService (宏觀事件與財報日避開守衛)
============================================================
涵蓋：
1. 聯準會 FOMC 利率決議與 BLS CPI/NFP 發布前後避開視窗
2. 個股財報日前後避開視窗 (Finnhub API + Redis 快取)
3. 設定開關與自定義視窗時間 (pre_hours, post_hours, pre_minutes, post_minutes)
4. 與 BatchCashDeploymentService 整合 (建倉清單標記、宏觀熔斷延後、個股延後且不提前推進批次)
5. 與 AutomatedTradingService 整合 (BUY 訂單攔截、SELL 訂單放行保障停損避險)
6. 與 ConversationRouter 整合 (/calendar 與 /guard 系統指令展現)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytz

from src.services.calendar_blackout_service import (
    BlackoutDecision,
    CalendarBlackoutService,
)
from src.services.batch_cash_deployment_service import (
    BatchCashDeploymentService,
)
from src.domain.trading import Order, OrderAction, OrderType


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


class TestCalendarBlackoutService:
    @pytest.fixture
    def ny_tz(self):
        return pytz.timezone("US/Eastern")

    @pytest.fixture
    def default_service(self):
        settings = DummySettingsService({
            "enable_earnings_blackout_guard": True,
            "earnings_blackout_pre_hours": 48.0,
            "earnings_blackout_post_hours": 24.0,
            "enable_macro_calendar_blackout_guard": True,
            "macro_blackout_pre_minutes": 60,
            "macro_blackout_post_minutes": 30,
            "source_finnhub_api_key": "dummy_test_token",
        })
        return CalendarBlackoutService(
            user_id="test_user_id",
            settings_service=settings,
        )

    def test_macro_blackout_fomc_pre_event(self, default_service, ny_tz):
        # FOMC 於 2026-10-28 14:00 發布
        # 測試 2026-10-28 13:30 EST (發布前 30 分鐘 -> 處於 60 分鐘保護窗口內)
        eval_time = ny_tz.localize(datetime(2026, 10, 28, 13, 30))
        decision = default_service.evaluate_macro_blackout(now_dt=eval_time)

        assert decision.is_blackout is True
        assert decision.event_type == "MACRO"
        assert "FOMC" in (decision.event_name or "")
        assert decision.recommended_action == "DEFER"
        assert "流動性保護避開窗口" in decision.reason

    def test_macro_blackout_fomc_post_event(self, default_service, ny_tz):
        # 測試 2026-10-28 14:15 EST (發布後 15 分鐘 -> 處於 30 分鐘沉澱期內)
        eval_time = ny_tz.localize(datetime(2026, 10, 28, 14, 15))
        decision = default_service.evaluate_macro_blackout(now_dt=eval_time)

        assert decision.is_blackout is True
        assert decision.event_type == "MACRO"
        assert decision.recommended_action == "DEFER"
        assert "市場吸收沉澱期" in decision.reason

    def test_macro_blackout_safe_window(self, default_service, ny_tz):
        # 測試 2026-10-28 10:00 EST (發布前 4 小時 -> 安全窗口)
        eval_time = ny_tz.localize(datetime(2026, 10, 28, 10, 0))
        decision = default_service.evaluate_macro_blackout(now_dt=eval_time)

        assert decision.is_blackout is False
        assert decision.recommended_action == "PROCEED"
        assert "安全" in decision.reason

    def test_macro_blackout_cpi_event(self, default_service, ny_tz):
        # CPI 於 2026-10-14 08:30 發布
        # 測試 2026-10-14 08:10 EST (發布前 20 分鐘)
        eval_time = ny_tz.localize(datetime(2026, 10, 14, 8, 10))
        decision = default_service.evaluate_macro_blackout(now_dt=eval_time)

        assert decision.is_blackout is True
        assert decision.event_type == "MACRO"
        assert "CPI" in (decision.event_name or "")
        assert decision.recommended_action == "DEFER"

    def test_macro_blackout_disabled_by_setting(self, ny_tz):
        settings = DummySettingsService({
            "enable_macro_calendar_blackout_guard": False,
        })
        svc = CalendarBlackoutService(user_id="u1", settings_service=settings)
        eval_time = ny_tz.localize(datetime(2026, 10, 28, 13, 50))
        decision = svc.evaluate_macro_blackout(now_dt=eval_time)

        assert decision.is_blackout is False
        assert "關閉" in decision.reason

    @pytest.mark.asyncio
    async def test_earnings_blackout_pre_release(self, default_service, ny_tz):
        # 模擬 MSFT 財報發布於 2026-10-28 AMC (16:30 EST)
        mock_earnings = {
            "symbol": "MSFT",
            "date": "2026-10-28",
            "hour": "amc",
            "quarter": 1,
            "year": 2027,
        }
        default_service.fetch_earnings_calendar = AsyncMock(return_value=mock_earnings)

        # 評估時間：2026-10-27 10:00 EST (距離發布尚有約 30.5 小時，落入 48h 保護視窗)
        now_dt = ny_tz.localize(datetime(2026, 10, 27, 10, 0))
        decision = await default_service.evaluate_earnings_blackout("MSFT", now_dt=now_dt)

        assert decision.is_blackout is True
        assert decision.event_type == "EARNINGS"
        assert decision.recommended_action == "DEFER"
        assert decision.timing == "amc"
        assert "處於財報保護避開視窗" in decision.reason

    @pytest.mark.asyncio
    async def test_earnings_blackout_post_release(self, default_service, ny_tz):
        # 模擬 AMD 財報發布於 2026-11-03 AMC (16:30 EST)
        mock_earnings = {
            "symbol": "AMD",
            "date": "2026-11-03",
            "hour": "amc",
            "quarter": 3,
            "year": 2026,
        }
        default_service.fetch_earnings_calendar = AsyncMock(return_value=mock_earnings)

        # 評估時間：2026-11-04 09:40 EST (已發布約 17 小時，處於 24h 消化沉澱期)
        now_dt = ny_tz.localize(datetime(2026, 11, 4, 9, 40))
        decision = await default_service.evaluate_earnings_blackout("AMD", now_dt=now_dt)

        assert decision.is_blackout is True
        assert decision.event_type == "EARNINGS"
        assert "波動沉澱" in decision.reason

    @pytest.mark.asyncio
    async def test_earnings_blackout_safe_window(self, default_service, ny_tz):
        # 模擬 MU 財報於 2026-09-30 發布，評估時間為 2026-10-11 (已過 11 天，遠超出 24h 沉澱期)
        mock_earnings = {
            "symbol": "MU",
            "date": "2026-09-30",
            "hour": "amc",
            "quarter": 4,
            "year": 2026,
        }
        default_service.fetch_earnings_calendar = AsyncMock(return_value=mock_earnings)

        now_dt = ny_tz.localize(datetime(2026, 10, 11, 9, 30))
        decision = await default_service.evaluate_earnings_blackout("MU", now_dt=now_dt)

        assert decision.is_blackout is False
        assert decision.recommended_action == "PROCEED"
        assert "安全交易區間" in decision.reason

    @pytest.mark.asyncio
    async def test_earnings_blackout_disabled_by_setting(self, ny_tz):
        settings = DummySettingsService({
            "enable_earnings_blackout_guard": False,
        })
        svc = CalendarBlackoutService(user_id="u1", settings_service=settings)
        svc.fetch_earnings_calendar = AsyncMock(return_value={"symbol": "NVDA", "date": "2026-10-12"})
        now_dt = ny_tz.localize(datetime(2026, 10, 12, 8, 0))

        decision = await svc.evaluate_earnings_blackout("NVDA", now_dt=now_dt)
        assert decision.is_blackout is False
        assert "關閉" in decision.reason

    @pytest.mark.asyncio
    async def test_candidate_evaluation_priority(self, default_service, ny_tz):
        # 當同時評估候選標的時，宏觀黑名單優先於個股財報
        # 設置宏觀黑名單觸發時間 (FOMC 2026-10-28 13:45 EST)
        now_dt = ny_tz.localize(datetime(2026, 10, 28, 13, 45))
        decision = await default_service.evaluate_candidate("AAPL", now_dt=now_dt)

        assert decision.is_blackout is True
        assert decision.event_type == "MACRO"

    @pytest.mark.asyncio
    async def test_upcoming_calendar_summary(self, default_service, ny_tz):
        default_service.fetch_earnings_calendar = AsyncMock(side_effect=lambda sym, **kw: {
            "symbol": sym,
            "date": "2026-10-28" if sym == "MSFT" else "2026-11-03",
            "hour": "amc",
        })
        now_dt = ny_tz.localize(datetime(2026, 10, 11, 9, 30))
        summary = await default_service.get_upcoming_calendar_summary(["MSFT", "AMD"], now_dt=now_dt)

        assert "macro_status" in summary
        assert "tickers" in summary
        assert "MSFT" in summary["tickers"]
        assert "AMD" in summary["tickers"]
        assert summary["tickers"]["MSFT"]["date"] == "2026-10-28"


class TestBatchDeploymentBlackoutIntegration:
    @pytest.fixture
    def mock_deps(self):
        settings = DummySettingsService({
            "enable_earnings_blackout_guard": True,
            "enable_macro_calendar_blackout_guard": True,
            "enable_slippage_guard": True,
            "enable_market_open_cash_deployment": True,
            "batch_cash_deployment_portion": 0.33,
        })
        broker = MagicMock()
        broker.get_positions = AsyncMock(return_value=[])
        slippage_guard = MagicMock()
        slippage_guard.is_opening_auction_window.return_value = (False, "安全窗口")
        slippage_guard._nyse_tz = pytz.timezone("US/Eastern")
        slippage_guard._get_setting_int.return_value = 5

        # Mock slippage evaluation passed
        from src.services.slippage_guard_service import SlippageGuardDecision
        slippage_guard.evaluate_trade = AsyncMock(return_value=SlippageGuardDecision(
            passed=True,
            reason="Passed",
            spread_pct=0.0005,
            adaptive_limit_price=100.0,
        ))

        market_clock = MagicMock()
        market_clock.is_market_open.return_value = True

        blackout_guard = MagicMock()
        blackout_guard.evaluate_macro_blackout.return_value = BlackoutDecision(
            is_blackout=False,
            reason="宏觀安全",
            recommended_action="PROCEED",
        )
        blackout_guard.get_upcoming_calendar_summary = AsyncMock(return_value={"macro_status": {}, "tickers": {}})

        return {
            "settings": settings,
            "broker": broker,
            "slippage_guard": slippage_guard,
            "market_clock": market_clock,
            "blackout_guard": blackout_guard,
        }

    @pytest.mark.asyncio
    async def test_deployment_plan_marks_blackout_candidate(self, mock_deps):
        svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=mock_deps["settings"],
            broker=mock_deps["broker"],
            slippage_guard=mock_deps["slippage_guard"],
            market_clock=mock_deps["market_clock"],
            blackout_guard=mock_deps["blackout_guard"],
        )

        # Mock portfolio status: $1000 equity, $500 available cash ($300 deployable)
        svc.get_portfolio_status = AsyncMock(return_value={
            "total_equity": 1000.0,
            "available_cash": 500.0,
            "deployable_cash": 300.0,
            "required_reserve_usd": 200.0,
            "holdings": {},
        })

        # Mock blackout evaluation: MSFT is in blackout, MU and AMD are safe
        async def mock_eval_candidate(ticker, **kw):
            if ticker == "MSFT":
                return BlackoutDecision(
                    is_blackout=True,
                    reason="MSFT 財報發布前 24h 避開",
                    event_type="EARNINGS",
                    recommended_action="DEFER",
                )
            return BlackoutDecision(is_blackout=False, reason="安全", recommended_action="PROCEED")

        mock_deps["blackout_guard"].evaluate_candidate = AsyncMock(side_effect=mock_eval_candidate)

        plan = await svc.get_deployment_plan(batch_number=2)
        assert "calendar_summary" in plan

        all_candidates = plan["all_candidates"]
        msft_cand = next(c for c in all_candidates if c["ticker"] == "MSFT")
        assert msft_cand["blackout_active"] is True
        assert msft_cand["amount_usd"] == 0.0

        # Executable items should only contain non-blackout candidates
        item_tickers = [i["ticker"] for i in plan["items"]]
        assert "MSFT" not in item_tickers

    @pytest.mark.asyncio
    async def test_execute_batch_macro_blackout_deferred(self, mock_deps):
        svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=mock_deps["settings"],
            broker=mock_deps["broker"],
            slippage_guard=mock_deps["slippage_guard"],
            market_clock=mock_deps["market_clock"],
            blackout_guard=mock_deps["blackout_guard"],
        )

        # 模擬宏觀避開觸發 (FOMC)
        mock_deps["blackout_guard"].evaluate_macro_blackout.return_value = BlackoutDecision(
            is_blackout=True,
            reason="FOMC 發布前 30 分鐘，暫緩開倉",
            event_type="MACRO",
            event_name="FOMC 利率決議",
            recommended_action="DEFER",
        )

        res = await svc.execute_batch(batch_number=2, force=False)
        assert res["success"] is False
        assert res["status"] == "macro_blackout_deferred"
        assert "FOMC" in res["message"]

    @pytest.mark.asyncio
    async def test_execute_batch_candidate_earnings_deferred_and_no_skip(self, mock_deps):
        svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=mock_deps["settings"],
            broker=mock_deps["broker"],
            slippage_guard=mock_deps["slippage_guard"],
            market_clock=mock_deps["market_clock"],
            blackout_guard=mock_deps["blackout_guard"],
        )

        # Plan contains MU ($50) and MSFT ($50)
        svc.get_deployment_plan = AsyncMock(return_value={
            "batch_number": 2,
            "can_execute": True,
            "status": {"deployable_cash": 200.0, "available_cash": 500.0, "required_reserve_usd": 200.0},
            "items": [
                {"ticker": "MU", "amount_usd": 50.0, "confidence_score": 85, "role": "記憶體", "rationale": "MU"},
                {"ticker": "MSFT", "amount_usd": 50.0, "confidence_score": 90, "role": "雲端", "rationale": "MSFT"},
            ],
        })
        svc.get_portfolio_status = AsyncMock(return_value={"total_equity": 1000.0, "available_cash": 450.0, "deployable_cash": 150.0})
        svc._send_deployment_notification = AsyncMock()

        # MSFT is in blackout; MU is safe
        async def mock_eval_candidate(ticker, **kw):
            if ticker == "MSFT":
                return BlackoutDecision(is_blackout=True, reason="財報避開", event_type="EARNINGS")
            return BlackoutDecision(is_blackout=False, reason="安全")

        mock_deps["blackout_guard"].evaluate_candidate = AsyncMock(side_effect=mock_eval_candidate)

        with patch("src.services.automated_trading_service.AutomatedTradingService") as MockTradeSvc:
            trade_inst = MockTradeSvc.return_value
            trade_inst.evaluate_and_execute_trade = AsyncMock(return_value={"status": "executed", "order_id": "ord_mu"})

            with patch("src.infrastructure.cache.redis_client.get_redis") as mock_get_redis:
                mock_redis = AsyncMock()
                mock_get_redis.return_value = mock_redis

                res = await svc.execute_batch(batch_number=2, force=False)
                trades = res["executed_trades"]

                # MU should be executed
                mu_trade = next(t for t in trades if t["ticker"] == "MU")
                assert mu_trade["status"] == "executed"

                # MSFT should be blackout_deferred
                msft_trade = next(t for t in trades if t["ticker"] == "MSFT")
                assert msft_trade["status"] == "blackout_deferred"

                # Batch number should NOT advance to 3 because MSFT was deferred!
                set_calls = mock_redis.set.call_args_list
                batch_advance_calls = [c for c in set_calls if "batch_deployment:current_batch" in str(c)]
                # Since not all fulfilled, current_batch was not advanced to "3"
                for call in batch_advance_calls:
                    assert call.args[1] != "3"


class TestAutomatedTradingBlackoutIntegration:
    @pytest.mark.asyncio
    async def test_automated_trading_blocks_buy_during_blackout(self):
        from src.services.automated_trading_service import AutomatedTradingService
        from src.repositories.settings_repository import AlchemySettingsRepository

        settings_repo = DummySettingsService({
            "enable_earnings_blackout_guard": True,
            "enable_slippage_guard": False,
        })
        trading_service = AutomatedTradingService(
            settings_repo=settings_repo,
            notification_service=MagicMock(),
        )

        order = Order(
            symbol="MSFT",
            action=OrderAction.BUY,
            quantity=50.0,
            amount_usd=50.0,
            order_type=OrderType.MARKET,
        )

        with patch("src.services.broker_factory.BrokerFactory.get_broker") as mock_get_broker:
            mock_broker = MagicMock()
            mock_broker.get_name.return_value = "TestBroker"
            mock_get_broker.return_value = mock_broker

            with patch("src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_candidate") as mock_eval:
                mock_eval.return_value = BlackoutDecision(
                    is_blackout=True,
                    reason="MSFT 處於財報發布前 48h 保護視窗",
                    event_type="EARNINGS",
                )

                result = await trading_service._execute_trade(
                    user_id="test_user",
                    order=order,
                    confidence_score=90,
                    rationale="Test",
                    approval_type="AUTO",
                )

                assert result["status"] == "blocked"
                assert result.get("blackout_guard") is True
                assert "財報發布前" in result["reason"]
                # Broker execute_order should never be called
                mock_broker.execute_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_automated_trading_allows_sell_during_blackout(self):
        from src.services.automated_trading_service import AutomatedTradingService

        settings_repo = DummySettingsService({
            "enable_earnings_blackout_guard": True,
            "enable_slippage_guard": False,
        })
        trading_service = AutomatedTradingService(
            settings_repo=settings_repo,
            notification_service=MagicMock(),
        )

        # SELL order for stop loss or risk-off exit
        order = Order(
            symbol="MSFT",
            action=OrderAction.SELL,
            quantity=10.0,
            order_type=OrderType.MARKET,
        )

        with patch("src.services.broker_factory.BrokerFactory.get_broker") as mock_get_broker:
            mock_broker = MagicMock()
            mock_broker.get_name.return_value = "TestBroker"
            mock_broker.execute_order = AsyncMock(return_value={"status": "success", "order_id": "sell_123"})
            mock_get_broker.return_value = mock_broker

            with patch("src.services.order_inflight_lock_service.OrderInflightLockService.acquire_lock", new_callable=AsyncMock):
                with patch("src.services.order_inflight_lock_service.OrderInflightLockService.release_lock", new_callable=AsyncMock):
                    with patch.object(trading_service, "_record_order_transaction", new_callable=AsyncMock):
                        result = await trading_service._execute_trade(
                            user_id="test_user",
                            order=order,
                            confidence_score=80,
                            rationale="Stop loss exit",
                            approval_type="AUTO",
                        )

                        # SELL order should proceed directly to broker even during blackout!
                        assert result.get("status") == "success"
                        mock_broker.execute_order.assert_called_once()


class TestConversationRouterCalendarIntegration:
    @pytest.mark.asyncio
    async def test_router_handles_calendar_command(self):
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()
        assert router._is_system_command("/calendar") is True
        assert router._is_system_command("行事曆") is True
        assert router._is_system_command("/earnings") is True

        with patch("src.services.calendar_blackout_service.CalendarBlackoutService.get_upcoming_calendar_summary") as mock_summary:
            mock_summary.return_value = {
                "macro_status": {
                    "is_blackout": False,
                    "next_event": {
                        "name": "美國 9 月 CPI 通膨報告",
                        "time": "2026-10-14 08:30",
                        "type": "CPI",
                        "hours_away": 74.4,
                        "days_away": 3.1,
                    },
                },
                "tickers": {
                    "MSFT": {
                        "ticker": "MSFT",
                        "is_blackout": False,
                        "display": "2026-10-28",
                        "hours_to_event": 400.0,
                    }
                },
            }

            resp = await router._handle_system_command(
                adapter=MagicMock(),
                channel_user_id="test_tg",
                text="/calendar",
                resolved_user_id="00000000-0000-4000-a000-000000000001",
            )

            assert resp is not None
            assert "宏觀行事曆與企業財報避開守衛總覽" in resp
            assert "美國 9 月 CPI 通膨報告" in resp
            assert "MSFT" in resp

    @pytest.mark.asyncio
    async def test_router_guard_includes_calendar_status(self):
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()
        assert router._is_system_command("/guard") is True

        with patch("src.services.slippage_guard_service.SlippageGuardService.is_opening_auction_window", return_value=(False, "安全")):
            with patch("src.services.calendar_blackout_service.CalendarBlackoutService.evaluate_macro_blackout") as mock_macro:
                mock_macro.return_value = BlackoutDecision(is_blackout=False, reason="安全")
                with patch("src.services.calendar_blackout_service.CalendarBlackoutService.get_upcoming_calendar_summary") as mock_sum:
                    mock_sum.return_value = {
                        "macro_status": {
                            "next_event": {"name": "FOMC", "time": "2026-10-28 14:00", "days_away": 17.0}
                        },
                        "tickers": {},
                    }

                    resp = await router._handle_system_command(
                        adapter=MagicMock(),
                        channel_user_id="test_tg",
                        text="/guard",
                        resolved_user_id="00000000-0000-4000-a000-000000000001",
                    )

                    assert resp is not None
                    assert "宏觀行事曆發布避開" in resp
                    assert "財報日前後避開保護" in resp
