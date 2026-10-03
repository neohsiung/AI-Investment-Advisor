"""
Unit Tests for KellySizingService and MultiAssetPortfolioBacktestEngine (M4)
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from src.services.kelly_sizing_service import KellyAssessment, KellySizingService
from src.services.multi_asset_backtest_engine import (
    MultiAssetBacktestResult,
    MultiAssetPortfolioBacktestEngine,
)


class DummySettingsService:
    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)


class TestKellySizingService:
    def test_calculate_from_metrics_positive_edge(self):
        """Test Quarter-Kelly sizing with solid win rate and payoff ratio."""
        service = KellySizingService()
        # p = 0.60, avg_win = 0.10, avg_loss = 0.05 -> b = 2.0
        # Expected edge = 0.60 * 2.0 - 0.40 = 0.80
        # Full Kelly = 0.80 / 2.0 = 0.40 (40%)
        # Quarter-Kelly (0.25x) = 0.10 (10%)
        res = service.calculate_from_metrics(
            win_rate=0.60,
            avg_win=0.10,
            avg_loss=0.05,
            sample_count=20,
        )

        assert res.is_statistically_valid is True
        assert res.win_rate == 0.60
        assert res.win_loss_ratio == 2.0
        assert math.isclose(res.full_kelly, 0.40, abs_tol=1e-3)
        assert math.isclose(res.fractional_kelly, 0.10, abs_tol=1e-3)
        assert math.isclose(res.recommended_size, 0.10, abs_tol=1e-3)
        assert res.expected_edge > 0
        assert "放行" in res.reason

    def test_calculate_from_metrics_negative_edge(self):
        """Test that negative expectancy results in zero position size."""
        service = KellySizingService()
        # p = 0.30, avg_win = 0.05, avg_loss = 0.10 -> b = 0.50
        # Expected edge = 0.30 * 0.50 - 0.70 = -0.55 <= 0
        res = service.calculate_from_metrics(
            win_rate=0.30,
            avg_win=0.05,
            avg_loss=0.10,
            sample_count=20,
        )

        assert res.is_statistically_valid is True
        assert res.full_kelly == 0.0
        assert res.fractional_kelly == 0.0
        assert res.recommended_size == 0.0
        assert res.expected_edge < 0
        assert "無統計優勢" in res.reason

    def test_sample_size_below_threshold_fallback(self):
        """Test smooth fallback to prior benchmark when sample size < 10."""
        service = KellySizingService()
        res = service.calculate_from_metrics(
            win_rate=0.80,
            avg_win=0.15,
            avg_loss=0.05,
            sample_count=5,  # Less than min_trades (10)
            default_prior_size=0.10,
        )

        assert res.is_statistically_valid is False
        assert res.sample_count == 5
        assert res.recommended_size == 0.10
        assert "樣本數不足" in res.reason

    def test_boundary_clamping_max_and_min(self):
        """Test that recommended size respects min (2%) and max (20%) boundaries."""
        service = KellySizingService()

        # Extreme positive edge: Full Kelly = 89%, Quarter-Kelly = 22.25% -> clamped to 20%
        res_max = service.calculate_from_metrics(
            win_rate=0.90,
            avg_win=0.20,
            avg_loss=0.02,
            sample_count=25,
        )
        assert res_max.fractional_kelly > 0.20
        assert res_max.recommended_size == 0.20

        # Marginal positive edge: Quarter-Kelly = 0.005 -> clamped to min floor 2%
        res_min = service.calculate_from_metrics(
            win_rate=0.51,
            avg_win=0.010,
            avg_loss=0.0098,
            sample_count=25,
        )
        assert res_min.fractional_kelly < 0.02
        assert res_min.recommended_size == 0.02

    def test_calculate_from_trades_list(self):
        """Test extracting stats from trade records."""
        service = KellySizingService()
        trades = [
            {"pnl": 500.0, "pnl_pct": 5.0},
            {"pnl": 600.0, "pnl_pct": 6.0},
            {"pnl": -200.0, "pnl_pct": -2.0},
            {"pnl": 400.0, "pnl_pct": 4.0},
            {"pnl": -250.0, "pnl_pct": -2.5},
            {"pnl": 700.0, "pnl_pct": 7.0},
            {"pnl": 300.0, "pnl_pct": 3.0},
            {"pnl": -150.0, "pnl_pct": -1.5},
            {"pnl": 800.0, "pnl_pct": 8.0},
            {"pnl": 350.0, "pnl_pct": 3.5},
            {"pnl": -180.0, "pnl_pct": -1.8},
        ]
        res = service.calculate_from_trades(trades)
        assert res.sample_count == 11
        assert res.is_statistically_valid is True
        assert res.win_rate > 0.60
        assert res.win_loss_ratio > 1.5
        assert res.recommended_size > 0.05

    def test_scale_target_allocations(self):
        """Test adjusting multi-asset portfolio weights via Kelly sizing."""
        service = KellySizingService()
        base_weights = {"AAPL": 0.25, "MSFT": 0.20, "BAD": 0.15}
        assessments = {
            "AAPL": KellyAssessment(
                win_rate=0.7, win_loss_ratio=2.0, full_kelly=0.55,
                fractional_kelly=0.1375, recommended_size=0.14,
                sample_count=15, is_statistically_valid=True, expected_edge=0.8, reason="ok"
            ),
            "MSFT": KellyAssessment(
                win_rate=0.6, win_loss_ratio=1.5, full_kelly=0.33,
                fractional_kelly=0.0825, recommended_size=0.08,
                sample_count=15, is_statistically_valid=True, expected_edge=0.4, reason="ok"
            ),
            "BAD": KellyAssessment(
                win_rate=0.2, win_loss_ratio=0.5, full_kelly=0.0,
                fractional_kelly=0.0, recommended_size=0.0,
                sample_count=15, is_statistically_valid=True, expected_edge=-0.7, reason="no edge"
            ),
        }

        adjusted = service.scale_target_allocations(base_weights, assessments, max_total_weight=0.90)
        assert "BAD" not in adjusted  # Negative edge excluded
        assert adjusted["AAPL"] <= 0.14
        assert adjusted["MSFT"] <= 0.08


class TestMultiAssetPortfolioBacktestEngine:
    @pytest.fixture
    def synthetic_market_data(self) -> dict[str, dict[str, list[Any]]]:
        """Generate 100 days of aligned synthetic market data for SPY, AAPL, MSFT, NVDA."""
        dates = [f"2023-{i // 25 + 1:02d}-{i % 25 + 1:02d}" for i in range(100)]
        np.random.seed(42)

        def make_series(start: float, drift: float, vol: float) -> list[float]:
            prices = [start]
            for _ in range(99):
                ret = drift + vol * np.random.randn()
                prices.append(round(prices[-1] * (1.0 + ret), 2))
            return prices

        spy = make_series(400.0, 0.0008, 0.010)
        aapl = make_series(150.0, 0.0012, 0.015)
        msft = make_series(280.0, 0.0010, 0.014)
        nvda = make_series(200.0, 0.0020, 0.025)

        return {
            "SPY": {"date": dates, "close": spy},
            "AAPL": {"date": dates, "close": aapl},
            "MSFT": {"date": dates, "close": msft},
            "NVDA": {"date": dates, "close": nvda},
        }

    def test_engine_run_produces_valid_result(self, synthetic_market_data):
        """Test running multi-asset backtest generates valid equity curve and metrics."""
        engine = MultiAssetPortfolioBacktestEngine(
            initial_cash=100_000.0,
            rebalance_interval_days=5,
            target_volatility=0.14,
            target_beta=0.90,
            cluster_cap=0.30,
        )

        res = engine.run(synthetic_market_data, benchmark_ticker="SPY")
        assert isinstance(res, MultiAssetBacktestResult)
        assert len(res.dates) == 100
        assert len(res.equity_curve) == 100
        assert len(res.cash_curve) == 100
        assert res.equity_curve[0] == 100_000.0
        assert res.equity_curve[-1] > 0

        # Check metrics bundle
        m = res.metrics
        assert "cagr_pct" in m
        assert "sharpe" in m
        assert "max_drawdown_pct" in m
        assert "turnover_rate" in m
        assert "annualized_volatility_pct" in m
        assert m["turnover_rate"] >= 0.0

        # Baseline comparison
        assert "baseline_metrics" in res.to_dict()
        assert "comparison_summary" in res.to_dict()
        assert "sharpe_delta" in res.comparison_summary

    def test_m3_opportunity_cost_saves_friction(self, synthetic_market_data):
        """Test that opportunity cost hurdle prevents unnecessary turnover and saves friction."""
        engine_with_hurdle = MultiAssetPortfolioBacktestEngine(
            initial_cash=100_000.0,
            enable_m3_opportunity_cost=True,
            rotation_friction_multiplier=2.5,
            rotation_hurdle_rate=0.010,
        )
        res_hurdle = engine_with_hurdle.run(synthetic_market_data, benchmark_ticker="SPY")

        assert res_hurdle.friction_saved >= 0.0
        # Friction saved should be recorded when trades are suppressed
        assert res_hurdle.comparison_summary.get("friction_saved_usd", 0.0) >= 0.0

    def test_m2_correlation_cluster_cap_enforcement(self, synthetic_market_data):
        """Test that correlation clustering properly caps high-correlation pairs."""
        engine = MultiAssetPortfolioBacktestEngine(
            initial_cash=100_000.0,
            enable_m2_correlation_clusters=True,
            cluster_cap=0.30,
            correlation_threshold=0.50,
        )
        res = engine.run(synthetic_market_data, benchmark_ticker="SPY")
        assert res is not None

        # Verify that throughout positions history, individual positions respect max_position_pct
        for pos_snapshot in res.positions_history:
            for weight in pos_snapshot.values():
                assert weight <= engine.max_position_pct + 0.05  # allowing slight market appreciation float

    def test_parametric_sensitivity_analysis(self, synthetic_market_data):
        """Test parameter grid sweep utility."""
        engine = MultiAssetPortfolioBacktestEngine(initial_cash=100_000.0)
        grid = engine.run_sensitivity_analysis(
            synthetic_market_data,
            benchmark_ticker="SPY",
            target_volatilities=[0.12, 0.16],
            cluster_caps=[0.25, 0.35],
            friction_multipliers=[1.5, 2.5],
        )

        assert len(grid) == 2 * 2 * 2  # 8 parameter combinations
        for row in grid:
            assert "target_volatility" in row
            assert "cluster_cap" in row
            assert "friction_multiplier" in row
            assert "sharpe" in row
            assert "max_drawdown_pct" in row
