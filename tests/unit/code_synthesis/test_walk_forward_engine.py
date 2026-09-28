"""
Unit Tests for WalkForwardEngine and MonteCarloSimulator
========================================================
Verifies:
  1. Walk-Forward rolling temporal window slicing and WFE calculation.
  2. Overfitted factor rejection via WFE < 0.50 or low OOS Sharpe.
  3. Monte Carlo path perturbation bootstrap sampling and MDD 95% evaluation.
  4. Tail risk failure detection under extreme drawdown scenarios.
  5. Short sample graceful handling.
"""
import numpy as np
import pandas as pd
import pytest

from src.services.code_synthesis.walk_forward_engine import (
    MonteCarloSimulator,
    WalkForwardEngine,
)


@pytest.fixture
def upward_trending_market() -> pd.DataFrame:
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    close = 100.0 + np.cumsum(np.random.normal(0.3, 0.8, n))
    return pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": np.random.randint(1000, 10000, n),
    }, index=dates)


def test_walk_forward_engine_robust_factor(upward_trending_market: pd.DataFrame):
    """
    Consistently performing momentum factor across in-sample and out-of-sample slices.
    """
    def robust_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:
        return df["Close"].pct_change(3).fillna(0.0)

    res = WalkForwardEngine.evaluate(
        candidate_params={},
        factor_callable=robust_factor,
        df=upward_trending_market,
        num_windows=3,
        train_ratio=0.60,
    )

    assert res.wfe > 0.0
    assert len(res.windows) > 0
    assert res.avg_oos_return_pct is not None
    assert isinstance(res.failures, list)


def test_walk_forward_engine_overfitted_factor(upward_trending_market: pd.DataFrame):
    """
    A factor that only performs well in the first half of the dataset (in-sample)
    and produces flat/negative signals in forward periods (out-of-sample).
    """
    half_point = len(upward_trending_market) // 2

    def overfitted_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:
        # High signals in first half, negative/zero signals in second half
        s = pd.Series(0.0, index=df.index)
        s.iloc[:half_point] = 10.0
        s.iloc[half_point:] = -10.0
        return s

    res = WalkForwardEngine.evaluate(
        candidate_params={},
        factor_callable=overfitted_factor,
        df=upward_trending_market,
        num_windows=3,
        train_ratio=0.60,
    )

    # In forward OOS slices, factor will underperform, driving WFE down
    assert res.passed is False or len(res.failures) > 0


def test_walk_forward_engine_insufficient_data():
    df_short = pd.DataFrame({"Close": [10.0, 11.0, 12.0]})
    res = WalkForwardEngine.evaluate(
        candidate_params={},
        factor_callable=lambda d, p: d["Close"],
        df=df_short,
    )
    assert res.passed is False
    assert any("too short" in f for f in res.failures)


def test_monte_carlo_simulator_robust_trades():
    """
    Test 20 trades with positive expectancy and modest losses.
    """
    trades = [
        {"pnl_pct": 4.5}, {"pnl_pct": 2.1}, {"pnl_pct": -1.5}, {"pnl_pct": 3.8},
        {"pnl_pct": -2.0}, {"pnl_pct": 5.2}, {"pnl_pct": 1.9}, {"pnl_pct": -1.2},
        {"pnl_pct": 3.0}, {"pnl_pct": 2.5}, {"pnl_pct": -1.8}, {"pnl_pct": 4.0},
        {"pnl_pct": 2.2}, {"pnl_pct": -1.0}, {"pnl_pct": 3.5}, {"pnl_pct": 1.8},
    ]

    res = MonteCarloSimulator.simulate_trade_paths(
        trades=trades,
        initial_cash=10000.0,
        num_simulations=500,
        random_seed=42,
    )

    assert res.passed is True
    assert res.mc_mdd_95 <= 25.0
    assert res.mc_profit_prob >= 0.80
    assert res.median_return_pct > 0.0
    assert len(res.failures) == 0


def test_monte_carlo_simulator_tail_risk_failure():
    """
    Test a strategy with massive loss outliers that breaks 95% max drawdown limit.
    """
    fragile_trades = [
        {"pnl_pct": 2.0}, {"pnl_pct": -28.0}, {"pnl_pct": -22.0},
        {"pnl_pct": 1.5}, {"pnl_pct": -18.0}, {"pnl_pct": 3.0},
    ]

    res = MonteCarloSimulator.simulate_trade_paths(
        trades=fragile_trades,
        initial_cash=10000.0,
        num_simulations=500,
        random_seed=42,
    )

    assert res.passed is False
    assert res.mc_mdd_95 > 25.0
    assert any("exceeds risk threshold" in f for f in res.failures)


def test_monte_carlo_simulator_insufficient_trades():
    few_trades = [{"pnl_pct": 1.0}, {"pnl_pct": -1.0}]
    res = MonteCarloSimulator.simulate_trade_paths(trades=few_trades)
    assert res.passed is False
    assert any("Insufficient trade sample" in f for f in res.failures)
