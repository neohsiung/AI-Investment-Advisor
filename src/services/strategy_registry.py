"""
Strategy Registry Service
=========================
策略註冊中心 (Strategy Registry)

集中管理與路由所有受系統承認並具備「實盤資格」的量化策略契約 (Strategy Contract)。
提供體制事件匹配 (Regime Matching)、認知盲區自我察覺 (Cognitive Blindspot Detection)
以及安全策略分類查詢。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from src.domain.strategy_contract import (
    StrategyContract,
    MarketRegimeType,
    MarketRegimeEvent,
    RiskBudget,
    StrategyExecutionPlan,
)

logger = logging.getLogger("StrategyRegistry")


class SafetyExitContract(StrategyContract):
    """Placeholder contract for built-in risk controls that bypass backtest gates."""
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self.subscribed_regimes = []
        self.risk_budget = RiskBudget(
            max_underlying_stop_pct=0.0,
            trailing_stop_pct=0.0,
            max_position_margin_pct=1.0,
            max_holding_days=0,
            max_allowed_leverage=1,
        )

    def evaluate_entry(self, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        return None

    def evaluate_exit(self, position: Any, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        return StrategyExecutionPlan(
            action="SELL",
            stage=0,
            target_leverage=1,
            reason=f"Safety control exit via {self.strategy_id}",
        )

    def is_safety_control(self) -> bool:
        return True


class ConcentrationRebalanceContract(StrategyContract):
    """Contract for portfolio concentration drift rebalancing."""
    def __init__(self):
        self.strategy_id = "concentration_rebalance"
        self.subscribed_regimes = [MarketRegimeType.NORMAL]
        self.risk_budget = RiskBudget(
            max_underlying_stop_pct=8.0,
            trailing_stop_pct=6.0,
            max_position_margin_pct=0.25,
            max_holding_days=90,
            max_allowed_leverage=1,
        )

    def evaluate_entry(self, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        return None

    def evaluate_exit(self, position: Any, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        return None


class StrategyRegistry:
    """
    Central registry for declarative strategy contracts.
    """
    _strategies: Dict[str, StrategyContract] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, strategy: StrategyContract) -> None:
        """Register a strategy contract."""
        cls._ensure_initialized()
        cls._strategies[strategy.strategy_id] = strategy
        logger.info(f"StrategyRegistry: registered strategy '{strategy.strategy_id}'")

    @classmethod
    def get(cls, strategy_id: str) -> Optional[StrategyContract]:
        """Lookup a strategy contract by its id."""
        cls._ensure_initialized()
        return cls._strategies.get(strategy_id)

    @classmethod
    def list_strategies(cls) -> List[StrategyContract]:
        """List all registered strategy contracts."""
        cls._ensure_initialized()
        return list(cls._strategies.values())

    @classmethod
    def match_regimes(cls, active_regimes: List[MarketRegimeType]) -> List[StrategyContract]:
        """
        Find all active strategies that subscribe to any of the current active regimes.
        匹配訂閱當前任何有效市場體制的所有策略契約。
        """
        cls._ensure_initialized()
        regime_set = set(active_regimes)
        matched = []
        for strategy in cls._strategies.values():
            if any(r in regime_set for r in strategy.subscribed_regimes):
                matched.append(strategy)
        return matched

    @classmethod
    def check_cognitive_blindspots(cls, active_regimes: List[MarketRegimeType]) -> List[MarketRegimeType]:
        """
        Identify active market regimes for which NO strategy is currently registered.
        自我察覺認知盲區：找出當前已發生但「系統無任何可用策略對應」之極端體制。
        """
        cls._ensure_initialized()
        covered_regimes: Set[MarketRegimeType] = set()
        for strategy in cls._strategies.values():
            covered_regimes.update(strategy.subscribed_regimes)

        uncovered = [r for r in active_regimes if r not in covered_regimes and r != MarketRegimeType.NORMAL]
        if uncovered:
            uncovered_names = [r.value for r in uncovered]
            logger.warning(
                f"🧠 Cognitive Blindspot Detected: Active regimes {uncovered_names} have NO registered strategy! "
                f"Autonomous research task recommended to discover strategies for these regimes."
            )
        return uncovered

    @classmethod
    def is_safety_control(cls, strategy_id: str) -> bool:
        """Check whether a strategy represents a capital safety control."""
        cls._ensure_initialized()
        contract = cls._strategies.get(strategy_id)
        if contract and contract.is_safety_control():
            return True
        # Standard safety keywords fallback
        return strategy_id in (
            "stop_loss", "emergency_exit", "position_exit", "take_profit",
            "capital_rotation", "rebalance_diversification"
        )

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Initialize built-in strategies once."""
        if cls._initialized:
            return
        cls._initialized = True

        # 1. Register Safety Controls
        for safe_name in ["stop_loss", "emergency_exit", "position_exit", "take_profit", "capital_rotation", "rebalance_diversification"]:
            cls._strategies[safe_name] = SafetyExitContract(safe_name)

        # 2. Register Concentration Rebalance
        cls._strategies["concentration_rebalance"] = ConcentrationRebalanceContract()

        # 3. Register VixPanicReboundStrategyContract
        try:
            from src.services.vix_panic_rebound_strategy import VixPanicReboundStrategyContract
            cls._strategies["vix_panic_rebound"] = VixPanicReboundStrategyContract()
        except Exception as e:
            logger.warning(f"StrategyRegistry: VixPanicReboundStrategyContract load deferred: {e}")
