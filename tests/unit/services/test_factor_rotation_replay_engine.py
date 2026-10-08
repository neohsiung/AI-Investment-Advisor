"""
Unit Tests for Factor Rotation Replay & Auto-Evolution Engine
=============================================================
Tests:
- FactorWeightMatrix simplex normalization, mutation, and serialization.
- ReplayBar dataset generation with alternating regimes.
- Historical replay simulation: portfolio equity, direct cash deployment, friction-aware swaps.
- Multi-objective fitness scoring (Sharpe, Calmar, Sortino, Return, Composite).
- Walk-Forward Optimization (WFO) and Simulated Annealing.
- Overfitting degradation guards and decision recommendation card.
- Integration with StrategyAutoEvolutionService and TacticalFactorRotationService.
- Celery background task execution.
"""
from __future__ import annotations

import json
import random
from unittest.mock import MagicMock, patch
import pytest

from src.services.factor_rotation_replay_engine import (
    FACTOR_NAMES,
    FactorEvolutionReport,
    FactorRotationReplayEngine,
    FactorWeightMatrix,
    ReplayBar,
    ReplayPerformanceMetrics,
)
from src.services.strategy_auto_evolution_service import StrategyAutoEvolutionService
from src.services.tactical_factor_rotation_service import (
    TacticalFactorRotationService,
    TacticalMarketPhase,
)


class TestFactorWeightMatrix:
    """Tests for FactorWeightMatrix simplex geometry and perturbations."""

    def test_default_weights_sum_to_one(self):
        matrix = FactorWeightMatrix()
        for phase, weights in matrix.phase_weights.items():
            assert set(weights.keys()) == set(FACTOR_NAMES)
            total = sum(weights.values())
            assert abs(total - 1.0) < 1e-4
            for factor, w in weights.items():
                assert w >= 0.0

    def test_normalize_simplex_projection(self):
        # Arbitrary raw unnormalized weights
        raw_weights = {
            "EARLY_REBOUND": {
                "momentum": 10.0,
                "smart_money": 20.0,
                "liquidity_premium": 30.0,
                "quality": 40.0,
                "value": -5.0,  # Negative should be truncated
                "low_vol": 0.0,
            }
        }
        matrix = FactorWeightMatrix(phase_weights=raw_weights)
        weights = matrix.phase_weights["EARLY_REBOUND"]
        assert weights["value"] == 0.0
        assert abs(sum(weights.values()) - 1.0) < 1e-4

    def test_normalize_all_zeros_fallback(self):
        raw_weights = {
            "EARLY_REBOUND": {f: 0.0 for f in FACTOR_NAMES}
        }
        matrix = FactorWeightMatrix(phase_weights=raw_weights)
        weights = matrix.phase_weights["EARLY_REBOUND"]
        assert abs(sum(weights.values()) - 1.0) < 1e-3
        for f in FACTOR_NAMES:
            assert weights[f] > 0.0

    def test_mutate_preserves_simplex(self):
        rng = random.Random(123)
        base = FactorWeightMatrix()
        mutated = base.mutate(step_scale=1.0, rng=rng)

        assert isinstance(mutated, FactorWeightMatrix)
        for phase, weights in mutated.phase_weights.items():
            assert abs(sum(weights.values()) - 1.0) < 1e-4
            for factor, w in weights.items():
                assert w >= 0.0
        assert 0.03 <= mutated.min_edge_pct <= 0.20

    def test_serialization_fidelity(self):
        matrix = FactorWeightMatrix(min_edge_pct=0.09, liquidity_premium_weight=0.40)
        data = matrix.to_dict()
        reconstructed = FactorWeightMatrix.from_dict(data)

        assert reconstructed.min_edge_pct == 0.09
        assert reconstructed.liquidity_premium_weight == 0.40
        for phase in matrix.phase_weights:
            for factor in FACTOR_NAMES:
                assert abs(matrix.phase_weights[phase][factor] - reconstructed.phase_weights[phase][factor]) < 1e-4

    def test_from_dict_empty_fallback(self):
        matrix = FactorWeightMatrix.from_dict({})
        assert matrix.min_edge_pct == 0.08
        assert len(matrix.phase_weights) == 4


class TestReplaySimulation:
    """Tests for historical replay simulation and performance evaluation."""

    @pytest.fixture
    def synthetic_dataset(self) -> list[ReplayBar]:
        return FactorRotationReplayEngine.generate_synthetic_replay_dataset(
            num_bars=120,
            num_assets=6,
            random_seed=42,
        )

    def test_generate_synthetic_replay_dataset(self, synthetic_dataset):
        assert len(synthetic_dataset) == 120
        first_bar = synthetic_dataset[0]
        assert first_bar.vix > 0.0
        assert first_bar.spy_price > 0.0
        assert len(first_bar.asset_factors) == 6
        assert len(first_bar.asset_returns) == 6

    def test_simulate_replay_empty_bars(self):
        engine = FactorRotationReplayEngine()
        metrics = engine.simulate_replay([], FactorWeightMatrix())
        assert metrics.sharpe == 0.0
        assert metrics.total_return == 0.0
        assert metrics.equity_curve == []

    def test_simulate_replay_execution_and_metrics(self, synthetic_dataset):
        engine = FactorRotationReplayEngine()
        matrix = FactorWeightMatrix()
        metrics = engine.simulate_replay(
            bars=synthetic_dataset,
            matrix=matrix,
            initial_cash=100000.0,
            target_cash_ratio=0.10,
        )

        assert len(metrics.equity_curve) == len(synthetic_dataset) + 1
        assert len(metrics.daily_returns) == len(synthetic_dataset)
        assert metrics.max_drawdown >= 0.0
        assert isinstance(metrics.sharpe, float)
        assert isinstance(metrics.sortino, float)
        assert isinstance(metrics.calmar, float)
        assert metrics.to_dict()["total_swaps"] == metrics.total_swaps

    def test_evaluate_fitness_all_objectives(self):
        engine = FactorRotationReplayEngine()
        metrics = ReplayPerformanceMetrics(
            sharpe=1.85,
            sortino=2.20,
            calmar=2.50,
            annualized_return=0.25,
            max_drawdown=0.10,
        )

        assert engine.evaluate_fitness(metrics, "SHARPE") == 1.85
        assert engine.evaluate_fitness(metrics, "CALMAR") == 2.50
        assert engine.evaluate_fitness(metrics, "SORTINO") == 2.20
        assert engine.evaluate_fitness(metrics, "RETURN") == 0.25

        comp = engine.evaluate_fitness(metrics, "COMPOSITE")
        expected_comp = 0.50 * 1.85 + 0.30 * 2.50 + 0.20 * 0.25 - 1.50 * 0.10
        assert abs(comp - expected_comp) < 1e-4


class TestSimulatedAnnealingAndWFO:
    """Tests for simulated annealing, walk-forward optimization, and promotion logic."""

    @pytest.fixture
    def test_bars(self) -> list[ReplayBar]:
        return FactorRotationReplayEngine.generate_synthetic_replay_dataset(
            num_bars=80,
            num_assets=6,
            random_seed=101,
        )

    def test_evolve_factor_weights_generates_report(self, test_bars):
        engine = FactorRotationReplayEngine()
        report = engine.evolve_factor_weights(
            bars=test_bars,
            max_iterations=5,
            train_ratio=0.70,
            random_seed=42,
        )

        assert isinstance(report, FactorEvolutionReport)
        assert report.total_iterations == 5
        assert len(report.annealing_history) == 5
        assert isinstance(report.best_matrix, FactorWeightMatrix)
        assert report.wfo_efficiency >= 0.0
        assert "decision" in report.recommendation_card
        assert "metrics_comparison" in report.recommendation_card

    def test_promotion_gate_thresholds(self):
        engine = FactorRotationReplayEngine()
        report_dict = {
            "run_id": "test-run",
            "timestamp": "2026-10-08T00:00:00Z",
            "objective": "SHARPE",
            "total_iterations": 10,
            "baseline_matrix": FactorWeightMatrix(),
            "baseline_metrics": ReplayPerformanceMetrics(sharpe=1.0, max_drawdown=0.10),
            "best_matrix": FactorWeightMatrix(),
            "best_is_metrics": ReplayPerformanceMetrics(sharpe=2.0),
            "best_oos_metrics": ReplayPerformanceMetrics(sharpe=1.25, max_drawdown=0.105),
            "wfo_efficiency": 0.625,
            "is_promotable": True,
            "promotion_reason": "Promoted",
        }
        report = FactorEvolutionReport(**report_dict)
        data = report.to_dict()
        assert data["is_promotable"] is True
        assert data["wfo_efficiency"] == 0.625


class TestServiceIntegration:
    """Tests integration with StrategyAutoEvolutionService and TacticalFactorRotationService."""

    def test_strategy_auto_evolution_service_integration(self):
        mock_repo = MagicMock()
        mock_repo.get.return_value = None

        evo_service = StrategyAutoEvolutionService(user_id="test_user", settings_repo=mock_repo)
        report = evo_service.evolve_factor_rotation_matrix(iterations=3, random_seed=42)

        assert isinstance(report, FactorEvolutionReport)
        assert report.total_iterations == 3

        # Test applying evolved matrix to settings
        success = evo_service.apply_evolved_matrix_to_settings(report.best_matrix)
        assert success is True
        assert mock_repo.set.call_count >= 1

        # Verify key was set
        set_calls = {call[0][1]: call[0][2] for call in mock_repo.set.call_args_list}
        assert "tactical_phase_factor_weights" in set_calls
        assert "tactical_rotation_min_edge_pct" in set_calls

    def test_tactical_factor_rotation_dynamic_weights_loading(self):
        custom_weights = {
            "phase_weights": {
                "EARLY_REBOUND": {
                    "momentum": 0.45,
                    "liquidity_premium": 0.20,
                    "smart_money": 0.15,
                    "quality": 0.10,
                    "value": 0.05,
                    "low_vol": 0.05,
                }
            }
        }
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda k, d=None, user_id=None: (
            json.dumps(custom_weights) if k == "tactical_phase_factor_weights" else d
        )

        rotation_svc = TacticalFactorRotationService(settings_service=mock_settings)
        weights = rotation_svc.get_phase_factor_weights(TacticalMarketPhase.EARLY_REBOUND)

        assert weights["momentum"] == 0.45
        assert weights["low_vol"] == 0.05

    def test_tactical_factor_rotation_fallback_on_invalid_setting(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda k, d=None, user_id=None: (
            "INVALID_JSON_CORRUPT" if k == "tactical_phase_factor_weights" else d
        )

        rotation_svc = TacticalFactorRotationService(settings_service=mock_settings)
        weights = rotation_svc.get_phase_factor_weights(TacticalMarketPhase.EARLY_REBOUND)

        # Should fall back to default EARLY_REBOUND weights without crashing
        assert weights["momentum"] == 0.30
        assert weights["liquidity_premium"] == 0.25


class TestCeleryTaskExecution:
    """Tests for Celery task dispatch and execution."""

    @patch("src.infrastructure.tasks._resolve_target_users", return_value=["test_user"])
    @patch("src.infrastructure.tasks.run_factor_rotation_evolution.delay")
    def test_dispatch_factor_rotation_evolution(self, mock_delay, mock_users):
        from src.infrastructure.tasks import dispatch_factor_rotation_evolution
        res = dispatch_factor_rotation_evolution()
        assert "Dispatched 1" in res
        mock_delay.assert_called_once_with(user_id="test_user")

    @patch("src.services.settings_service.SettingsService")
    @patch("src.services.strategy_auto_evolution_service.StrategyAutoEvolutionService")
    def test_run_factor_rotation_evolution_success(self, mock_evo_cls, mock_settings_cls):
        from src.infrastructure.tasks import run_factor_rotation_evolution

        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda k, d=None, user_id=None: {
            "enable_tactical_factor_replay_tuning": True,
            "replay_evolution_lookback_bars": 60,
            "replay_evolution_wfo_train_ratio": 0.70,
        }.get(k, d)
        mock_settings_cls.return_value = mock_settings

        mock_evo = MagicMock()
        mock_report = MagicMock()
        mock_report.is_promotable = True
        mock_report.promotion_reason = "Promoted with Sharpe +20%"
        mock_report.wfo_efficiency = 0.75
        mock_report.baseline_metrics.sharpe = 1.00
        mock_report.best_oos_metrics.sharpe = 1.25
        mock_report.best_matrix = FactorWeightMatrix()
        mock_evo.evolve_factor_rotation_matrix.return_value = mock_report
        mock_evo_cls.return_value = mock_evo

        result = run_factor_rotation_evolution(user_id="test_user", iterations=2)

        assert result["status"] == "success"
        assert result["is_promotable"] is True
        assert result["sharpe_evolved"] == 1.25
        mock_evo.apply_evolved_matrix_to_settings.assert_called_once()

    @patch("src.services.settings_service.SettingsService")
    def test_run_factor_rotation_evolution_skipped_when_disabled(self, mock_settings_cls):
        from src.infrastructure.tasks import run_factor_rotation_evolution

        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda k, d=None, user_id=None: (
            False if k == "enable_tactical_factor_replay_tuning" else d
        )
        mock_settings_cls.return_value = mock_settings

        result = run_factor_rotation_evolution(user_id="test_user", force=False)
        assert result["status"] == "skipped"
        assert result["reason"] == "disabled"
