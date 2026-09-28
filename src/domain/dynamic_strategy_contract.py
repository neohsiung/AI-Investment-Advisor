"""
Dynamic Strategy Contract
=========================
將通過 AST 靜態稽核、微沙盒 TDD 驗測與 36 年歷史回測的自主生成因子函式，
動態實例化為標準之 StrategyContract 策略契約。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.domain.strategy_contract import (
    DeleveragingRule,
    LadderStage,
    MarketRegimeType,
    RiskBudget,
    StrategyContract,
    StrategyExecutionPlan,
)
from src.services.code_synthesis.factor_synthesizer import (
    SynthesizedFactorCandidate,
)

logger = logging.getLogger("DynamicStrategyContract")


class DynamicSynthesizedStrategyContract(StrategyContract):
    """
    Standard StrategyContract dynamic wrapper around a verified pure-function factor.
    """

    def __init__(
        self,
        candidate: SynthesizedFactorCandidate,
        factor_callable: Callable[[pd.DataFrame, Optional[dict]], pd.Series],
        backtest_metrics: Dict[str, Any],
        entry_threshold: float = 0.5,
        exit_threshold: float = -0.5,
    ):
        self.candidate = candidate
        self.strategy_id = candidate.factor_name
        self.factor_callable = factor_callable
        self.backtest_metrics = backtest_metrics
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

        # 解析訂閱之體制 (Subscribed Regimes)
        self.subscribed_regimes: List[MarketRegimeType] = []
        for r_name in candidate.target_regimes:
            try:
                self.subscribed_regimes.append(MarketRegimeType(r_name))
            except (ValueError, KeyError):
                self.subscribed_regimes.append(MarketRegimeType.NORMAL)
        if not self.subscribed_regimes:
            self.subscribed_regimes = [MarketRegimeType.NORMAL]

        # 配置剛性風險預算 (Risk Budget)
        self.risk_budget = RiskBudget(
            max_underlying_stop_pct=6.0,
            trailing_stop_pct=5.0,
            max_position_margin_pct=0.10,
            max_holding_days=45,
            max_portfolio_gross_leverage=1.20,
            max_allowed_leverage=1,
        )

        # 降槓桿與保護規則
        self.deleveraging_rules = [
            DeleveragingRule(
                trigger_gain_pct=10.0,
                target_leverage=1,
                close_ratio=0.50,
                description="Take 50% profit at +10% gain",
            )
        ]

    def evaluate_entry(self, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        """
        Evaluate entry signal based on factor calculation over market data history.
        """
        hist_df = market_context.get("history_df")
        if hist_df is None or not isinstance(hist_df, pd.DataFrame) or hist_df.empty:
            return None

        try:
            factor_series = self.factor_callable(hist_df, self.candidate.parameters)
            if factor_series.empty:
                return None
            latest_val = float(factor_series.iloc[-1])

            if latest_val >= self.entry_threshold:
                return StrategyExecutionPlan(
                    action="BUY",
                    stage=1,
                    target_leverage=self.risk_budget.max_allowed_leverage,
                    target_cumulative_weight=1.0,
                    incremental_weight=1.0,
                    stop_loss_pct=self.risk_budget.max_underlying_stop_pct,
                    take_profit_pct=15.0,
                    is_trailing_stop_loss=True,
                    reason=f"Synthesized factor '{self.strategy_id}' triggered: {latest_val:.2f} >= {self.entry_threshold:.2f}",
                )
        except Exception as e:
            logger.warning(
                "Error evaluating entry for synthesized strategy %s: %s",
                self.strategy_id,
                str(e),
            )
            return None

        return None

    def evaluate_exit(self, position: Any, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        """
        Evaluate exit signal based on factor weakness or risk stop.
        """
        hist_df = market_context.get("history_df")
        if hist_df is None or not isinstance(hist_df, pd.DataFrame) or hist_df.empty:
            return None

        try:
            factor_series = self.factor_callable(hist_df, self.candidate.parameters)
            if factor_series.empty:
                return None
            latest_val = float(factor_series.iloc[-1])

            if latest_val <= self.exit_threshold:
                return StrategyExecutionPlan(
                    action="SELL",
                    stage=0,
                    target_leverage=1,
                    target_cumulative_weight=0.0,
                    incremental_weight=0.0,
                    reason=f"Synthesized factor '{self.strategy_id}' exit triggered: {latest_val:.2f} <= {self.exit_threshold:.2f}",
                )
        except Exception as e:
            logger.warning(
                "Error evaluating exit for synthesized strategy %s: %s",
                self.strategy_id,
                str(e),
            )
            return None

        return None
