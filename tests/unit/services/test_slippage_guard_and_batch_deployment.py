"""
Unit Tests for Slippage Guard and Batch Cash Deployment Service
==============================================================
測試開盤極端波動率防線、即時買賣價差熔斷守衛、自適應限價保護、階梯式分批建倉與交易整合。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytz

from src.services.slippage_guard_service import (
    SlippageGuardDecision,
    SlippageGuardService,
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


class TestSlippageGuardService:
    @pytest.fixture
    def slippage_svc(self):
        settings = DummySettingsService({
            "enable_slippage_guard": True,
            "max_allowed_spread_pct": 0.0015,
            "market_open_delay_minutes": 5,
            "slippage_warning_pct": 0.0020,
        })
        market_data = MagicMock()
        return SlippageGuardService(
            user_id="test_user",
            settings_service=settings,
            market_data_service=market_data,
        )

    def test_opening_auction_window_detection(self, slippage_svc):
        ny_tz = pytz.timezone("US/Eastern")
        
        # 1. Friday 09:32 EST -> Inside 5-min opening window
        dt_opening = ny_tz.localize(datetime(2026, 10, 9, 9, 32, 0))
        is_opening, reason = slippage_svc.is_opening_auction_window(ny_now=dt_opening)
        assert is_opening is True
        assert "美股開盤前 5 分鐘極端波動保護窗口" in reason

        # 2. Friday 09:36 EST -> Past 5-min opening window
        dt_past = ny_tz.localize(datetime(2026, 10, 9, 9, 36, 0))
        is_past, reason_past = slippage_svc.is_opening_auction_window(ny_now=dt_past)
        assert is_past is False
        assert "開盤緩衝期已過" in reason_past

        # 3. Friday 09:15 EST -> Pre-market before 09:30
        dt_pre = ny_tz.localize(datetime(2026, 10, 9, 9, 15, 0))
        is_pre, _ = slippage_svc.is_opening_auction_window(ny_now=dt_pre)
        assert is_pre is False

        # 4. Saturday 09:32 EST -> Weekend
        dt_weekend = ny_tz.localize(datetime(2026, 10, 10, 9, 32, 0))
        is_weekend, reason_wk = slippage_svc.is_opening_auction_window(ny_now=dt_weekend)
        assert is_weekend is False
        assert "週末" in reason_wk

    def test_spread_circuit_breaker_triggers_on_wide_spread(self, slippage_svc):
        async def _test():
            # Mock quote with wide spread: Bid $100.00, Ask $100.30 -> spread 0.30% > 0.15%
            slippage_svc.get_ticker_quote = AsyncMock(return_value={
                "ticker": "NVDA",
                "bid": 100.00,
                "ask": 100.30,
                "mid": 100.15,
                "spread": 0.30,
                "spread_pct": 0.30 / 100.15,  # ~0.00299 > 0.0015
                "last": 100.15,
                "source": "mock_test",
            })

            decision = await slippage_svc.evaluate_trade(
                ticker="NVDA",
                action="BUY",
                amount_usd=100.0,
                check_opening_window=False,
            )

            assert decision.passed is False
            assert decision.circuit_breaker_triggered is True
            assert decision.recommended_action == "DEFER"
            assert "觸發價差熔斷保護" in decision.reason

        asyncio.run(_test())

    def test_spread_circuit_breaker_passes_on_tight_spread(self, slippage_svc):
        async def _test():
            # Mock quote with tight spread: Bid $200.00, Ask $200.10 -> spread 0.05% < 0.15%
            slippage_svc.get_ticker_quote = AsyncMock(return_value={
                "ticker": "TSM",
                "bid": 200.00,
                "ask": 200.10,
                "mid": 200.05,
                "spread": 0.10,
                "spread_pct": 0.10 / 200.05,  # ~0.000499 < 0.0015
                "last": 200.05,
                "source": "mock_test",
            })

            decision = await slippage_svc.evaluate_trade(
                ticker="TSM",
                action="BUY",
                amount_usd=100.0,
                check_opening_window=False,
            )

            assert decision.passed is True
            assert decision.circuit_breaker_triggered is False
            assert decision.recommended_action == "PROCEED"
            assert decision.adaptive_limit_price is not None
            assert decision.adaptive_limit_price >= 200.10

        asyncio.run(_test())

    def test_opening_window_blocks_even_with_tight_spread(self, slippage_svc):
        async def _test():
            slippage_svc.is_opening_auction_window = MagicMock(return_value=(True, "開盤前 5 分鐘極端波動保護窗口"))
            slippage_svc.get_ticker_quote = AsyncMock(return_value={
                "ticker": "AAPL",
                "bid": 200.00,
                "ask": 200.05,
                "mid": 200.025,
                "spread_pct": 0.00025,
            })

            decision = await slippage_svc.evaluate_trade(
                ticker="AAPL",
                action="BUY",
                amount_usd=50.0,
                check_opening_window=True,
            )

            assert decision.passed is False
            assert decision.is_opening_window is True
            assert decision.circuit_breaker_triggered is True
            assert decision.recommended_action == "DEFER"

        asyncio.run(_test())

    def test_disabled_slippage_guard_passes(self):
        async def _test():
            settings = DummySettingsService({"enable_slippage_guard": False})
            svc = SlippageGuardService(user_id="test_user", settings_service=settings)

            decision = await svc.evaluate_trade("NVDA", "BUY")
            assert decision.passed is True
            assert "已由使用者設定關閉" in decision.reason

        asyncio.run(_test())

    def test_record_realized_slippage(self, slippage_svc):
        # BUY: expected 100, filled 100.30 -> slippage +0.30% > 0.20% warning threshold
        with patch("src.repositories.event_queue_repository.EventQueueRepository.insert_event") as mock_insert:
            slip = slippage_svc.record_realized_slippage(
                ticker="NVDA",
                action="BUY",
                expected_price=100.0,
                fill_price=100.30,
                order_id="test_ord_1",
            )
            assert round(slip, 4) == 0.003
            mock_insert.assert_called_once()
            call_kwargs = mock_insert.call_args[1]
            assert call_kwargs["event_type"] == "slippage_warning"
            assert call_kwargs["content"]["ticker"] == "NVDA"


class TestBatchCashDeploymentService:
    @pytest.fixture
    def deployment_svc(self):
        settings = DummySettingsService({
            "target_cash_ratio": 0.20,
            "enable_slippage_guard": True,
            "max_allowed_spread_pct": 0.0015,
        })
        broker = MagicMock()
        account = MagicMock()
        account.total_equity = 1692.50
        account.available_cash = 1404.09
        broker.get_account = AsyncMock(return_value=account)

        pos_aapl = MagicMock()
        pos_aapl.symbol = "AAPL"
        pos_aapl.market_value = 80.20
        broker.get_positions = AsyncMock(return_value=[pos_aapl])

        guard = MagicMock()
        guard.is_opening_auction_window.return_value = (False, "正常時段")
        guard.evaluate_trade = AsyncMock(return_value=SlippageGuardDecision(
            passed=True,
            reason="價差合格",
            spread_pct=0.0005,
            adaptive_limit_price=120.0,
        ))

        clock = MagicMock()
        clock.is_market_open.return_value = True

        svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=settings,
            broker=broker,
            slippage_guard=guard,
            market_clock=clock,
        )
        return svc

    def test_portfolio_status_preserves_defensive_cash(self, deployment_svc):
        async def _test():
            status = await deployment_svc.get_portfolio_status()
            assert status["total_equity"] == 1692.50
            assert status["available_cash"] == 1404.09
            # Defensive reserve 20% of 1692.50 = 338.50
            assert status["required_reserve_usd"] == 338.50
            # Deployable = 1404.09 - 338.50 = 1065.59
            assert status["deployable_cash"] == 1065.59

        asyncio.run(_test())

    def test_get_deployment_plan_batch_1(self, deployment_svc):
        async def _test():
            with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository.get_target_allocations") as mock_targets:
                mock_targets.return_value = [
                    {"ticker": "AAPL", "target_weight": 0.1127, "confidence_score": 0.686},
                    {"ticker": "NVDA", "target_weight": 0.0673, "confidence_score": 0.686},
                    {"ticker": "TSM", "target_weight": 0.0850, "confidence_score": 0.669},
                ]

                plan = await deployment_svc.get_deployment_plan(batch_number=1)
                assert plan["batch_number"] == 1
                assert plan["can_execute"] is True
                items = plan["items"]
                assert len(items) == 3
                tickers = [i["ticker"] for i in items]
                assert "NVDA" in tickers
                assert "TSM" in tickers
                assert "AAPL" in tickers
                # Total Batch 1 amount is ~$347.00
                assert plan["total_batch_amount"] == 347.00
                # Post-batch remaining cash ~$1057.09
                assert plan["expected_remaining_cash"] == 1057.09
                assert plan["expected_cash_ratio"] >= 60.0

        asyncio.run(_test())

    def test_execute_batch_1_success(self, deployment_svc):
        async def _test():
            with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository.get_target_allocations") as mock_targets, \
                 patch("src.services.automated_trading_service.AutomatedTradingService.evaluate_and_execute_trade") as mock_exec, \
                 patch("src.services.notification_service.NotificationService.notify_all") as mock_notify:

                mock_targets.return_value = [
                    {"ticker": "AAPL", "target_weight": 0.1127, "confidence_score": 0.686},
                    {"ticker": "NVDA", "target_weight": 0.0673, "confidence_score": 0.686},
                    {"ticker": "TSM", "target_weight": 0.0850, "confidence_score": 0.669},
                ]
                mock_exec.return_value = {"status": "executed", "order_id": "order_123"}
                mock_notify.return_value = AsyncMock()

                result = await deployment_svc.execute_batch(batch_number=1, force=True)
                assert result["success"] is True
                assert len(result["executed_trades"]) == 3
                assert all(t["status"] == "executed" for t in result["executed_trades"])

        asyncio.run(_test())

    def test_execute_batch_circuit_breaker_defers_trade(self, deployment_svc):
        async def _test():
            # Slippage guard triggers circuit breaker on wide spread
            deployment_svc.slippage_guard.evaluate_trade = AsyncMock(return_value=SlippageGuardDecision(
                passed=False,
                reason="價差 0.25% 超過 0.15% 門檻",
                circuit_breaker_triggered=True,
                spread_pct=0.0025,
                recommended_action="DEFER",
            ))

            with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository.get_target_allocations") as mock_targets, \
                 patch("src.services.notification_service.NotificationService.notify_all") as mock_notify:

                mock_targets.return_value = [
                    {"ticker": "AAPL", "target_weight": 0.1127, "confidence_score": 0.686},
                    {"ticker": "NVDA", "target_weight": 0.0673, "confidence_score": 0.686},
                    {"ticker": "TSM", "target_weight": 0.0850, "confidence_score": 0.669},
                ]
                mock_notify.return_value = AsyncMock()

                result = await deployment_svc.execute_batch(batch_number=1, force=False)
                assert result["success"] is False
                assert all(t["status"] == "circuit_breaker_deferred" for t in result["executed_trades"])

        asyncio.run(_test())


class TestAutomatedTradingSlippageIntegration:
    def test_automated_trading_blocks_on_slippage_guard(self):
        async def _test():
            from src.services.automated_trading_service import AutomatedTradingService
            settings = DummySettingsService({
                "enable_slippage_guard": True,
                "auto_trade_threshold": 7.5,
            })
            trading_svc = AutomatedTradingService(
                settings_repo=settings,
                notification_service=MagicMock(),
            )

            with patch("src.services.broker_factory.BrokerFactory.get_broker") as mock_bf, \
                 patch("src.services.slippage_guard_service.SlippageGuardService.evaluate_trade") as mock_guard:

                mock_broker = MagicMock()
                mock_broker.get_name.return_value = "MockBroker"
                mock_bf.return_value = mock_broker

                mock_guard.return_value = SlippageGuardDecision(
                    passed=False,
                    reason="開盤波動保護視窗暫緩下單",
                    circuit_breaker_triggered=True,
                    is_opening_window=True,
                )

                order = Order(
                    symbol="NVDA",
                    action=OrderAction.BUY,
                    quantity=114.0,
                    price=120.0,
                )

                result = await trading_svc._execute_trade(
                    user_id="test_user",
                    order=order,
                    confidence_score=8.5,
                    rationale="Test",
                    approval_type="自動執行",
                )

                assert result["status"] == "blocked"
                assert result["circuit_breaker_triggered"] is True
                assert "開盤波動保護視窗暫緩下單" in result["reason"]
                mock_broker.execute_order.assert_not_called()

        asyncio.run(_test())
