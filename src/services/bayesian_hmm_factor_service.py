"""
Bayesian Hidden Markov Model Continuous Multi-Factor Allocator (Phase 38)
========================================================================
在線連續貝葉斯濾波與隱馬爾可夫機制轉換因子動態配置服務

核心架構：
1. 四大市場風格體制隱狀態空間 (Tactical Market Regimes, K=4)：
   - S1: BULL_ACCELERATION (順勢多頭動能加速)
   - S2: EARLY_REBOUND (恐慌拐點 / 超跌強彈)
   - S3: LATE_CYCLE_VALUE (景氣高檔 / 價值與防守現金流領先)
   - S4: DEFENSIVE_CONSOLIDATION (震盪盤整 / 低波動品質防守)
2. 馬爾可夫轉移機率矩陣 P (4x4 Transition Probability Matrix)：
   - 具有可調節的對角線粘性 (Diagonal Persistence, p ~ 0.94)。
   - 拓撲非對稱轉移機率矩陣，精確映射宏觀週期演變路徑（如：Bull -> Late Cycle -> Defense -> Rebound -> Bull）。
3. 多元連續高斯觀測向量 y_t (Multivariate Observation Vector)：
   - trend_ratio: SPY 距 200MA 偏離度 ((SPY - SMA200) / SMA200)
   - vix: VIX 隱含波動率水準
   - vix_z_score: VIX 滾動 30 日 Z-Score
   - yield_spread: 10Y - 2Y 美債殖利率利差 (%)
   - return_5d: SPY 5 日累積報酬率
4. 遞歸在線漢密爾頓貝葉斯濾波 (Recursive Online Hamilton Filter)：
   - 先驗預測：π_{t|t-1} = P^T π_{t-1|t-1}
   - 多元高斯似然度：η_{t, k} = f(y_t | S_t = k)
   - 後驗更新與歸一化：π_{t|t, k} = (π_{t|t-1, k} * η_{t, k}) / Σ_j (π_{t|t-1, j} * η_{t, j})
5. 連續平滑因子混合期望值 (Continuous Factor Mixture Expectation)：
   - w*_t = Σ_{k=1}^4 π_{t, k} * w_k
   - 消除傳統離散門檻跳躍之階梯斷層與調倉磨損。
6. 香農熵與體制轉換模糊守衛 (Shannon Entropy & Transition Ambiguity Guard)：
   - H(π) = - Σ π_k log2(π_k) in [0.0, 2.0]
   - 當 H(π) >= H_threshold 時，識別市場處於體制拐點模糊期，自適應向低波動 (Low Vol) 與品質 (Quality) 防守錨點傾斜。
7. 跨進程分散式狀態同步 (Redis Cache Key: bayesian_hmm:factor_belief:{user_id})。
"""

from __future__ import annotations

import copy
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from src.config.owner import resolve_user_id
from src.services.tactical_factor_rotation_service import (
    TacticalMarketPhase,
)

logger = logging.getLogger("BayesianHMMFactorService")

FACTOR_NAMES = [
    "momentum",
    "smart_money",
    "liquidity_premium",
    "quality",
    "value",
    "low_vol",
]

# 四大市場週期基準因子權重矩陣
DEFAULT_PHASE_BASE_WEIGHTS: Dict[TacticalMarketPhase, Dict[str, float]] = {
    TacticalMarketPhase.BULL_ACCELERATION: {
        "momentum": 0.35,
        "smart_money": 0.25,
        "quality": 0.20,
        "liquidity_premium": 0.10,
        "value": 0.10,
        "low_vol": 0.00,
    },
    TacticalMarketPhase.EARLY_REBOUND: {
        "momentum": 0.30,
        "liquidity_premium": 0.25,
        "smart_money": 0.20,
        "quality": 0.15,
        "value": 0.10,
        "low_vol": 0.00,
    },
    TacticalMarketPhase.LATE_CYCLE_VALUE: {
        "value": 0.35,
        "quality": 0.25,
        "liquidity_premium": 0.15,
        "low_vol": 0.15,
        "smart_money": 0.05,
        "momentum": 0.05,
    },
    TacticalMarketPhase.DEFENSIVE_CONSOLIDATION: {
        "low_vol": 0.35,
        "quality": 0.35,
        "value": 0.15,
        "liquidity_premium": 0.10,
        "smart_money": 0.05,
        "momentum": 0.00,
    },
}

# 模糊體制防守錨點配置
DEFENSIVE_ANCHOR_WEIGHTS: Dict[str, float] = {
    "low_vol": 0.45,
    "quality": 0.45,
    "value": 0.10,
    "liquidity_premium": 0.00,
    "smart_money": 0.00,
    "momentum": 0.00,
}


@dataclass
class HMMFactorObservation:
    """Multivariate market observation vector at time t for Bayesian factor filtering."""
    trend_ratio: float = 0.0         # (SPY - SMA200) / SMA200
    vix: float = 18.0                # Current VIX level
    vix_z_score: float = 0.0         # Rolling 30d Z-score of VIX
    yield_spread: float = 0.50       # 10Y - 2Y yield spread in %
    return_5d: float = 0.0           # SPY 5-day cumulative return
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, float]:
        return {
            "trend_ratio": round(self.trend_ratio, 4),
            "vix": round(self.vix, 2),
            "vix_z_score": round(self.vix_z_score, 2),
            "yield_spread": round(self.yield_spread, 3),
            "return_5d": round(self.return_5d, 4),
        }


@dataclass
class HMMFactorPosterior:
    """Posterior regime distribution, entropy metrics, and continuous factor blend."""
    probabilities: Dict[str, float]
    dominant_phase: TacticalMarketPhase
    entropy: float
    ambiguity_index: float
    confidence: float
    continuous_weights: Dict[str, float]
    guarded_weights: Dict[str, float]
    is_entropy_guard_active: bool
    observation: Dict[str, float] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
            "dominant_phase": self.dominant_phase.value,
            "entropy": round(self.entropy, 4),
            "ambiguity_index": round(self.ambiguity_index, 4),
            "confidence": round(self.confidence, 4),
            "continuous_weights": {k: round(v, 4) for k, v in self.continuous_weights.items()},
            "guarded_weights": {k: round(v, 4) for k, v in self.guarded_weights.items()},
            "is_entropy_guard_active": self.is_entropy_guard_active,
            "observation": self.observation,
            "timestamp": self.timestamp,
        }


class BayesianHMMFactorService:
    """
    Bayesian Hidden Markov Model Continuous Multi-Factor Allocator.
    Computes continuous online regime posterior beliefs and frictionless factor mixtures.
    """

    STATES: List[TacticalMarketPhase] = [
        TacticalMarketPhase.BULL_ACCELERATION,
        TacticalMarketPhase.EARLY_REBOUND,
        TacticalMarketPhase.LATE_CYCLE_VALUE,
        TacticalMarketPhase.DEFENSIVE_CONSOLIDATION,
    ]

    DEFAULT_PERSISTENCE = 0.94
    DEFAULT_ENTROPY_DEFENSE_THRESHOLD = 1.15
    DEFAULT_MAX_ENTROPY = 2.0  # log2(4) = 2.0

    # Canonical emission profiles: (mean, std) for [trend_ratio, vix, vix_z_score, yield_spread, return_5d]
    EMISSION_PROFILES: Dict[TacticalMarketPhase, Dict[str, Tuple[float, float]]] = {
        TacticalMarketPhase.BULL_ACCELERATION: {
            "trend_ratio": (0.05, 0.035),
            "vix": (15.0, 3.5),
            "vix_z_score": (-0.5, 0.8),
            "yield_spread": (0.75, 0.45),
            "return_5d": (0.015, 0.018),
        },
        TacticalMarketPhase.EARLY_REBOUND: {
            "trend_ratio": (-0.02, 0.040),
            "vix": (26.0, 5.0),
            "vix_z_score": (-0.8, 1.0),
            "yield_spread": (0.20, 0.50),
            "return_5d": (0.025, 0.025),
        },
        TacticalMarketPhase.LATE_CYCLE_VALUE: {
            "trend_ratio": (0.02, 0.030),
            "vix": (19.0, 3.5),
            "vix_z_score": (0.2, 0.8),
            "yield_spread": (-0.35, 0.30),
            "return_5d": (0.002, 0.018),
        },
        TacticalMarketPhase.DEFENSIVE_CONSOLIDATION: {
            "trend_ratio": (-0.06, 0.045),
            "vix": (32.0, 6.0),
            "vix_z_score": (1.5, 1.0),
            "yield_spread": (-0.10, 0.55),
            "return_5d": (-0.025, 0.030),
        },
    }

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_service: Optional[Any] = None,
    ):
        try:
            self.user_id = resolve_user_id(user_id) if user_id else "default"
        except Exception:
            self.user_id = user_id or "default"
        self.settings_service = settings_service
        self.market_service = market_service
        self._memory_posterior_cache: Optional[HMMFactorPosterior] = None

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service:
            try:
                val = self.settings_service.get_setting(key, default, user_id=self.user_id)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to load setting '{key}': {e}")
        return default

    @property
    def is_enabled(self) -> bool:
        val = self._get_setting("enable_bayesian_hmm_factor_allocation", True)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    @property
    def transition_persistence(self) -> float:
        try:
            val = float(self._get_setting("bayesian_hmm_transition_stickiness", self.DEFAULT_PERSISTENCE))
            return max(0.70, min(0.99, val))
        except (ValueError, TypeError):
            return self.DEFAULT_PERSISTENCE

    @property
    def entropy_defense_threshold(self) -> float:
        try:
            val = float(self._get_setting("bayesian_hmm_entropy_defense_threshold", self.DEFAULT_ENTROPY_DEFENSE_THRESHOLD))
            return max(0.50, min(1.90, val))
        except (ValueError, TypeError):
            return self.DEFAULT_ENTROPY_DEFENSE_THRESHOLD

    @property
    def is_entropy_guard_enabled(self) -> bool:
        val = self._get_setting("enable_bayesian_hmm_entropy_guard", True)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    def get_transition_matrix(self, persistence: Optional[float] = None) -> np.ndarray:
        """
        Construct 4x4 state transition matrix P where P[i, j] = P(S_t = j | S_{t-1} = i).
        State order: [0: BULL_ACCELERATION, 1: EARLY_REBOUND, 2: LATE_CYCLE_VALUE, 3: DEFENSIVE_CONSOLIDATION].
        """
        p = float(persistence if persistence is not None else self.transition_persistence)
        p = max(0.70, min(0.99, p))
        rem = 1.0 - p

        # Off-diagonal probability transitions reflecting macro cycle mechanics:
        # Bull: 60% Late Cycle, 35% Defense, 5% Rebound
        # Rebound: 75% Bull, 20% Defense, 5% Late Cycle
        # Late Cycle: 70% Defense, 25% Bull, 5% Rebound
        # Defense: 80% Rebound, 15% Late Cycle, 5% Bull
        P = np.array([
            [p, rem * 0.05, rem * 0.60, rem * 0.35],  # BULL
            [rem * 0.75, p, rem * 0.05, rem * 0.20],  # REBOUND
            [rem * 0.25, rem * 0.05, p, rem * 0.70],  # LATE_CYCLE
            [rem * 0.05, rem * 0.80, rem * 0.15, p],  # DEFENSE
        ], dtype=float)

        # Ensure row stochastic normalization
        row_sums = P.sum(axis=1, keepdims=True)
        return P / row_sums

    @staticmethod
    def _gaussian_pdf(x: float, mean: float, std: float) -> float:
        """1D Gaussian probability density function with numerical underflow clamp."""
        std = max(1e-4, float(std))
        coeff = 1.0 / (math.sqrt(2.0 * math.pi) * std)
        exponent = -0.5 * (((x - mean) / std) ** 2)
        if exponent < -700.0:
            return 1e-20
        return max(1e-20, coeff * math.exp(exponent))

    def compute_emission_likelihood(
        self,
        obs: HMMFactorObservation,
        phase: TacticalMarketPhase,
    ) -> float:
        """
        Compute joint Gaussian emission likelihood P(O_t | S_t = phase) across
        trend, VIX, VIX Z-score, yield spread, and return.
        """
        profile = self.EMISSION_PROFILES[phase]

        p_trend = self._gaussian_pdf(obs.trend_ratio, *profile["trend_ratio"])
        p_vix = self._gaussian_pdf(obs.vix, *profile["vix"])
        p_vix_z = self._gaussian_pdf(obs.vix_z_score, *profile["vix_z_score"])
        p_yield = self._gaussian_pdf(obs.yield_spread, *profile["yield_spread"])
        p_ret = self._gaussian_pdf(obs.return_5d, *profile["return_5d"])

        joint = p_trend * p_vix * p_vix_z * p_yield * p_ret
        return max(1e-25, joint)

    def _redis_key(self) -> str:
        return f"bayesian_hmm:factor_belief:{self.user_id}"

    def _load_belief_from_redis(self) -> Optional[Dict[str, float]]:
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                raw = r.get(self._redis_key())
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return {k: float(v) for k, v in data.items()}
        except Exception as e:
            logger.debug(f"Redis HMM belief load skipped: {e}")
        return None

    def _save_belief_to_redis(self, probs: Dict[str, float]) -> None:
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                r.setex(self._redis_key(), 7 * 86400, json.dumps(probs))
        except Exception as e:
            logger.debug(f"Redis HMM belief save skipped: {e}")

    def update_beliefs_sync(
        self,
        observation: Union[HMMFactorObservation, Dict[str, float]],
        prior_probs: Optional[Dict[str, float]] = None,
        persist: bool = True,
    ) -> HMMFactorPosterior:
        """
        Synchronous execution of the online Hamilton Bayesian filter step:
        1. Prior prediction: pi_{t|t-1} = P^T pi_{t-1|t-1}
        2. Likelihood update: pi_{t|t, j} ~ pi_{t|t-1, j} * P(y_t | S_t = j)
        3. Normalization: Sum(pi_{t|t, j}) = 1.0
        4. Continuous multi-factor mixture calculation & Entropy Defense Guard.
        """
        if isinstance(observation, dict):
            obs = HMMFactorObservation(
                trend_ratio=float(observation.get("trend_ratio", 0.0)),
                vix=float(observation.get("vix", 18.0)),
                vix_z_score=float(observation.get("vix_z_score", 0.0)),
                yield_spread=float(observation.get("yield_spread", 0.50)),
                return_5d=float(observation.get("return_5d", 0.0)),
            )
        else:
            obs = observation

        num_states = len(self.STATES)

        # 0. Retrieve Prior vector
        if prior_probs is None:
            cached_prior = self._load_belief_from_redis()
            if cached_prior:
                prior_probs = cached_prior

        if not prior_probs:
            prior_vec = np.array([1.0 / num_states] * num_states, dtype=float)
        else:
            raw = [float(prior_probs.get(s.value, 1.0 / num_states)) for s in self.STATES]
            total_raw = sum(raw)
            prior_vec = np.array(raw, dtype=float) / (total_raw if total_raw > 0 else 1.0)

        # 1. Prediction step: pi_{t|t-1} = prior_vec @ P (where P[i, j] = P(j|i))
        P = self.get_transition_matrix()
        predicted_priors = prior_vec @ P

        # 2. Likelihood measurement step
        likelihoods = np.zeros(num_states, dtype=float)
        for j, state in enumerate(self.STATES):
            likelihoods[j] = self.compute_emission_likelihood(obs, state)

        unnorm_posteriors = predicted_priors * likelihoods

        # 3. Normalization
        total_mass = float(np.sum(unnorm_posteriors))
        if total_mass <= 0.0 or math.isnan(total_mass):
            normalized_posteriors = np.array([1.0 / num_states] * num_states, dtype=float)
        else:
            normalized_posteriors = unnorm_posteriors / total_mass

        prob_dict: Dict[str, float] = {
            self.STATES[i].value: float(normalized_posteriors[i]) for i in range(num_states)
        }

        # 4. Dominant Phase
        best_idx = int(np.argmax(normalized_posteriors))
        dominant_phase = self.STATES[best_idx]

        # 5. Shannon Entropy & Ambiguity Index
        entropy = 0.0
        for p in normalized_posteriors:
            if p > 1e-12:
                entropy -= float(p * math.log2(p))

        ambiguity_index = max(0.0, min(1.0, entropy / self.DEFAULT_MAX_ENTROPY))
        confidence = max(0.0, min(1.0, 1.0 - ambiguity_index))

        # 6. Continuous Factor Mixture: w* = sum(pi_k * w_k)
        continuous_weights: Dict[str, float] = {f: 0.0 for f in FACTOR_NAMES}
        for j, state in enumerate(self.STATES):
            weight_pi = float(normalized_posteriors[j])
            state_base = DEFAULT_PHASE_BASE_WEIGHTS.get(state, {})
            for f in FACTOR_NAMES:
                continuous_weights[f] += weight_pi * state_base.get(f, 0.0)

        # Simplex normalization for continuous weights
        sum_cw = sum(continuous_weights.values())
        if sum_cw > 0:
            for f in FACTOR_NAMES:
                continuous_weights[f] = round(continuous_weights[f] / sum_cw, 4)

        # 7. Shannon Entropy Ambiguity Guard
        is_guard_active = False
        guarded_weights = copy.deepcopy(continuous_weights)

        if self.is_entropy_guard_enabled and entropy >= self.entropy_defense_threshold:
            is_guard_active = True
            # Linear ramp from threshold to max entropy (2.0)
            threshold = self.entropy_defense_threshold
            excess_ratio = min(1.0, max(0.0, (entropy - threshold) / (self.DEFAULT_MAX_ENTROPY - threshold)))
            # Max anchor blending factor is 50%
            alpha_anchor = excess_ratio * 0.50

            for f in FACTOR_NAMES:
                anchor_w = DEFENSIVE_ANCHOR_WEIGHTS.get(f, 0.0)
                guarded_weights[f] = (1.0 - alpha_anchor) * continuous_weights[f] + alpha_anchor * anchor_w

            # Simplex normalize
            sum_gw = sum(guarded_weights.values())
            if sum_gw > 0:
                for f in FACTOR_NAMES:
                    guarded_weights[f] = round(guarded_weights[f] / sum_gw, 4)

        posterior = HMMFactorPosterior(
            probabilities=prob_dict,
            dominant_phase=dominant_phase,
            entropy=round(entropy, 4),
            ambiguity_index=round(ambiguity_index, 4),
            confidence=round(confidence, 4),
            continuous_weights=continuous_weights,
            guarded_weights=guarded_weights,
            is_entropy_guard_active=is_guard_active,
            observation=obs.to_dict(),
        )

        self._memory_posterior_cache = posterior

        if persist:
            self._save_belief_to_redis(prob_dict)

        return posterior

    async def update_beliefs(
        self,
        observation: Union[HMMFactorObservation, Dict[str, float]],
        prior_probs: Optional[Dict[str, float]] = None,
        persist: bool = True,
    ) -> HMMFactorPosterior:
        """Asynchronous wrapper for update_beliefs_sync."""
        return self.update_beliefs_sync(
            observation=observation,
            prior_probs=prior_probs,
            persist=persist,
        )

    def get_current_posterior(
        self,
        default_obs: Optional[HMMFactorObservation] = None,
    ) -> HMMFactorPosterior:
        """
        Retrieve current posterior belief from cache or generate from default/neutral observation.
        """
        if self._memory_posterior_cache is not None:
            return self._memory_posterior_cache

        cached_belief = self._load_belief_from_redis()
        obs = default_obs or HMMFactorObservation()
        return self.update_beliefs_sync(observation=obs, prior_probs=cached_belief, persist=False)

    def get_effective_continuous_weights(
        self,
        observation: Optional[Union[HMMFactorObservation, Dict[str, float]]] = None,
    ) -> Dict[str, float]:
        """
        Get final active continuous factor weights for portfolio optimization.
        Returns guarded weights if entropy guard is triggered, else continuous mixture weights.
        """
        if not self.is_enabled:
            # Fallback to neutral default
            return DEFAULT_PHASE_BASE_WEIGHTS[TacticalMarketPhase.BULL_ACCELERATION]

        if observation is not None:
            posterior = self.update_beliefs_sync(observation=observation, persist=True)
        else:
            posterior = self.get_current_posterior()

        return posterior.guarded_weights if posterior.is_entropy_guard_active else posterior.continuous_weights

    def batch_filter(
        self,
        observations: List[Union[HMMFactorObservation, Dict[str, float]]],
        initial_prior: Optional[Dict[str, float]] = None,
    ) -> List[HMMFactorPosterior]:
        """
        Filter a historical chronological sequence of observations, passing posterior forward.
        """
        results: List[HMMFactorPosterior] = []
        prior = initial_prior

        for obs in observations:
            posterior = self.update_beliefs_sync(
                observation=obs,
                prior_probs=prior,
                persist=False,
            )
            results.append(posterior)
            prior = posterior.probabilities

        return results

    def simulate_observation(self, regime_name: str) -> HMMFactorObservation:
        """Construct synthetic typical observation for a given regime."""
        r_upper = regime_name.upper()
        if "BULL" in r_upper:
            return HMMFactorObservation(
                trend_ratio=0.06,
                vix=14.5,
                vix_z_score=-0.6,
                yield_spread=0.85,
                return_5d=0.018,
            )
        elif "REBOUND" in r_upper or "PIVOT" in r_upper:
            return HMMFactorObservation(
                trend_ratio=-0.02,
                vix=25.0,
                vix_z_score=-0.9,
                yield_spread=0.25,
                return_5d=0.028,
            )
        elif "VALUE" in r_upper or "LATE" in r_upper:
            return HMMFactorObservation(
                trend_ratio=0.02,
                vix=18.5,
                vix_z_score=0.2,
                yield_spread=-0.40,
                return_5d=0.003,
            )
        else:  # DEFENSE
            return HMMFactorObservation(
                trend_ratio=-0.07,
                vix=34.0,
                vix_z_score=1.8,
                yield_spread=-0.15,
                return_5d=-0.030,
            )

    def reset_state(self) -> None:
        """Clear memory cache and Redis belief state."""
        self._memory_posterior_cache = None
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                r.delete(self._redis_key())
        except Exception as e:
            logger.debug(f"Redis HMM state clear skipped: {e}")
