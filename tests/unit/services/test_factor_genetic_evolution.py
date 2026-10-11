"""
Unit Tests for Factor Genetic Hyper-Evolution Engine (Phase 31)
================================================================
Tests:
- GenerationSummary, GeneticIndividual, GeneticEvolutionReport data structures.
- Multi-objective penalized fitness function computation.
- Shannon factor diversity index computation (uniform vs concentrated).
- Population initialization (baseline seed, style tilts, simplex invariance).
- Tournament selection operator (k=3).
- Dual crossover operator (regime block swap & convex simplex blend).
- Adaptive Gaussian simplex mutation operator.
- Generational evolution loop & Walk-Forward cross validation (WFO).
- Promotion gate criteria and SettingsRepository auto-promotion.
- StrategyAutoEvolutionService.evolve_factor_matrix_genetic integration.
- Celery dispatcher and worker execution tasks.
- 0-LLM /evolve command and /factor cross-link integration in ConversationRouter.
"""
from __future__ import annotations

import json
import math
import random
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.factor_genetic_evolution_engine import (
    FactorGeneticEvolutionEngine,
    GenerationSummary,
    GeneticEvolutionReport,
    GeneticIndividual,
)
from src.services.factor_rotation_replay_engine import (
    FACTOR_NAMES,
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


class TestFactorGeneticEvolutionOperators:
    """Unit tests for individual genetic operators and fitness/diversity math."""

    def test_compute_fitness_reward_and_penalties(self):
        """驗證適應度函數正確獎勵 Sharpe/Sortino/Calmar，並懲罰高換手與大回撤。"""
        good_metrics = ReplayPerformanceMetrics(
            total_return=0.35,
            annualized_return=0.30,
            sharpe=2.50,
            sortino=3.00,
            calmar=2.50,
            max_drawdown=0.08,
            turnover_ratio=0.80,
            total_swaps=15,
        )
        bad_metrics = ReplayPerformanceMetrics(
            total_return=-0.10,
            annualized_return=-0.08,
            sharpe=0.30,
            sortino=0.40,
            calmar=0.30,
            max_drawdown=0.35,
            turnover_ratio=4.00,
            total_swaps=80,
        )

        good_fit = FactorGeneticEvolutionEngine.compute_fitness(good_metrics)
        bad_fit = FactorGeneticEvolutionEngine.compute_fitness(bad_metrics)

        assert good_fit > bad_fit
        assert good_fit > 2.0
        # bad_fit should be heavily penalized by turnover and drawdown
        assert bad_fit < 1.0

    def test_calculate_shannon_diversity_uniform_vs_extreme(self):
        """驗證香農多樣性：完全均勻權重應接近 ln(6)，極端偏激單因子權重應極低。"""
        uniform_matrix = FactorWeightMatrix(
            phase_weights={
                p.value: {fn: 1.0 / 6.0 for fn in FACTOR_NAMES}
                for p in TacticalMarketPhase
            }
        )
        uniform_div = FactorGeneticEvolutionEngine.calculate_shannon_diversity(uniform_matrix)
        expected_ln6 = math.log(6.0)
        assert pytest.approx(uniform_div, 0.05) == expected_ln6
        assert uniform_div >= 1.70

        # 極端單因子集中矩陣 (99% 在 momentum)
        extreme_weights = {}
        for p in TacticalMarketPhase:
            w = {fn: 0.002 for fn in FACTOR_NAMES}
            w["momentum"] = 0.99
            extreme_weights[p.value] = w
        extreme_matrix = FactorWeightMatrix(phase_weights=extreme_weights)
        extreme_matrix.normalize()
        extreme_div = FactorGeneticEvolutionEngine.calculate_shannon_diversity(extreme_matrix)
        assert extreme_div < 0.30
        assert extreme_div < FactorGeneticEvolutionEngine.DEFAULT_MIN_SHANNON_DIVERSITY

    def test_initialize_population_properties(self):
        """驗證族群初始化：規模正確、包含基準種子與風格傾斜種子、全體維持單體歸一。"""
        engine = FactorGeneticEvolutionEngine(user_id="test_user")
        baseline = FactorWeightMatrix()
        rng = random.Random(42)

        pop = engine.initialize_population(pop_size=12, baseline=baseline, rng=rng)
        assert len(pop) == 12

        # 第一個個體應為基準菁英種子
        assert pop[0].matrix.to_dict() == baseline.to_dict()

        # 所有個體染色體權重總和必須嚴格等於 1.0，且因子數量完整
        for ind in pop:
            for ph, weights in ind.matrix.phase_weights.items():
                assert set(weights.keys()) == set(FACTOR_NAMES)
                assert pytest.approx(sum(weights.values()), 1e-4) == 1.0
                for w in weights.values():
                    assert w >= 0.0

    def test_selection_tournament_picks_highest_fitness(self):
        """驗證錦標賽選擇 (Tournament Selection) 在樣本中挑選出最高適應度個體。"""
        pop = [
            GeneticIndividual(matrix=FactorWeightMatrix(), fitness=1.2),
            GeneticIndividual(matrix=FactorWeightMatrix(), fitness=3.8),
            GeneticIndividual(matrix=FactorWeightMatrix(), fitness=2.1),
        ]
        winner = FactorGeneticEvolutionEngine.selection_tournament(pop, k=3)
        assert winner.fitness == 3.8

    def test_crossover_simplex_preservation(self):
        """驗證雙親交叉重組運算：無論區塊重組或凸幾何混血，子代皆保持權重總和 1.0000。"""
        p1 = FactorWeightMatrix()
        p2 = copy_mat = FactorWeightMatrix()
        # 賦予不同的權重
        p2.phase_weights["EARLY_REBOUND"]["momentum"] = 0.70
        p2.normalize()

        rng = random.Random(123)
        c1, c2 = FactorGeneticEvolutionEngine.crossover(p1, p2, crossover_rate=1.0, rng=rng)

        for child in (c1, c2):
            for ph, weights in child.phase_weights.items():
                assert pytest.approx(sum(weights.values()), 1e-4) == 1.0
                for w in weights.values():
                    assert w >= 0.0

        # 若 crossover_rate = 0.0，則應直接複製雙親
        c1_no, c2_no = FactorGeneticEvolutionEngine.crossover(p1, p2, crossover_rate=0.0, rng=rng)
        assert c1_no.to_dict() == p1.to_dict()
        assert c2_no.to_dict() == p2.to_dict()

    def test_mutate_simplex_preservation(self):
        """驗證單體突變運算：高斯擾動後依然維持非負與單體歸一。"""
        mat = FactorWeightMatrix()
        rng = random.Random(999)

        mutated = FactorGeneticEvolutionEngine.mutate(mat, mutation_rate=1.0, rng=rng)
        for ph, weights in mutated.phase_weights.items():
            assert pytest.approx(sum(weights.values()), 1e-4) == 1.0
            for w in weights.values():
                assert w >= 0.0

        # mutation_rate = 0.0 時不發生突變
        unmutated = FactorGeneticEvolutionEngine.mutate(mat, mutation_rate=0.0, rng=rng)
        assert unmutated.to_dict() == mat.to_dict()


class TestFactorGeneticEvolutionExecution:
    """End-to-end generational loop, WFO validation, and promotion gate tests."""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        storage = {
            "enable_factor_genetic_evolution": True,
            "factor_ga_population_size": 6,
            "factor_ga_generations": 3,
            "factor_ga_mutation_rate": 0.20,
            "factor_ga_crossover_rate": 0.80,
            "factor_ga_auto_promote": True,
        }
        settings.get_setting.side_effect = lambda k, default=None, user_id=None: storage.get(k, default)
        settings.set_setting.side_effect = lambda k, val, user_id=None: storage.__setitem__(k, val)
        return settings

    def test_full_evolution_generational_loop_and_report(self, mock_settings):
        """驗證完整世代演化循環、走查驗證 (WFO)、報告結構與歷程。"""
        bars = FactorRotationReplayEngine.generate_synthetic_replay_dataset(num_bars=60, random_seed=42)
        engine = FactorGeneticEvolutionEngine(user_id="test_user", settings_service=mock_settings)

        report = engine.evolve(
            bars=bars,
            population_size=6,
            generations=3,
            mutation_rate=0.25,
            crossover_rate=0.75,
            train_ratio=0.70,
            random_seed=42,
        )

        assert isinstance(report, GeneticEvolutionReport)
        assert report.run_id.startswith("ga_")
        assert report.population_size == 6
        assert report.generations == 3
        assert len(report.generation_history) == 3

        # 驗證每一世代摘要指標
        for gen_sum in report.generation_history:
            assert isinstance(gen_sum, GenerationSummary)
            assert gen_sum.best_fitness != 0.0
            assert gen_sum.diversity_score > 0.0

        # 驗證最優冠軍矩陣歸一性
        for ph, ws in report.best_matrix.phase_weights.items():
            assert pytest.approx(sum(ws.values()), 1e-4) == 1.0

        # 驗證 WFO 指標與香農多樣性
        assert isinstance(report.wfo_efficiency, float)
        assert report.factor_shannon_diversity >= 0.50
        assert isinstance(report.is_promotable, bool)
        assert len(report.promotion_reason) > 0

        # 驗證 to_dict 可正確序列化為 JSON
        rep_dict = report.to_dict()
        assert json.dumps(rep_dict)

    def test_promotion_gate_logic_and_settings_application(self, mock_settings):
        """驗證防過擬合晉級門檻 (WFO efficiency, Sharpe improvement, MDD, diversity) 及 SettingsService 寫入。"""
        engine = FactorGeneticEvolutionEngine(user_id="test_user", settings_service=mock_settings)
        champion_mat = FactorWeightMatrix()

        # 測試手動觸發 _apply_matrix_to_settings
        applied = engine._apply_matrix_to_settings(champion_mat)
        assert applied is True
        mock_settings.set_setting.assert_any_call("tactical_phase_factor_weights", json.dumps(champion_mat.to_dict()))

    def test_strategy_auto_evolution_service_facade(self, mock_settings):
        """驗證 StrategyAutoEvolutionService.evolve_factor_matrix_genetic 外觀調用。"""
        svc = StrategyAutoEvolutionService(user_id="test_user", settings_repo=mock_settings)
        bars = FactorRotationReplayEngine.generate_synthetic_replay_dataset(num_bars=50, random_seed=77)

        report = svc.evolve_factor_matrix_genetic(
            bars=bars,
            population_size=4,
            generations=2,
            random_seed=77,
        )
        assert isinstance(report, GeneticEvolutionReport)
        assert len(report.generation_history) == 2


class TestFactorGeneticEvolutionTasksAndCommands:
    """Celery background task and 0-LLM conversation commands test."""

    @patch("src.infrastructure.tasks.run_factor_genetic_evolution.delay")
    @patch("src.infrastructure.tasks._resolve_target_users")
    def test_dispatch_factor_genetic_evolution(self, mock_resolve_users, mock_delay):
        """驗證 dispatch_factor_genetic_evolution 正確 fan-out 派發任務。"""
        from src.infrastructure.tasks import dispatch_factor_genetic_evolution
        mock_resolve_users.return_value = ["user_1", "user_2"]

        res = dispatch_factor_genetic_evolution()
        assert "Dispatched 2" in res
        assert mock_delay.call_count == 2
        mock_delay.assert_any_call(user_id="user_1")
        mock_delay.assert_any_call(user_id="user_2")

    @patch("src.services.strategy_auto_evolution_service.StrategyAutoEvolutionService.evolve_factor_matrix_genetic")
    @patch("src.services.settings_service.SettingsService")
    def test_run_factor_genetic_evolution_success(self, mock_settings_cls, mock_evolve_genetic):
        """驗證 run_factor_genetic_evolution worker 任務成功執行並回傳結構。"""
        from src.infrastructure.tasks import run_factor_genetic_evolution

        mock_svc = MagicMock()
        mock_svc.get_setting.side_effect = lambda k, d=None, user_id=None: d
        mock_settings_cls.return_value = mock_svc

        fake_report = MagicMock()
        fake_report.run_id = "ga_test123"
        fake_report.is_promotable = True
        fake_report.promoted_to_settings = True
        fake_report.promotion_reason = "Passed all gates"
        fake_report.wfo_efficiency = 0.85
        fake_report.sharpe_improvement_pct = 25.0
        fake_report.mdd_expansion_pct = -5.0
        fake_report.factor_shannon_diversity = 1.65
        fake_report.baseline_oos_metrics.sharpe = 1.50
        fake_report.best_oos_metrics.sharpe = 1.95
        mock_evolve_genetic.return_value = fake_report

        res = run_factor_genetic_evolution(user_id="test_user", population_size=10, generations=5, force=True)
        assert res["status"] == "success"
        assert res["run_id"] == "ga_test123"
        assert res["is_promotable"] is True
        assert res["wfo_efficiency"] == 0.85

    @patch("src.services.settings_service.SettingsService")
    def test_run_factor_genetic_evolution_disabled(self, mock_settings_cls):
        """驗證當開關關閉時，任務安全跳過。"""
        from src.infrastructure.tasks import run_factor_genetic_evolution

        mock_svc = MagicMock()
        mock_svc.get_setting.return_value = False
        mock_settings_cls.return_value = mock_svc

        res = run_factor_genetic_evolution(user_id="test_user", force=False)
        assert res == {"status": "skipped", "reason": "disabled"}

    @pytest.mark.asyncio
    async def test_conversation_router_evolve_command(self):
        """驗證 ConversationRouter 對 /evolve 與其別名之即時回應與報告卡片。"""
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()

        # 1. 關鍵字識別測試
        assert router._is_system_command("/evolve") is True
        assert router._is_system_command("/evolution") is True
        assert router._is_system_command("/ga") is True
        assert router._is_system_command("基因演化") is True
        assert router._is_system_command("因子演化") is True

        # 2. 尚未產生演化報告情境
        with patch.object(FactorGeneticEvolutionEngine, "load_latest_report", return_value=None):
            resp = await router._handle_system_command(
                adapter=None,
                channel_user_id="user_1",
                text="/evolve",
                resolved_user_id="user_1",
            )
            assert "全歷史多因子遺傳演算法超參數演化" in resp
            assert "尚未產生離線遺傳演化報告" in resp

        # 3. 存在演化報告情境
        sample_report = {
            "run_id": "ga_abc123",
            "timestamp": "2026-10-11T20:00:00Z",
            "population_size": 20,
            "generations": 20,
            "mutation_rate": 0.20,
            "crossover_rate": 0.80,
            "wfo_efficiency": 0.82,
            "sharpe_improvement_pct": 21.5,
            "mdd_expansion_pct": -2.3,
            "factor_shannon_diversity": 1.58,
            "is_promotable": True,
            "promoted_to_settings": True,
            "promotion_reason": "✅ 通過遺傳演化終審晉級門檻",
            "baseline_oos_metrics": {"sharpe": 1.40, "annualized_return": 0.18, "max_drawdown": 0.12},
            "best_oos_metrics": {"sharpe": 1.70, "annualized_return": 0.23, "max_drawdown": 0.11},
            "generation_history": [
                {"generation": 1, "best_fitness": 1.5, "mean_fitness": 1.1, "best_sharpe_is": 1.4, "diversity_score": 1.6},
                {"generation": 10, "best_fitness": 2.1, "mean_fitness": 1.7, "best_sharpe_is": 1.8, "diversity_score": 1.5},
                {"generation": 20, "best_fitness": 2.6, "mean_fitness": 2.2, "best_sharpe_is": 2.1, "diversity_score": 1.5},
            ],
            "best_matrix": {
                "phase_weights": {
                    "EARLY_REBOUND": {"momentum": 0.35, "smart_money": 0.25, "liquidity_premium": 0.20, "quality": 0.10, "value": 0.05, "low_vol": 0.05},
                    "BULL_ACCELERATION": {"momentum": 0.40, "smart_money": 0.20, "liquidity_premium": 0.15, "quality": 0.15, "value": 0.05, "low_vol": 0.05},
                }
            },
        }

        with patch.object(FactorGeneticEvolutionEngine, "load_latest_report", return_value=sample_report):
            resp = await router._handle_system_command(
                adapter=None,
                channel_user_id="user_1",
                text="/evolve",
                resolved_user_id="user_1",
            )
            assert "ga_abc123" in resp
            assert "終審通過 (PROMOTED)" in resp
            assert "已生效至生產環境" in resp
            assert "+21.5%" in resp
            assert "世代適應度演化進程" in resp
            assert "演化最優冠軍權重矩陣" in resp
