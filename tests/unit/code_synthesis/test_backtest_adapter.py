"""
Unit Tests for BacktestAdapter and DynamicSynthesizedStrategyContract
=====================================================================
驗測回測轉接器、五大剛性門檻評定以及動態策略契約訊號觸發。
"""
import numpy as np
import pandas as pd
import pytest

from src.domain.dynamic_strategy_contract import (
    DynamicSynthesizedStrategyContract,
)
from src.domain.strategy_contract import MarketRegimeType
from src.services.code_synthesis.backtest_adapter import (
    BacktestAdapter,
    BacktestValidationResult,
)
from src.services.code_synthesis.factor_synthesizer import (
    SynthesizedFactorCandidate,
)


@pytest.fixture
def sample_market_df() -> pd.DataFrame:
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    # Upward trending market with fluctuations
    close = 100.0 + np.cumsum(np.random.normal(0.2, 1.0, n))
    return pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": np.random.randint(1000, 10000, n),
    }, index=dates)


def test_backtest_adapter_evaluates_factor(sample_market_df: pd.DataFrame):
    def factor_func(df: pd.DataFrame, params: dict = None) -> pd.Series:
        return df["Close"].pct_change(5).fillna(0.0)

    candidate = SynthesizedFactorCandidate(
        factor_name="momentum_5d",
        description="5-day momentum",
        source_code="",
        parameters={},
        target_regimes=["NORMAL"],
    )

    adapter = BacktestAdapter(initial_cash=10000.0)
    result = adapter.backtest_factor(candidate, factor_func, sample_market_df)

    assert isinstance(result, BacktestValidationResult)
    assert "sharpe" in result.metrics
    assert "max_drawdown_pct" in result.metrics
    assert "net_return_pct" in result.metrics
    assert "total_trades" in result.metrics
    # Option C: Verify Walk-Forward and Monte Carlo metrics
    assert "wfe" in result.metrics
    assert "oos_sharpe" in result.metrics
    assert "mc_mdd_95" in result.metrics
    assert "mc_profit_prob" in result.metrics


def test_dynamic_synthesized_strategy_contract(sample_market_df: pd.DataFrame):
    def factor_func(df: pd.DataFrame, params: dict = None) -> pd.Series:
        # Generate positive trigger on latest bar
        s = pd.Series(0.0, index=df.index)
        s.iloc[-1] = 1.0
        return s

    candidate = SynthesizedFactorCandidate(
        factor_name="trend_breakout_score",
        description="Trend breakout trigger",
        source_code="",
        parameters={},
        target_regimes=["TREND_ACCELERATION"],
    )

    contract = DynamicSynthesizedStrategyContract(
        candidate=candidate,
        factor_callable=factor_func,
        backtest_metrics={"sharpe": 1.2},
        entry_threshold=0.5,
    )

    assert contract.strategy_id == "trend_breakout_score"
    assert MarketRegimeType.TREND_ACCELERATION in contract.subscribed_regimes
    assert contract.risk_budget.max_underlying_stop_pct == 6.0

    # Evaluate Entry
    context = {"history_df": sample_market_df}
    plan = contract.evaluate_entry(context)
    assert plan is not None
    assert plan.action == "BUY"
    assert plan.target_cumulative_weight == 1.0
    assert plan.stage == 1


def test_dynamic_contract_evaluates_exit(sample_market_df: pd.DataFrame):
    def factor_func(df: pd.DataFrame, params: dict = None) -> pd.Series:
        # Generate negative trigger on latest bar
        s = pd.Series(0.0, index=df.index)
        s.iloc[-1] = -1.0
        return s

    candidate = SynthesizedFactorCandidate(
        factor_name="trend_breakout_score",
        description="Trend breakout trigger",
        source_code="",
        parameters={},
        target_regimes=["TREND_ACCELERATION"],
    )

    contract = DynamicSynthesizedStrategyContract(
        candidate=candidate,
        factor_callable=factor_func,
        backtest_metrics={"sharpe": 1.2},
        exit_threshold=-0.5,
    )

    context = {"history_df": sample_market_df}
    exit_plan = contract.evaluate_exit(position=None, market_context=context)
    assert exit_plan is not None
    assert exit_plan.action == "SELL"
    assert exit_plan.stage == 0
