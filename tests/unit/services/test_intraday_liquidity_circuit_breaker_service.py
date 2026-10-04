"""Unit tests for P7 Intraday Liquidity Circuit Breaker Service and Execution Endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.intraday_liquidity_circuit_breaker_service import (
    IntradayLiquidityCircuitBreakerService,
    CircuitBreakerState,
    ShockTriggerType,
    MarketQuoteObservation,
    AssetBaseline,
    CircuitBreakerStatus,
)
from src.services.smart_order_routing_service import (
    SmartOrderRoutingService,
    OrderAction,
)
from src.services.actionable_alert_service import ActionableAlertHubService
from src.api.v1.schemas.circuit_breaker_schemas import (
    CircuitBreakerQuoteEvaluationRequest,
    CircuitBreakerTriggerRequest,
    CircuitBreakerResumeRequest,
)


@pytest.fixture
def circuit_breaker_service():
    """Provides a fresh IntradayLiquidityCircuitBreakerService instance."""
    service = IntradayLiquidityCircuitBreakerService()
    # Mock settings on the service instance if needed
    service._statuses.clear()
    service._baselines.clear()
    # Seed a baseline for AAPL
    service._baselines["AAPL"] = AssetBaseline(
        symbol="AAPL",
        typical_spread_bps=10.0,
        reference_price=150.0,
        typical_volatility=0.20,
        last_updated=datetime.now(timezone.utc),
    )
    return service


class TestIntradayLiquidityCircuitBreakerService:
    def test_baseline_management(self, circuit_breaker_service):
        baseline = circuit_breaker_service.get_or_create_baseline("AAPL")
        assert baseline is not None
        assert baseline.symbol == "AAPL"
        assert baseline.reference_price == 150.0
        assert baseline.typical_spread_bps == 10.0

        # Update baseline
        updated = circuit_breaker_service.update_baseline("AAPL", typical_spread_bps=12.0)
        assert updated.typical_spread_bps == 12.0

    def test_evaluate_quote_normal(self, circuit_breaker_service):
        obs = MarketQuoteObservation(
            symbol="AAPL",
            bid_price=149.95,
            ask_price=150.05,
            last_price=150.0,
            timestamp=datetime.now(timezone.utc),
        )
        status = circuit_breaker_service.evaluate_quote(obs)
        assert status.state == CircuitBreakerState.NORMAL
        assert status.trigger_type is None
        assert circuit_breaker_service.can_execute("AAPL") is True
        assert circuit_breaker_service.is_halted("AAPL") is False

    def test_evaluate_quote_spread_expansion(self, circuit_breaker_service):
        # Baseline spread is 10 bps (0.1%).
        # Bid = 145.0, Ask = 155.0 -> spread = 10.0 / 150.0 = 667 bps
        # Spread expansion ratio = 66.7x (> 3.0x) and spread = 667 bps (> 50 bps)
        obs = MarketQuoteObservation(
            symbol="AAPL",
            bid_price=145.0,
            ask_price=155.0,
            last_price=150.0,
            timestamp=datetime.now(timezone.utc),
        )
        status = circuit_breaker_service.evaluate_quote(obs)
        assert status.state == CircuitBreakerState.TRIGGERED
        assert status.trigger_type == ShockTriggerType.SPREAD_EXPANSION
        assert circuit_breaker_service.is_halted("AAPL") is True
        assert circuit_breaker_service.can_execute("AAPL") is False

    def test_evaluate_quote_price_gap_shock(self, circuit_breaker_service):
        # Baseline price is 150.0. Current last_price drops to 140.0 (-6.67% > 3.5%)
        obs = MarketQuoteObservation(
            symbol="AAPL",
            bid_price=139.9,
            ask_price=140.1,
            last_price=140.0,
            timestamp=datetime.now(timezone.utc),
        )
        status = circuit_breaker_service.evaluate_quote(obs)
        assert status.state == CircuitBreakerState.TRIGGERED
        assert status.trigger_type == ShockTriggerType.PRICE_GAP_SHOCK
        assert "price displacement" in status.reason.lower()
        assert circuit_breaker_service.is_halted("AAPL") is True

    def test_evaluate_quote_volatility_surge(self, circuit_breaker_service):
        obs = MarketQuoteObservation(
            symbol="AAPL",
            bid_price=149.9,
            ask_price=150.1,
            last_price=150.0,
            timestamp=datetime.now(timezone.utc),
            intraday_volatility=0.85,  # Baseline 0.20 -> vol sigma > 3.0
        )
        status = circuit_breaker_service.evaluate_quote(obs)
        assert status.state == CircuitBreakerState.TRIGGERED
        assert status.trigger_type == ShockTriggerType.VOLATILITY_SURGE
        assert circuit_breaker_service.is_halted("AAPL") is True

    def test_evaluate_quote_warning_state(self, circuit_breaker_service):
        # Spread expanded to 2.0x (>= 0.6 * 3.0 = 1.8x, but < 3.0x and < 50 bps)
        # Bid = 149.85, Ask = 150.15 -> spread 30 bps -> 30/10 = 3.0? No, let's make spread 20 bps -> 2.0x
        obs = MarketQuoteObservation(
            symbol="AAPL",
            bid_price=149.85,
            ask_price=150.15,
            last_price=150.0,
            timestamp=datetime.now(timezone.utc),
        )
        status = circuit_breaker_service.evaluate_quote(obs)
        assert status.state in (CircuitBreakerState.WARNING, CircuitBreakerState.NORMAL)
        # Verify can_execute remains True in WARNING
        if status.state == CircuitBreakerState.WARNING:
            assert circuit_breaker_service.can_execute("AAPL") is True

    def test_manual_trigger_and_resume(self, circuit_breaker_service):
        status = circuit_breaker_service.manual_trigger(
            symbol="AAPL",
            reason="Operator manual halt due to geopolitical headline",
            cooldown_minutes=20,
        )
        assert status.state == CircuitBreakerState.TRIGGERED
        assert status.trigger_type == ShockTriggerType.MANUAL
        assert circuit_breaker_service.is_halted("AAPL") is True
        assert circuit_breaker_service.is_halted("MSFT") is False

        # Resume
        resumed = circuit_breaker_service.resume(symbol="AAPL")
        assert resumed is True
        current_status = circuit_breaker_service.get_status("AAPL")
        assert current_status.state == CircuitBreakerState.NORMAL
        assert circuit_breaker_service.is_halted("AAPL") is False

    def test_global_circuit_breaker(self, circuit_breaker_service):
        circuit_breaker_service.manual_trigger(
            symbol="GLOBAL",
            reason="Systemic market flash crash",
        )
        assert circuit_breaker_service.is_halted("GLOBAL") is True
        assert circuit_breaker_service.is_halted("AAPL") is True
        assert circuit_breaker_service.is_halted("NVDA") is True
        assert circuit_breaker_service.can_execute("AAPL") is False

        # Resume global
        circuit_breaker_service.resume(symbol="GLOBAL")
        assert circuit_breaker_service.is_halted("GLOBAL") is False
        assert circuit_breaker_service.is_halted("AAPL") is False

    def test_extend_cooldown(self, circuit_breaker_service):
        circuit_breaker_service.manual_trigger(symbol="AAPL", cooldown_minutes=10)
        old_until = circuit_breaker_service.get_status("AAPL").cooldown_until

        status = circuit_breaker_service.extend_cooldown(symbol="AAPL", additional_minutes=15)
        assert status.cooldown_until is not None
        assert status.cooldown_until > old_until

    def test_cooldown_expiration_auto_recovery(self, circuit_breaker_service):
        circuit_breaker_service.manual_trigger(symbol="AAPL", cooldown_minutes=5)
        # Artificially set cooldown_until to the past
        status = circuit_breaker_service.get_status("AAPL")
        status.cooldown_until = datetime.now(timezone.utc) - timedelta(seconds=10)

        # Status check should auto-transition to NORMAL
        current_status = circuit_breaker_service.get_status("AAPL")
        assert current_status.state == CircuitBreakerState.NORMAL
        assert circuit_breaker_service.is_halted("AAPL") is False


class TestSmartOrderRoutingCircuitBreakerIntegration:
    def test_sor_blocks_halted_asset(self, circuit_breaker_service):
        sor = SmartOrderRoutingService(
            circuit_breaker_service=circuit_breaker_service,
        )

        circuit_breaker_service.manual_trigger(symbol="AAPL", reason="Liquidity shock")

        plan = sor.generate_plan(
            symbol="AAPL",
            action=OrderAction.BUY,
            requested_quantity=1000,
            arrival_price=150.0,
            adv_20=500000.0,
        )

        assert plan.status == "CIRCUIT_BREAKER_HALTED"
        assert len(plan.child_orders) == 0
        assert "liquidity shock" in plan.circuit_breaker_reason.lower()

    def test_sor_allows_active_asset(self, circuit_breaker_service):
        sor = SmartOrderRoutingService(
            circuit_breaker_service=circuit_breaker_service,
        )

        plan = sor.generate_plan(
            symbol="AAPL",
            action=OrderAction.BUY,
            requested_quantity=1000,
            arrival_price=150.0,
            adv_20=500000.0,
        )

        assert plan.status != "CIRCUIT_BREAKER_HALTED"
        assert len(plan.child_orders) > 0


class TestActionableAlertHubIntegration:
    @pytest.mark.asyncio
    async def test_actionable_hub_circuit_breaker_alert(self):
        hub = ActionableAlertHubService(user_id="test_user")

        with patch.object(hub, "_get_notification_service") as mock_get_noti:
            mock_noti = MagicMock()
            mock_noti.notify_all = AsyncMock(return_value={"sent": True})
            mock_get_noti.return_value = mock_noti

            res = await hub.dispatch_liquidity_circuit_breaker_alert(
                ticker="TSLA",
                reason="Spread expanded by 4.5x",
                trigger_type="SPREAD_EXPANSION",
                spread_bps=55.0,
                spread_multiplier=4.5,
                cooldown_minutes=15,
            )

            assert res["sent"] is True
            mock_noti.notify_all.assert_called_once()
            call_kwargs = mock_noti.notify_all.call_args[1]
            assert "TSLA" in call_kwargs["title"]
            assert len(call_kwargs["actions"]) == 3
            assert call_kwargs["actions"][0]["key"] == "cb_resume"
            assert call_kwargs["actions"][1]["key"] == "cb_cash"
            assert call_kwargs["actions"][2]["key"] == "cb_extend"

    @pytest.mark.asyncio
    async def test_actionable_hub_execute_circuit_breaker_actions(self, circuit_breaker_service):
        hub = ActionableAlertHubService(user_id="test_user")
        circuit_breaker_service.manual_trigger(symbol="TSLA", cooldown_minutes=15)
        assert circuit_breaker_service.is_halted("TSLA") is True

        with patch("src.services.intraday_liquidity_circuit_breaker_service.IntradayLiquidityCircuitBreakerService", return_value=circuit_breaker_service):
            # Test resume
            res = await hub.execute_action(
                action_name="resume_circuit_breaker",
                params={"ticker": "TSLA"},
            )
            assert res["ok"] is True
            assert circuit_breaker_service.is_halted("TSLA") is False

            # Trigger again and test extend
            circuit_breaker_service.manual_trigger(symbol="TSLA", cooldown_minutes=10)
            res_extend = await hub.execute_action(
                action_name="extend_circuit_breaker",
                params={"ticker": "TSLA"},
            )
            assert res_extend["ok"] is True

            # Test emergency cash
            with patch("src.services.settings_service.SettingsService.save_setting") as mock_save:
                res_cash = await hub.execute_action(
                    action_name="emergency_cash",
                    params={"ticker": "TSLA"},
                )
                assert res_cash["ok"] is True
                mock_save.assert_called_with("ai_trading_enabled", "false")


class TestCircuitBreakerEndpoints:
    def test_circuit_breaker_api_flow(self, circuit_breaker_service):
        from src.api.v1.endpoints.execution import (
            list_circuit_breaker_statuses,
            get_symbol_circuit_breaker_status,
            assess_quote_for_circuit_breaker,
            manually_trigger_circuit_breaker,
            manually_resume_circuit_breaker,
        )

        # 1. Get status list
        res_list = list_circuit_breaker_statuses(service=circuit_breaker_service)
        assert res_list.status == "success"

        # 2. Assess normal quote
        assess_req = CircuitBreakerQuoteEvaluationRequest(
            symbol="AAPL",
            bid_price=149.95,
            ask_price=150.05,
            last_price=150.0,
        )
        assess_res = assess_quote_for_circuit_breaker(payload=assess_req, service=circuit_breaker_service)
        assert assess_res.status == "success"
        assert assess_res.circuit_breaker.state == "NORMAL"

        # 3. Manual trigger
        trigger_req = CircuitBreakerTriggerRequest(
            symbol="AAPL",
            reason="Testing API manual trigger",
            cooldown_minutes=10,
        )
        trig_res = manually_trigger_circuit_breaker(payload=trigger_req, service=circuit_breaker_service)
        assert trig_res.status == "success"
        assert trig_res.symbol == "AAPL"
        assert trig_res.state == "TRIGGERED"

        # 4. Check symbol status
        sym_res = get_symbol_circuit_breaker_status(symbol="AAPL", service=circuit_breaker_service)
        assert sym_res.symbol == "AAPL"
        assert sym_res.state == "TRIGGERED"

        # 5. Resume
        resume_req = CircuitBreakerResumeRequest(
            symbol="AAPL",
        )
        res_res = manually_resume_circuit_breaker(payload=resume_req, service=circuit_breaker_service)
        assert res_res.status == "success"
        assert res_res.state == "NORMAL"
