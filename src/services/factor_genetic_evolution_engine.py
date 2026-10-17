"""
Factor Genetic Hyper-Evolution Engine (Phase 31)
================================================
全歷史動態多因子權重遺傳演算法離線自主演化排程引擎

核心架構：
1. 染色體表示與族群初始化 (Chromosome & Population Initialization)：
   - 基因型：4 大市場週期 (EARLY_REBOUND, BULL_ACCELERATION, LATE_CYCLE_VALUE, DEFENSIVE_CONSOLIDATION)
     各 6 大因子權重向量 (Momentum, Smart Money, Liquidity, Quality, Value, Low Vol) 及
     換倉超參數 (min_edge_pct, liquidity_premium_weight)。
   - 族群注入：基準菁英染色體 (Baseline Seed) + 風格偏向突變種 (Momentum/Quality/Defensive) + 隨機單體個體。
2. 遺傳算子 (Genetic Operators)：
   - 適應度函數 (Fitness)：多目標非線性綜合適應度 (Sharpe + 0.35 Calmar + 0.15 AnnReturn - 0.10 Turnover - 1.5 MDD)。
   - 錦標賽選擇 (Tournament Selection, k=3) 與菁英保留 (Elitism, K=2)。
   - 雙重交叉算子 (Crossover)：體制級區塊重組 (Regime Block Swap) 與凸幾何單體混血 (Convex Simplex Blend)。
   - 自適應高斯單體突變 (Simplex Mutation)：動態階躍擾動並透過 Simplex Normalization 確保權重嚴格非負且總和 1.0000。
3. 嚴格走查驗證與防過擬合閘門 (Walk-Forward Validation Gate)：
   - In-Sample (IS, 70%) 訓練演化 vs Out-of-Sample (OOS, 30%) 盲測走查。
   - WFO Efficiency >= 0.55 (OOS Sharpe / IS Sharpe)。
   - OOS Sharpe 相對提升 >= 15%。
   - OOS 最大回撤 (MDD) 擴張 <= 10%。
   - 香農多因子多樣性指數 (Shannon Diversity Index) >= 0.80，杜絕退化為單因子極端集中。
4. 離線非同步排程與自動晉級 (Autonomous Promotion & Redis Persistence)：
   - 支援自動將通過驗證之基因矩陣晉級至 SettingsRepository (tactical_phase_factor_weights)。
   - 跨程序 Redis 快取持久化 (factor_evolution:genetic_latest:{user_id}) 與 0-LLM 指令 /evolve。
"""

from __future__ import annotations

import copy
import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.config.owner import resolve_user_id
from src.services.factor_rotation_replay_engine import (
    FACTOR_NAMES,
    FactorRotationReplayEngine,
    FactorWeightMatrix,
    ReplayBar,
    ReplayPerformanceMetrics,
)
from src.services.tactical_factor_rotation_service import (
    TacticalMarketPhase,
)

logger = logging.getLogger("FactorGeneticEvolutionEngine")


@dataclass
class GenerationSummary:
    """單一世代之統計指標與多樣性摘要"""
    generation: int
    best_fitness: float
    mean_fitness: float
    fitness_std: float
    best_sharpe_is: float
    best_ann_return_is: float
    best_max_dd_is: float
    diversity_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation": self.generation,
            "best_fitness": round(self.best_fitness, 4),
            "mean_fitness": round(self.mean_fitness, 4),
            "fitness_std": round(self.fitness_std, 4),
            "best_sharpe_is": round(self.best_sharpe_is, 4),
            "best_ann_return_is": round(self.best_ann_return_is, 4),
            "best_max_dd_is": round(self.best_max_dd_is, 4),
            "diversity_score": round(self.diversity_score, 4),
        }


@dataclass
class GeneticIndividual:
    """遺傳演算法染色體個體"""
    matrix: FactorWeightMatrix
    fitness: float = 0.0
    is_metrics: Optional[ReplayPerformanceMetrics] = None
    oos_metrics: Optional[ReplayPerformanceMetrics] = None
    generation_born: int = 0


@dataclass
class GeneticEvolutionReport:
    """全歷史多因子遺傳演化終審診斷報告"""
    run_id: str
    timestamp: str
    population_size: int
    generations: int
    mutation_rate: float
    crossover_rate: float
    baseline_matrix: FactorWeightMatrix
    baseline_is_metrics: ReplayPerformanceMetrics
    baseline_oos_metrics: ReplayPerformanceMetrics
    best_matrix: FactorWeightMatrix
    best_is_metrics: ReplayPerformanceMetrics
    best_oos_metrics: ReplayPerformanceMetrics
    wfo_efficiency: float
    sharpe_improvement_pct: float
    mdd_expansion_pct: float
    factor_shannon_diversity: float
    is_promotable: bool
    promotion_reason: str
    generation_history: List[GenerationSummary] = field(default_factory=list)
    promoted_to_settings: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "population_size": self.population_size,
            "generations": self.generations,
            "mutation_rate": round(self.mutation_rate, 3),
            "crossover_rate": round(self.crossover_rate, 3),
            "baseline_matrix": self.baseline_matrix.to_dict(),
            "baseline_is_metrics": self.baseline_is_metrics.to_dict(),
            "baseline_oos_metrics": self.baseline_oos_metrics.to_dict(),
            "best_matrix": self.best_matrix.to_dict(),
            "best_is_metrics": self.best_is_metrics.to_dict(),
            "best_oos_metrics": self.best_oos_metrics.to_dict(),
            "wfo_efficiency": round(self.wfo_efficiency, 4),
            "sharpe_improvement_pct": round(self.sharpe_improvement_pct, 2),
            "mdd_expansion_pct": round(self.mdd_expansion_pct, 2),
            "factor_shannon_diversity": round(self.factor_shannon_diversity, 4),
            "is_promotable": self.is_promotable,
            "promotion_reason": self.promotion_reason,
            "generation_history": [g.to_dict() for g in self.generation_history],
            "promoted_to_settings": self.promoted_to_settings,
        }


class FactorGeneticEvolutionEngine:
    """
    全歷史多因子遺傳演算法超參數離線演化引擎
    """

    _REDIS_LATEST_KEY_PREFIX = "factor_evolution:genetic_latest"
    _REDIS_HISTORY_KEY_PREFIX = "factor_evolution:genetic_history"
    _MEMORY_LATEST_REPORT: Dict[str, Dict[str, Any]] = {}

    DEFAULT_WFO_MIN_EFFICIENCY = 0.55
    DEFAULT_MIN_SHARPE_EDGE = 0.15          # 要求 OOS Sharpe 至少提升 15%
    DEFAULT_MAX_MDD_EXPANSION = 0.10        # 容許 OOS MDD 擴張至多 10%
    DEFAULT_MIN_SHANNON_DIVERSITY = 0.80    # 避免因子單一崩縮

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        replay_engine: Optional[FactorRotationReplayEngine] = None,
    ):
        try:
            self.user_id = resolve_user_id(user_id) if user_id else "default"
        except Exception:
            self.user_id = user_id or "default"
        self.settings_service = settings_service
        self.replay_engine = replay_engine or FactorRotationReplayEngine()

    def _get_setting_bool(self, key: str, default: bool = True) -> bool:
        if not self.settings_service:
            return default
        try:
            if hasattr(self.settings_service, "get_setting"):
                val = self.settings_service.get_setting(key, default)
            elif hasattr(self.settings_service, "get"):
                val = self.settings_service.get(self.user_id, key, default)
            else:
                val = default
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes")
        except Exception:
            return default

    def _get_setting_float(self, key: str, default: float) -> float:
        if not self.settings_service:
            return default
        try:
            if hasattr(self.settings_service, "get_setting"):
                val = self.settings_service.get_setting(key, default)
            elif hasattr(self.settings_service, "get"):
                val = self.settings_service.get(self.user_id, key, default)
            else:
                val = default
            return float(val) if val is not None else default
        except Exception:
            return default

    def _get_setting_int(self, key: str, default: int) -> int:
        return int(self._get_setting_float(key, float(default)))

    @property
    def is_enabled(self) -> bool:
        return self._get_setting_bool("enable_factor_genetic_evolution", False)

    @property
    def default_population_size(self) -> int:
        return self._get_setting_int("factor_ga_population_size", 20)

    @property
    def default_generations(self) -> int:
        return self._get_setting_int("factor_ga_generations", 20)

    @property
    def default_mutation_rate(self) -> float:
        return self._get_setting_float("factor_ga_mutation_rate", 0.20)

    @property
    def default_crossover_rate(self) -> float:
        return self._get_setting_float("factor_ga_crossover_rate", 0.80)

    @property
    def auto_promote(self) -> bool:
        return self._get_setting_bool("factor_ga_auto_promote", True)

    @staticmethod
    def compute_fitness(metrics: ReplayPerformanceMetrics) -> float:
        """
        多目標懲罰適應度函數：
        綜合年化夏普 (Sharpe)、索提諾 (Sortino)、卡瑪比率 (Calmar)、
        年化回報並對回撤與頻繁無效換倉施加剛性懲罰。
        """
        sharpe = float(metrics.sharpe)
        sortino = float(metrics.sortino)
        calmar = float(metrics.calmar)
        ann_return = float(metrics.annualized_return)
        max_dd = float(metrics.max_drawdown)
        turnover = float(metrics.turnover_ratio)

        # 懲罰項：避免換手率過高導致券商手續費與滑點摩擦腐蝕本金
        turnover_penalty = 0.10 * min(5.0, max(0.0, turnover - 1.0))
        # 懲罰項：對超過 15% 的最大回撤施加二次方加速抑制
        dd_penalty = 1.50 * min(0.60, max_dd)

        fitness = (
            sharpe * 0.60
            + min(3.0, sortino) * 0.25
            + min(3.0, calmar) * 0.20
            + min(1.0, ann_return) * 0.15
            - turnover_penalty
            - dd_penalty
        )
        return float(round(fitness, 4))

    @staticmethod
    def calculate_shannon_diversity(matrix: FactorWeightMatrix) -> float:
        r"""
        計算 4 大市場體制因子權重之平均香農熵 (Shannon Entropy)：
        H = - \sum p_i \ln(p_i)
        滿分度量 (6 因子等權): ln(6) = 1.7918。
        若香農熵過低 (< 0.80)，表示模型退化為單一因子極度偏激集中，有嚴重的過擬合風險。
        """
        entropies = []
        for phase, weights in matrix.phase_weights.items():
            h_p = 0.0
            for w in weights.values():
                val = max(1e-9, float(w))
                h_p -= val * math.log(val)
            entropies.append(h_p)
        return float(np.mean(entropies)) if entropies else 0.0

    def initialize_population(
        self,
        pop_size: int,
        baseline: FactorWeightMatrix,
        rng: random.Random,
    ) -> List[GeneticIndividual]:
        """
        種群初始化：以基準個體為錨點，結合風格傾向個體與單體隨機均勻採樣個體。
        """
        pop: List[GeneticIndividual] = []

        # 1. 菁英種子 (Baseline Seed)
        pop.append(GeneticIndividual(matrix=copy.deepcopy(baseline), generation_born=0))

        # 2. 風格偏好種子 (Momentum-Heavy, Quality-Heavy, Defensive-Heavy, Value-Heavy)
        style_tilts = [
            ("momentum", 0.45),
            ("quality", 0.40),
            ("low_vol", 0.40),
            ("value", 0.35),
            ("liquidity_premium", 0.35),
        ]
        for tilt_factor, tilt_weight in style_tilts:
            if len(pop) >= pop_size:
                break
            tilted_mat = copy.deepcopy(baseline)
            for phase_name in tilted_mat.phase_weights:
                curr_w = tilted_mat.phase_weights[phase_name]
                if tilt_factor in curr_w:
                    curr_w[tilt_factor] = tilt_weight
            tilted_mat.normalize()
            pop.append(GeneticIndividual(matrix=tilted_mat, generation_born=0))

        # 3. 隨機微擾與均勻單體個體填充
        while len(pop) < pop_size:
            mut_scale = rng.uniform(0.15, 0.45)
            cand_mat = baseline.mutate(step_scale=mut_scale, rng=rng)
            cand_mat.min_edge_pct = round(rng.uniform(0.04, 0.12), 4)
            cand_mat.liquidity_premium_weight = round(rng.uniform(0.15, 0.40), 4)
            pop.append(GeneticIndividual(matrix=cand_mat, generation_born=0))

        return pop

    @staticmethod
    def selection_tournament(
        population: List[GeneticIndividual],
        k: int = 3,
        rng: Optional[random.Random] = None,
    ) -> GeneticIndividual:
        """
        錦標賽選擇算子 (Tournament Selection, k=3)
        """
        r = rng or random
        k_val = min(k, len(population))
        contestants = r.sample(population, k_val)
        return max(contestants, key=lambda ind: ind.fitness)

    @classmethod
    def crossover(
        cls,
        parent1: FactorWeightMatrix,
        parent2: FactorWeightMatrix,
        crossover_rate: float,
        rng: random.Random,
    ) -> Tuple[FactorWeightMatrix, FactorWeightMatrix]:
        """
        雙親重組交叉算子：
        以 crossover_rate 觸發：
        50% 機率採用體制級區塊基因重組 (Regime Block Swap)；
        50% 機率採用凸幾何單體混血 (Convex Simplex Blend)。
        """
        if rng.random() > crossover_rate:
            return copy.deepcopy(parent1), copy.deepcopy(parent2)

        c1 = copy.deepcopy(parent1)
        c2 = copy.deepcopy(parent2)

        # 選擇交叉模式
        mode_swap = rng.random() < 0.50

        all_phases = [p.value for p in TacticalMarketPhase]

        if mode_swap:
            # 體制區塊交換
            swap_phases = rng.sample(all_phases, k=rng.randint(1, 3))
            for sp in swap_phases:
                c1.phase_weights[sp] = copy.deepcopy(parent2.phase_weights.get(sp, {}))
                c2.phase_weights[sp] = copy.deepcopy(parent1.phase_weights.get(sp, {}))
        else:
            # 凸幾何加權混血 (Convex Blend)
            alpha = rng.uniform(0.25, 0.75)
            for sp in all_phases:
                w1 = parent1.phase_weights.get(sp, {})
                w2 = parent2.phase_weights.get(sp, {})
                blended1 = {fn: alpha * w1.get(fn, 0.16) + (1.0 - alpha) * w2.get(fn, 0.16) for fn in FACTOR_NAMES}
                blended2 = {fn: (1.0 - alpha) * w1.get(fn, 0.16) + alpha * w2.get(fn, 0.16) for fn in FACTOR_NAMES}
                c1.phase_weights[sp] = blended1
                c2.phase_weights[sp] = blended2

        # 換倉超參數交叉
        blend_param = rng.uniform(0.3, 0.7)
        c1.min_edge_pct = round(blend_param * parent1.min_edge_pct + (1.0 - blend_param) * parent2.min_edge_pct, 4)
        c2.min_edge_pct = round((1.0 - blend_param) * parent1.min_edge_pct + blend_param * parent2.min_edge_pct, 4)

        c1.liquidity_premium_weight = round(blend_param * parent1.liquidity_premium_weight + (1.0 - blend_param) * parent2.liquidity_premium_weight, 4)
        c2.liquidity_premium_weight = round((1.0 - blend_param) * parent1.liquidity_premium_weight + blend_param * parent2.liquidity_premium_weight, 4)

        c1.normalize()
        c2.normalize()
        return c1, c2

    @classmethod
    def mutate(
        cls,
        matrix: FactorWeightMatrix,
        mutation_rate: float,
        rng: random.Random,
    ) -> FactorWeightMatrix:
        """
        高斯微擾單體突變算子
        """
        if rng.random() > mutation_rate:
            return matrix

        mut_scale = rng.uniform(0.15, 0.35)
        mutated = matrix.mutate(step_scale=mut_scale, rng=rng)

        # 20% 機率微調超參數
        if rng.random() < 0.20:
            mutated.min_edge_pct = round(max(0.04, min(0.12, mutated.min_edge_pct + rng.gauss(0, 0.015))), 4)
        if rng.random() < 0.20:
            mutated.liquidity_premium_weight = round(max(0.15, min(0.40, mutated.liquidity_premium_weight + rng.gauss(0, 0.025))), 4)

        mutated.normalize()
        return mutated

    def evolve(
        self,
        bars: List[ReplayBar],
        baseline_matrix: Optional[FactorWeightMatrix] = None,
        population_size: Optional[int] = None,
        generations: Optional[int] = None,
        mutation_rate: Optional[float] = None,
        crossover_rate: Optional[float] = None,
        elitism_count: int = 2,
        train_ratio: float = 0.70,
        random_seed: Optional[int] = None,
    ) -> GeneticEvolutionReport:
        """
        執行全歷史遺傳演算法超參數優化與前向走查交叉驗證 (WFO)。
        """
        run_id = f"ga_{uuid.uuid4().hex[:8]}"
        now_ts = datetime.now(timezone.utc).isoformat()
        rng = random.Random(random_seed) if random_seed is not None else random.Random()

        pop_size = population_size or self.default_population_size
        num_gens = generations or self.default_generations
        mut_rate = mutation_rate if mutation_rate is not None else self.default_mutation_rate
        cross_rate = crossover_rate if crossover_rate is not None else self.default_crossover_rate

        base_mat = baseline_matrix or FactorWeightMatrix()

        # 1. 劃分 Walk-Forward In-Sample 訓練集與 Out-of-Sample 盲測集
        n_bars = len(bars)
        split_idx = max(20, int(n_bars * max(0.50, min(0.90, train_ratio))))
        is_bars = bars[:split_idx]
        oos_bars = bars[split_idx:]

        # 2. 評定基準矩陣表現 (Baseline Benchmark)
        base_is_metrics = self.replay_engine.simulate_replay(is_bars, base_mat)
        base_oos_metrics = self.replay_engine.simulate_replay(oos_bars, base_mat)
        base_is_fitness = self.compute_fitness(base_is_metrics)

        logger.info(
            f"[{run_id}] Starting Genetic Evolution: Pop={pop_size}, Gens={num_gens}, "
            f"IS_Bars={len(is_bars)}, OOS_Bars={len(oos_bars)}, Base_IS_Sharpe={base_is_metrics.sharpe:.2f}"
        )

        # 3. 初始化族群
        population = self.initialize_population(pop_size, base_mat, rng)

        # 評估初始世代適應度
        for ind in population:
            ind.is_metrics = self.replay_engine.simulate_replay(is_bars, ind.matrix)
            ind.fitness = self.compute_fitness(ind.is_metrics)

        generation_history: List[GenerationSummary] = []

        # 4. 世代演化迴圈 (Generational Loop)
        for gen in range(1, num_gens + 1):
            # 排序族群：適應度由高到低
            population.sort(key=lambda ind: ind.fitness, reverse=True)

            best_ind = population[0]
            fitness_values = [ind.fitness for ind in population]
            mean_fit = float(np.mean(fitness_values))
            std_fit = float(np.std(fitness_values))
            div_score = self.calculate_shannon_diversity(best_ind.matrix)

            summary = GenerationSummary(
                generation=gen,
                best_fitness=best_ind.fitness,
                mean_fitness=mean_fit,
                fitness_std=std_fit,
                best_sharpe_is=best_ind.is_metrics.sharpe if best_ind.is_metrics else 0.0,
                best_ann_return_is=best_ind.is_metrics.annualized_return if best_ind.is_metrics else 0.0,
                best_max_dd_is=best_ind.is_metrics.max_drawdown if best_ind.is_metrics else 0.0,
                diversity_score=div_score,
            )
            generation_history.append(summary)

            # 若為最後一代則不再產生子代
            if gen == num_gens:
                break

            # 菁英保留 (Elitism)
            next_generation: List[GeneticIndividual] = []
            for elite_idx in range(min(elitism_count, len(population))):
                next_generation.append(copy.deepcopy(population[elite_idx]))

            # 產生剩餘子代
            while len(next_generation) < pop_size:
                p1 = self.selection_tournament(population, k=3, rng=rng)
                p2 = self.selection_tournament(population, k=3, rng=rng)

                c1_mat, c2_mat = self.crossover(p1.matrix, p2.matrix, cross_rate, rng)
                c1_mat = self.mutate(c1_mat, mut_rate, rng)
                c2_mat = self.mutate(c2_mat, mut_rate, rng)

                c1_metrics = self.replay_engine.simulate_replay(is_bars, c1_mat)
                c1_fit = self.compute_fitness(c1_metrics)
                next_generation.append(GeneticIndividual(
                    matrix=c1_mat,
                    fitness=c1_fit,
                    is_metrics=c1_metrics,
                    generation_born=gen,
                ))

                if len(next_generation) < pop_size:
                    c2_metrics = self.replay_engine.simulate_replay(is_bars, c2_mat)
                    c2_fit = self.compute_fitness(c2_metrics)
                    next_generation.append(GeneticIndividual(
                        matrix=c2_mat,
                        fitness=c2_fit,
                        is_metrics=c2_metrics,
                        generation_born=gen,
                    ))

            population = next_generation

        # 5. 終審驗證：對最優菁英個體執行 Out-of-Sample 盲測驗證
        population.sort(key=lambda ind: ind.fitness, reverse=True)
        champion = population[0]

        champ_is_metrics = champion.is_metrics or self.replay_engine.simulate_replay(is_bars, champion.matrix)
        champ_oos_metrics = self.replay_engine.simulate_replay(oos_bars, champion.matrix)

        # 6. 防過擬合驗證指標精算
        is_sharpe = max(0.01, champ_is_metrics.sharpe)
        oos_sharpe = champ_oos_metrics.sharpe
        wfo_eff = oos_sharpe / is_sharpe if is_sharpe > 0 else 0.0

        base_oos_sharpe = base_oos_metrics.sharpe
        sharpe_improvement_pct = (
            (oos_sharpe - base_oos_sharpe) / max(0.10, abs(base_oos_sharpe)) * 100.0
        )

        base_oos_mdd = max(0.01, base_oos_metrics.max_drawdown)
        mdd_expansion_pct = (
            (champ_oos_metrics.max_drawdown - base_oos_mdd) / base_oos_mdd * 100.0
        )

        diversity = self.calculate_shannon_diversity(champion.matrix)

        # 7. 晉級裁定 (Promotion Gate Criteria)
        promotable = True
        rejection_reasons = []

        if wfo_eff < self.DEFAULT_WFO_MIN_EFFICIENCY:
            promotable = False
            rejection_reasons.append(
                f"WFO Efficiency 偏低 ({wfo_eff:.2f} < {self.DEFAULT_WFO_MIN_EFFICIENCY:.2f})"
            )

        if sharpe_improvement_pct < (self.DEFAULT_MIN_SHARPE_EDGE * 100.0):
            promotable = False
            rejection_reasons.append(
                f"OOS Sharpe 提升未達門檻 (+{sharpe_improvement_pct:.1f}% < +{self.DEFAULT_MIN_SHARPE_EDGE*100:.0f}%)"
            )

        if mdd_expansion_pct > (self.DEFAULT_MAX_MDD_EXPANSION * 100.0):
            promotable = False
            rejection_reasons.append(
                f"OOS 最大回撤擴張超標 (+{mdd_expansion_pct:.1f}% > +{self.DEFAULT_MAX_MDD_EXPANSION*100:.0f}%)"
            )

        if diversity < self.DEFAULT_MIN_SHANNON_DIVERSITY:
            promotable = False
            rejection_reasons.append(
                f"香農因子多樣性過低 ({diversity:.2f} < {self.DEFAULT_MIN_SHANNON_DIVERSITY:.2f})，過度集中單因子"
            )

        if promotable:
            promotion_reason = (
                f"✅ 通過遺傳演化終審晉級門檻：OOS Sharpe 提升 +{sharpe_improvement_pct:.1f}% "
                f"({base_oos_sharpe:.2f} ➔ {oos_sharpe:.2f}), WFO 效率 {wfo_eff:.2f}, "
                f"回撤變化 {mdd_expansion_pct:+.1f}%, 因子香農多樣性 {diversity:.2f}"
            )
        else:
            promotion_reason = f"⚠️ 未達晉級門檻，維持基準權重：{'; '.join(rejection_reasons)}"

        promoted_applied = False
        if promotable and self.auto_promote:
            promoted_applied = self._apply_matrix_to_settings(champion.matrix)

        report = GeneticEvolutionReport(
            run_id=run_id,
            timestamp=now_ts,
            population_size=pop_size,
            generations=num_gens,
            mutation_rate=mut_rate,
            crossover_rate=cross_rate,
            baseline_matrix=base_mat,
            baseline_is_metrics=base_is_metrics,
            baseline_oos_metrics=base_oos_metrics,
            best_matrix=champion.matrix,
            best_is_metrics=champ_is_metrics,
            best_oos_metrics=champ_oos_metrics,
            wfo_efficiency=wfo_eff,
            sharpe_improvement_pct=sharpe_improvement_pct,
            mdd_expansion_pct=mdd_expansion_pct,
            factor_shannon_diversity=diversity,
            is_promotable=promotable,
            promotion_reason=promotion_reason,
            generation_history=generation_history,
            promoted_to_settings=promoted_applied,
        )

        # 8. 持久化至 Redis 與內存
        self._save_report_to_redis(report)

        return report

    def _apply_matrix_to_settings(self, matrix: FactorWeightMatrix) -> bool:
        """將驗證通過之基因矩陣持久化至 SettingsService / Repository"""
        if not self.settings_service:
            return False
        try:
            mat_dict = matrix.to_dict()
            json_str = json.dumps(mat_dict)
            if hasattr(self.settings_service, "set_setting"):
                self.settings_service.set_setting("tactical_phase_factor_weights", json_str)
                self.settings_service.set_setting("tactical_rotation_min_edge_pct", float(matrix.min_edge_pct))
                self.settings_service.set_setting("factor_liquidity_premium_weight", float(matrix.liquidity_premium_weight))
            elif hasattr(self.settings_service, "set"):
                self.settings_service.set(self.user_id, "tactical_phase_factor_weights", json_str)
                self.settings_service.set(self.user_id, "tactical_rotation_min_edge_pct", float(matrix.min_edge_pct))
                self.settings_service.set(self.user_id, "factor_liquidity_premium_weight", float(matrix.liquidity_premium_weight))
            logger.info(f"Successfully promoted evolved genetic factor matrix for {self.user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply genetic matrix to settings: {e}")
            return False

    def _save_report_to_redis(self, report: GeneticEvolutionReport) -> None:
        """持久化演化報告至 Redis 與記憶體快取"""
        rep_dict = report.to_dict()
        self._MEMORY_LATEST_REPORT[self.user_id] = rep_dict
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                r.set(f"{self._REDIS_LATEST_KEY_PREFIX}:{self.user_id}", json.dumps(rep_dict), ex=2592000)  # 30 天有效
                # 歷史記錄存入 List
                r.lpush(f"{self._REDIS_HISTORY_KEY_PREFIX}:{self.user_id}", json.dumps(rep_dict))
                r.ltrim(f"{self._REDIS_HISTORY_KEY_PREFIX}:{self.user_id}", 0, 19)  # 保留最近 20 次
        except Exception as e:
            logger.debug(f"Non-blocking Redis write for genetic evolution report: {e}")

    def load_latest_report(self) -> Optional[Dict[str, Any]]:
        """讀取最新演化終審報告"""
        if self.user_id in self._MEMORY_LATEST_REPORT:
            return self._MEMORY_LATEST_REPORT[self.user_id]
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                raw = r.get(f"{self._REDIS_LATEST_KEY_PREFIX}:{self.user_id}")
                if raw:
                    data = json.loads(raw)
                    self._MEMORY_LATEST_REPORT[self.user_id] = data
                    return data
        except Exception as e:
            logger.debug(f"Non-blocking Redis read for genetic report: {e}")
        return None
