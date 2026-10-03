"""
Unit Tests for Strategy Auto-Evolution & Grid Annealing Service (P4).
測試策略自動演化、模擬退火、WFO 前向走查與推薦卡決策套件。
"""
from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest

from src.services.strategy_auto_evolution_service import (
    CandidateParameterSet,
    EvolutionObjective,
    EvolutionRunReport,
    ParameterRange,
    StrategyAutoEvolutionService,
)


class MockSettingsRepo:
    def __init__(self, data: dict | None = None):
        self.data = data or {}

    def get(self, user_id: str, key: str, default=None):
        return self.data.get(key, default)

    def set(self, user_id: str, key: str, val):
        self.data[key] = val


@pytest.fixture
def synthetic_returns():
    """Generate 252 daily synthetic returns with modest positive drift."""
    rng = random.Random(42)
    # Mean ~0.05% per day, std ~1.0% per day
    return [rng.gauss(0.0005, 0.01) for _ in range(252)]


class TestParameterRange:
    """Test hyperparameter definition, bounded sampling, and mutation logic."""

    def test_float_sampling_and_mutation(self):
        pr = ParameterRange("vol_target", "float", min_val=0.10, max_val=0.20, step=0.01, default_val=0.15)
        rng = random.Random(123)

        # Sampling
        sampled = pr.sample(rng)
        assert 0.10 <= sampled <= 0.20

        # Mutation stays within bounds
        mutated = pr.mutate(0.15, step_scale=1.0, rng=rng)
        assert 0.10 <= mutated <= 0.20

        # Boundary clamping check
        high_mutated = pr.mutate(0.20, step_scale=10.0, rng=random.Random(1))
        assert high_mutated <= 0.20
        low_mutated = pr.mutate(0.10, step_scale=10.0, rng=random.Random(2))
        assert low_mutated >= 0.10

    def test_int_sampling_and_mutation(self):
        pr = ParameterRange("window", "int", min_val=3, max_val=10, step=1, default_val=5)
        rng = random.Random(123)

        sampled = pr.sample(rng)
        assert isinstance(sampled, int)
        assert 3 <= sampled <= 10

        mutated = pr.mutate(5, step_scale=1.0, rng=rng)
        assert isinstance(mutated, int)
        assert 3 <= mutated <= 10

    def test_choice_sampling_and_mutation(self):
        pr = ParameterRange("rebalance_rule", "choice", choices=["daily", "weekly", "monthly"], default_val="weekly")
        rng = random.Random(123)

        sampled = pr.sample(rng)
        assert sampled in ["daily", "weekly", "monthly"]

        mutated = pr.mutate("weekly", step_scale=1.0, rng=rng)
        assert mutated in ["daily", "weekly", "monthly"]

    def test_to_dict_serialization(self):
        pr = ParameterRange("beta", "float", min_val=0.5, max_val=1.5, step=0.1, default_val=1.0)
        d = pr.to_dict()
        assert d["name"] == "beta"
        assert d["param_type"] == "float"
        assert d["min_val"] == 0.5
        assert d["max_val"] == 1.5


class TestFitnessEvaluation:
    """Test multi-objective scoring and penalty constraints."""

    def test_evaluate_fitness_sharpe(self):
        svc = StrategyAutoEvolutionService()
        metrics = {"sharpe": 1.85, "max_drawdown": 0.12, "annualized_return": 0.25}
        score = svc.evaluate_fitness(metrics, EvolutionObjective.SHARPE)
        assert score == 1.85

        # String duck typing
        assert svc.evaluate_fitness(metrics, "sharpe") == 1.85
        assert svc.evaluate_fitness(metrics, "SHARPE") == 1.85

    def test_evaluate_fitness_calmar_and_sortino(self):
        svc = StrategyAutoEvolutionService()
        metrics = {"sharpe": 1.5, "calmar": 2.2, "sortino": 2.5, "annualized_return": 0.22, "max_drawdown": 0.10}
        assert svc.evaluate_fitness(metrics, EvolutionObjective.CALMAR) == 2.2
        assert svc.evaluate_fitness(metrics, "calmar") == 2.2
        assert svc.evaluate_fitness(metrics, EvolutionObjective.SORTINO) == 2.5
        assert svc.evaluate_fitness(metrics, EvolutionObjective.TOTAL_RETURN) == 0.22

    def test_evaluate_composite_fitness_penalizes_drawdown(self):
        svc = StrategyAutoEvolutionService()
        low_dd_metrics = {"sharpe": 1.5, "calmar": 2.0, "annualized_return": 0.20, "max_drawdown": 0.10}
        high_dd_metrics = {"sharpe": 1.5, "calmar": 2.0, "annualized_return": 0.20, "max_drawdown": 0.40}

        score_low = svc.evaluate_fitness(low_dd_metrics, EvolutionObjective.COMPOSITE_FITNESS)
        score_high = svc.evaluate_fitness(high_dd_metrics, EvolutionObjective.COMPOSITE_FITNESS)

        assert score_low > score_high


class TestWalkForwardSplitAndEfficiency:
    """Test temporal data splitting and WFO cross-validation ratio."""

    def test_split_walk_forward(self):
        svc = StrategyAutoEvolutionService()
        is_bounds, oos_bounds = svc.split_walk_forward(100, train_ratio=0.70)
        assert is_bounds == (0, 70)
        assert oos_bounds == (70, 100)

        # Clamping checks
        is_b, oos_b = svc.split_walk_forward(100, train_ratio=0.99)
        assert is_b == (0, 90)  # max 0.90
        assert oos_b == (90, 100)

    def test_calculate_wfo_efficiency(self):
        svc = StrategyAutoEvolutionService()
        # Normal positive case
        assert svc.calculate_wfo_efficiency(is_sharpe=2.0, oos_sharpe=1.5) == 0.75
        # Perfect consistency
        assert svc.calculate_wfo_efficiency(is_sharpe=1.8, oos_sharpe=1.8) == 1.0
        # Negative IS Sharpe fallback
        assert svc.calculate_wfo_efficiency(is_sharpe=-0.5, oos_sharpe=0.5) == 1.0
        assert svc.calculate_wfo_efficiency(is_sharpe=-0.5, oos_sharpe=-0.2) == 0.0


class TestPromotionGateAndRecommendation:
    """Test statistical candidate gating and decision recommendation cards."""

    def test_promotion_gate_passed(self):
        svc = StrategyAutoEvolutionService()
        baseline_metrics = {"sharpe": 1.20, "max_drawdown": 0.15}
        cand = CandidateParameterSet(
            candidate_id="cand-001",
            params={"alloc_target_volatility": 0.16},
            in_sample_metrics={"sharpe": 1.80, "max_drawdown": 0.12},
            out_of_sample_metrics={"sharpe": 1.45, "max_drawdown": 0.14},
            wfo_efficiency=0.80,
            composite_fitness=1.50,
        )

        promoted, reason = svc.evaluate_promotion_gate(cand, baseline_metrics)
        assert promoted is True
        assert "Passed all promotion gates" in reason

    def test_promotion_gate_rejected_for_low_wfo(self):
        svc = StrategyAutoEvolutionService()
        baseline_metrics = {"sharpe": 1.20, "max_drawdown": 0.15}
        cand = CandidateParameterSet(
            candidate_id="cand-overfitted",
            params={"alloc_target_volatility": 0.18},
            in_sample_metrics={"sharpe": 3.00, "max_drawdown": 0.05},
            out_of_sample_metrics={"sharpe": 1.40, "max_drawdown": 0.15},
            wfo_efficiency=0.46,  # < 0.55
            composite_fitness=1.20,
        )

        promoted, reason = svc.evaluate_promotion_gate(cand, baseline_metrics)
        assert promoted is False
        assert "Overfitting risk" in reason

    def test_promotion_gate_rejected_for_insufficient_sharpe_edge(self):
        svc = StrategyAutoEvolutionService()
        baseline_metrics = {"sharpe": 1.50, "max_drawdown": 0.15}
        cand = CandidateParameterSet(
            candidate_id="cand-weak-edge",
            params={"alloc_target_volatility": 0.14},
            in_sample_metrics={"sharpe": 1.60, "max_drawdown": 0.14},
            out_of_sample_metrics={"sharpe": 1.55, "max_drawdown": 0.14},  # +3.3% < 15%
            wfo_efficiency=0.96,
            composite_fitness=1.20,
        )

        promoted, reason = svc.evaluate_promotion_gate(cand, baseline_metrics)
        assert promoted is False
        assert "+15% edge" in reason

    def test_promotion_gate_rejected_for_excessive_mdd(self):
        svc = StrategyAutoEvolutionService()
        baseline_metrics = {"sharpe": 1.20, "max_drawdown": 0.10}
        cand = CandidateParameterSet(
            candidate_id="cand-blowup",
            params={"alloc_target_volatility": 0.20},
            in_sample_metrics={"sharpe": 2.00, "max_drawdown": 0.09},
            out_of_sample_metrics={"sharpe": 1.60, "max_drawdown": 0.20},  # 20% > 10% * 1.15 = 11.5%
            wfo_efficiency=0.80,
            composite_fitness=1.10,
        )

        promoted, reason = svc.evaluate_promotion_gate(cand, baseline_metrics)
        assert promoted is False
        assert "exceeded tolerance ceiling" in reason

    def test_recommendation_card_generation(self):
        svc = StrategyAutoEvolutionService()
        baseline_params = {"alloc_target_volatility": 0.14, "alloc_target_beta": 0.90}
        baseline_metrics = {"sharpe": 1.20, "max_drawdown": 0.15}

        # Case 1: No promotable candidate
        card_none = svc.generate_recommendation_card(None, baseline_params, baseline_metrics)
        assert card_none["decision"] == "MAINTAIN_CURRENT"
        assert card_none["status"] == "NO_PROMOTION"

        # Case 2: Promotable candidate
        cand = CandidateParameterSet(
            candidate_id="cand-star",
            params={"alloc_target_volatility": 0.16, "alloc_target_beta": 0.90},
            in_sample_metrics={"sharpe": 1.80, "max_drawdown": 0.12},
            out_of_sample_metrics={"sharpe": 1.50, "max_drawdown": 0.13},
            wfo_efficiency=0.83,
            composite_fitness=1.45,
            is_promotable=True,
            promotion_reason="Approved",
        )
        card_promo = svc.generate_recommendation_card(cand, baseline_params, baseline_metrics)
        assert card_promo["decision"] == "PRODUCE_UPDATE_RECOMMENDATION"
        assert card_promo["status"] == "READY_FOR_PROMOTION"
        assert "alloc_target_volatility" in card_promo["param_diffs"]
        assert card_promo["param_diffs"]["alloc_target_volatility"] == {"current": 0.14, "evolved": 0.16}


class TestSimulatedAnnealingEngine:
    """Test simulated annealing execution, temperature cooling, and convergence."""

    def test_simulated_annealing_run(self, synthetic_returns):
        svc = StrategyAutoEvolutionService()
        report = svc.run_simulated_annealing(
            historical_returns=synthetic_returns,
            iterations=15,
            initial_temp=50.0,
            cooling_rate=0.80,
            random_seed=42,
        )

        assert isinstance(report, EvolutionRunReport)
        assert report.search_method == "SIMULATED_ANNEALING"
        assert report.total_candidates_evaluated == 15
        assert len(report.annealing_history) == 15

        # Check temperature decay
        first_temp = report.annealing_history[0]["temperature"]
        last_temp = report.annealing_history[-1]["temperature"]
        assert first_temp > last_temp
        assert first_temp == 50.0

        # Check best candidate structure
        assert report.best_candidate is not None
        assert "sharpe" in report.best_candidate.out_of_sample_metrics
        assert report.recommendation_card["decision"] in ["MAINTAIN_CURRENT", "PRODUCE_UPDATE_RECOMMENDATION"]

        # Serialization
        report_dict = report.to_dict()
        assert report_dict["run_id"] == report.run_id
        assert "top_candidates" in report_dict


class TestGridAndRandomSearch:
    """Test deterministic grid exploration and random exploration modes."""

    def test_run_grid_search(self, synthetic_returns):
        svc = StrategyAutoEvolutionService()
        mini_space = [
            ParameterRange("alloc_target_volatility", "float", min_val=0.12, max_val=0.16, step=0.02, default_val=0.14),
            ParameterRange("rebalance_interval_days", "int", min_val=3, max_val=5, step=1, default_val=5),
        ]

        report = svc.run_grid_search(
            historical_returns=synthetic_returns,
            search_space=mini_space,
            max_combinations=10,
        )

        assert report.search_method == "GRID"
        assert report.total_candidates_evaluated > 0
        assert report.total_candidates_evaluated <= 10
        assert report.best_candidate is not None

    def test_run_random_search(self, synthetic_returns):
        svc = StrategyAutoEvolutionService()
        mini_space = [
            ParameterRange("alloc_target_volatility", "float", min_val=0.10, max_val=0.20, step=0.01, default_val=0.14),
        ]

        report = svc.run_random_search(
            historical_returns=synthetic_returns,
            search_space=mini_space,
            iterations=8,
            random_seed=123,
        )

        assert report.search_method == "RANDOM"
        assert report.total_candidates_evaluated == 8
        assert len(report.top_candidates) > 0


class TestSettingsPersistenceAndIntegration:
    """Test dynamic settings schema loading and one-click promotion into repository."""

    def test_apply_candidate_to_settings(self):
        repo = MockSettingsRepo()
        svc = StrategyAutoEvolutionService(user_id="test_trader", settings_repo=repo)

        cand = CandidateParameterSet(
            candidate_id="cand-win",
            params={
                "alloc_target_volatility": 0.17,
                "alloc_target_beta": 0.95,
            },
            in_sample_metrics={},
            out_of_sample_metrics={},
            wfo_efficiency=0.85,
            composite_fitness=1.5,
            is_promotable=True,
        )

        success = svc.apply_candidate_to_settings(cand)
        assert success is True
        assert repo.get("test_trader", "alloc_target_volatility") == 0.17
        assert repo.get("test_trader", "alloc_target_beta") == 0.95

    def test_apply_candidate_with_none_repo(self):
        svc = StrategyAutoEvolutionService(settings_repo=None)
        cand = CandidateParameterSet(
            candidate_id="cand-win",
            params={"test_param": 1},
            in_sample_metrics={},
            out_of_sample_metrics={},
            wfo_efficiency=0.8,
            composite_fitness=1.0,
        )
        assert svc.apply_candidate_to_settings(cand) is False

    def test_apply_candidate_handles_repo_exception(self):
        broken_repo = MagicMock()
        broken_repo.set.side_effect = RuntimeError("Database write lock error")
        svc = StrategyAutoEvolutionService(settings_repo=broken_repo)
        cand = CandidateParameterSet(
            candidate_id="cand-fail",
            params={"alloc_target_volatility": 0.15},
            in_sample_metrics={},
            out_of_sample_metrics={},
            wfo_efficiency=0.8,
            composite_fitness=1.0,
        )
        assert svc.apply_candidate_to_settings(cand) is False

    def test_service_properties_from_settings(self):
        repo = MockSettingsRepo({
            "evolution_annealing_enabled": "false",
            "evolution_wfo_min_efficiency": "0.62",
            "evolution_annealing_initial_temp": "120.0",
            "evolution_annealing_cooling_rate": "0.90",
        })
        svc = StrategyAutoEvolutionService(settings_repo=repo)
        assert svc.is_enabled is False
        assert svc.min_wfo_efficiency == 0.62
        assert svc.initial_temp == 120.0
        assert svc.cooling_rate == 0.90
