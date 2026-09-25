"""
Unit Tests for Strategy Registry Service
========================================
驗證策略註冊中心之策略契約註冊、體制路由匹配、認知盲區自我察覺與安全策略識別。
"""
import pytest

from src.domain.strategy_contract import (
    MarketRegimeType,
    RiskBudget,
    StrategyContract,
    StrategyExecutionPlan,
)
from src.services.strategy_registry import StrategyRegistry, SafetyExitContract


class MockCustomRegimeStrategy(StrategyContract):
    def __init__(self, strat_id: str, regime: MarketRegimeType):
        self.strategy_id = strat_id
        self.subscribed_regimes = [regime]
        self.risk_budget = RiskBudget(
            max_underlying_stop_pct=5.0,
            trailing_stop_pct=4.0,
            max_position_margin_pct=0.15,
            max_holding_days=45,
            max_allowed_leverage=2,
        )

    def evaluate_entry(self, market_context):
        return StrategyExecutionPlan(
            action="BUY",
            stage=1,
            target_leverage=2,
            reason="Mock entry triggered",
        )

    def evaluate_exit(self, position, market_context):
        return StrategyExecutionPlan(
            action="SELL",
            stage=0,
            target_leverage=1,
            reason="Mock exit triggered",
        )


class TestStrategyRegistry:
    def test_builtin_strategies_registered(self):
        """Verify built-in safety and alpha strategies are registered upon access."""
        vix_strat = StrategyRegistry.get("vix_panic_rebound")
        assert vix_strat is not None
        assert vix_strat.strategy_id == "vix_panic_rebound"
        assert MarketRegimeType.VOLATILITY_EXTREME in vix_strat.subscribed_regimes

        rebal_strat = StrategyRegistry.get("concentration_rebalance")
        assert rebal_strat is not None
        assert rebal_strat.strategy_id == "concentration_rebalance"

        stop_loss = StrategyRegistry.get("stop_loss")
        assert stop_loss is not None
        assert stop_loss.is_safety_control() is True

    def test_custom_strategy_registration_and_lookup(self):
        """Verify dynamic registration and lookup of custom strategy contracts."""
        strat = MockCustomRegimeStrategy("trend_breakout_v1", MarketRegimeType.TREND_ACCELERATION)
        StrategyRegistry.register(strat)

        retrieved = StrategyRegistry.get("trend_breakout_v1")
        assert retrieved is not None
        assert retrieved.strategy_id == "trend_breakout_v1"
        assert retrieved.subscribed_regimes == [MarketRegimeType.TREND_ACCELERATION]

    def test_regime_matching(self):
        """Verify match_regimes returns all strategies subscribing to active regimes."""
        matched_extreme = StrategyRegistry.match_regimes([MarketRegimeType.VOLATILITY_EXTREME])
        strat_ids = [s.strategy_id for s in matched_extreme]
        assert "vix_panic_rebound" in strat_ids

        strat = MockCustomRegimeStrategy("range_compression_hunter", MarketRegimeType.RANGE_COMPRESSION)
        StrategyRegistry.register(strat)

        matched_range = StrategyRegistry.match_regimes([MarketRegimeType.RANGE_COMPRESSION])
        assert any(s.strategy_id == "range_compression_hunter" for s in matched_range)

    def test_cognitive_blindspot_detection(self):
        """
        Verify check_cognitive_blindspots identifies active regimes that have NO registered strategy.
        測試當出現未覆蓋之極端體制時，系統能自主察覺認知盲區。
        """
        # LIQUIDITY_SHOCK has no registered strategy currently
        uncovered = StrategyRegistry.check_cognitive_blindspots([MarketRegimeType.LIQUIDITY_SHOCK])
        assert MarketRegimeType.LIQUIDITY_SHOCK in uncovered

        # NORMAL regime is filtered out from blindspots
        uncovered_normal = StrategyRegistry.check_cognitive_blindspots([MarketRegimeType.NORMAL])
        assert MarketRegimeType.NORMAL not in uncovered_normal

        # VOLATILITY_EXTREME has vix_panic_rebound registered, so it is NOT uncovered
        uncovered_vix = StrategyRegistry.check_cognitive_blindspots([MarketRegimeType.VOLATILITY_EXTREME])
        assert MarketRegimeType.VOLATILITY_EXTREME not in uncovered_vix

    def test_is_safety_control(self):
        """Verify safety controls are identified correctly vs alpha strategies."""
        assert StrategyRegistry.is_safety_control("stop_loss") is True
        assert StrategyRegistry.is_safety_control("emergency_exit") is True
        assert StrategyRegistry.is_safety_control("take_profit") is True
        assert StrategyRegistry.is_safety_control("vix_panic_rebound") is False
        assert StrategyRegistry.is_safety_control("unknown_alpha_model") is False
