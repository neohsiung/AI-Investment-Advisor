"""
Unit Tests for Strategy Contract & Market Regime Domain Models
==============================================================
驗證市場體制、風險預算、階梯調度、降槓桿規則與策略契約領域模型。
"""
import pytest
from datetime import datetime, timezone

from src.domain.strategy_contract import (
    MarketRegimeType,
    MarketRegimeEvent,
    RiskBudget,
    LadderStage,
    DeleveragingRule,
    StrategyExecutionPlan,
    StrategyContract,
)


class DummyTestStrategyContract(StrategyContract):
    def __init__(self):
        self.strategy_id = "dummy_test_strategy"
        self.subscribed_regimes = [MarketRegimeType.VOLATILITY_EXTREME]
        self.risk_budget = RiskBudget(
            max_underlying_stop_pct=4.0,
            trailing_stop_pct=3.0,
            max_position_margin_pct=0.05,
            max_holding_days=30,
            max_portfolio_gross_leverage=1.30,
            max_allowed_leverage=5,
        )

    def evaluate_entry(self, market_context):
        if market_context.get("trigger"):
            return StrategyExecutionPlan(
                action="BUY",
                stage=1,
                target_leverage=5,
                target_cumulative_weight=0.5,
                incremental_weight=0.5,
                stop_loss_pct=3.5,
                is_trailing_stop_loss=True,
                reason="Dummy entry triggered",
            )
        return None

    def evaluate_exit(self, position, market_context):
        if market_context.get("exit"):
            return StrategyExecutionPlan(
                action="SELL",
                stage=0,
                target_leverage=1,
                reason="Dummy exit triggered",
            )
        return None


class TestStrategyContractDomain:
    def test_market_regime_types(self):
        """Verify all standard market regime types exist."""
        assert MarketRegimeType.VOLATILITY_EXTREME.value == "VOLATILITY_EXTREME"
        assert MarketRegimeType.VOLATILITY_PIVOT.value == "VOLATILITY_PIVOT"
        assert MarketRegimeType.TREND_ACCELERATION.value == "TREND_ACCELERATION"
        assert MarketRegimeType.RANGE_COMPRESSION.value == "RANGE_COMPRESSION"
        assert MarketRegimeType.LIQUIDITY_SHOCK.value == "LIQUIDITY_SHOCK"
        assert MarketRegimeType.NORMAL.value == "NORMAL"

    def test_market_regime_event_creation(self):
        """Verify MarketRegimeEvent records indicators and metadata."""
        now = datetime.now(timezone.utc)
        event = MarketRegimeEvent(
            regime_type=MarketRegimeType.VOLATILITY_EXTREME,
            severity="critical",
            confidence=0.95,
            indicators={"vix": 52.4, "ma5": 48.0},
            timestamp=now,
        )
        assert event.regime_type == MarketRegimeType.VOLATILITY_EXTREME
        assert event.severity == "critical"
        assert event.confidence == 0.95
        assert event.indicators["vix"] == 52.4
        assert event.timestamp == now

    def test_risk_budget_defaults_and_constraints(self):
        """Verify RiskBudget default values and explicit parametrization."""
        default_budget = RiskBudget()
        assert default_budget.max_underlying_stop_pct == 8.0
        assert default_budget.trailing_stop_pct == 6.0
        assert default_budget.max_position_margin_pct == 0.10
        assert default_budget.max_portfolio_gross_leverage == 1.30
        assert default_budget.max_allowed_leverage == 2

        tight_budget = RiskBudget(
            max_underlying_stop_pct=3.5,
            trailing_stop_pct=2.5,
            max_position_margin_pct=0.05,
            max_allowed_leverage=5,
        )
        assert tight_budget.max_underlying_stop_pct == 3.5
        assert tight_budget.max_allowed_leverage == 5

    def test_ladder_stage_and_deleveraging_rule(self):
        """Verify LadderStage and DeleveragingRule definitions."""
        stage = LadderStage(
            stage_num=1,
            target_cumulative_weight=0.30,
            incremental_weight=0.30,
            recommended_leverage=1,
            stop_loss_pct=10.0,
            is_trailing_stop_loss=False,
            description="Initial spot entry",
        )
        assert stage.stage_num == 1
        assert stage.recommended_leverage == 1
        assert stage.is_trailing_stop_loss is False

        rule = DeleveragingRule(
            trigger_gain_pct=4.0,
            target_leverage=2,
            close_ratio=0.60,
            description="Deleverage from 5x to 2x on +4% gain",
        )
        assert rule.trigger_gain_pct == 4.0
        assert rule.target_leverage == 2
        assert rule.close_ratio == 0.60

    def test_strategy_contract_evaluation(self):
        """Verify StrategyContract entry and exit dispatching."""
        strat = DummyTestStrategyContract()
        assert strat.strategy_id == "dummy_test_strategy"
        assert strat.is_safety_control() is False

        # No trigger
        assert strat.evaluate_entry({}) is None

        # Triggered
        entry_plan = strat.evaluate_entry({"trigger": True})
        assert entry_plan is not None
        assert entry_plan.action == "BUY"
        assert entry_plan.target_leverage == 5
        assert entry_plan.stop_loss_pct == 3.5

        # Exit
        exit_plan = strat.evaluate_exit(None, {"exit": True})
        assert exit_plan is not None
        assert exit_plan.action == "SELL"
        assert exit_plan.target_leverage == 1
