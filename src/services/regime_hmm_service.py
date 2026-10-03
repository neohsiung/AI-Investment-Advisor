"""
Bayesian Hidden Markov Model Regime Transition & Online Nowcasting Service (O1)
貝葉斯隱馬爾可夫體制轉移與在線現在預測服務
=============================================================================
Provides continuous posterior regime belief distributions across:
1. BULL_MOMENTUM: Risk-On expansion (trend positive, low VIX, positive returns).
2. NEUTRAL_RANGE: Choppy rotation / consolidation (trend flat, medium VIX).
3. BEAR_CRISIS: Risk-Off defensive contraction (trend negative, high/spiking VIX).

Key Architectural Innovations:
1. Eliminates discrete boundary whipsaws & jumping step functions.
2. Incorporates Markovian state persistence & transition probabilities.
3. Computes Shannon Entropy & Regime Confidence Index [0.0, 1.0].
4. Enables Soft Mixture Policy Blending for cash buffers, target beta, and M6 multi-factor weights.
5. Supports k-step forward state prediction and sequential time-series filtering.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class RegimeState(str, Enum):
    """Hidden market regime states."""
    BULL = "BULL"
    NEUTRAL = "NEUTRAL"
    BEAR = "BEAR"


@dataclass
class RegimeObservation:
    """Multivariate observable market data vector at time t."""
    spy_price: float
    spy_sma200: float
    vix: float
    return_5d: float = 0.0
    realized_vol_20d: float = 0.16

    @property
    def trend_ratio(self) -> float:
        """Percentage distance of SPY relative to SMA200: (SPY - SMA200) / SMA200."""
        if self.spy_sma200 <= 0.0:
            return 0.0
        return (self.spy_price - self.spy_sma200) / self.spy_sma200

    def to_dict(self) -> dict[str, float]:
        return {
            "spy_price": round(self.spy_price, 2),
            "spy_sma200": round(self.spy_sma200, 2),
            "trend_ratio": round(self.trend_ratio, 4),
            "vix": round(self.vix, 2),
            "return_5d": round(self.return_5d, 4),
            "realized_vol_20d": round(self.realized_vol_20d, 4),
        }


@dataclass
class RegimePosterior:
    """Posterior probability distribution and risk policy blend at time t."""
    probabilities: dict[str, float]
    dominant_regime: RegimeState
    entropy: float
    confidence: float
    blended_cash_reserve_pct: float
    blended_target_beta: float
    transition_matrix: list[list[float]] = field(default_factory=list)
    observation_summary: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
            "dominant_regime": self.dominant_regime.value,
            "entropy": round(self.entropy, 4),
            "confidence": round(self.confidence, 4),
            "blended_cash_reserve_pct": round(self.blended_cash_reserve_pct, 2),
            "blended_target_beta": round(self.blended_target_beta, 3),
            "transition_matrix": [[round(x, 4) for x in row] for row in self.transition_matrix],
            "observation_summary": self.observation_summary,
        }


class BayesianRegimeHMMService:
    """Bayesian Online Filtering and Hidden Markov Model for Macro Market Regimes."""

    DEFAULT_PERSISTENCE = 0.92               # Diagonal transition persistence
    DEFAULT_MIN_CONFIDENCE = 0.40            # Minimum confidence before warning of ambiguity
    DEFAULT_VIX_BEAR_THRESHOLD = 28.0        # VIX bear center boundary
    DEFAULT_VIX_BULL_THRESHOLD = 19.0        # VIX bull center boundary

    # Canonical Emission Distribution Profiles (Mean, Std)
    # [trend_ratio, vix, return_5d]
    EMISSION_PROFILES: dict[RegimeState, dict[str, tuple[float, float]]] = {
        RegimeState.BULL: {
            "trend_ratio": (0.05, 0.04),     # S&P comfortably above 200MA
            "vix": (15.0, 3.5),              # Subdued, calm volatility
            "return_5d": (0.015, 0.020),     # Positive upward drift
        },
        RegimeState.NEUTRAL: {
            "trend_ratio": (0.00, 0.03),     # Oscillating around 200MA
            "vix": (21.0, 4.0),              # Normal baseline volatility
            "return_5d": (0.000, 0.025),     # Flat / choppy returns
        },
        RegimeState.BEAR: {
            "trend_ratio": (-0.06, 0.05),    # Broken below 200MA
            "vix": (32.0, 7.0),              # Elevated fear / panic volatility
            "return_5d": (-0.025, 0.040),    # Negative downward drift
        },
    }

    # Policy Baseline Values for Blending
    REGIME_POLICIES: dict[RegimeState, dict[str, float]] = {
        RegimeState.BULL: {
            "cash_reserve_pct": 5.0,
            "target_beta": 1.10,
        },
        RegimeState.NEUTRAL: {
            "cash_reserve_pct": 20.0,
            "target_beta": 0.85,
        },
        RegimeState.BEAR: {
            "cash_reserve_pct": 50.0,
            "target_beta": 0.40,
        },
    }

    def __init__(self, user_id: str = "default_user", settings_repo: Any = None):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
        if not self.settings_repo:
            return default
        try:
            val = self.settings_repo.get(self.user_id, key)
            if val is None:
                return default
            if val_type is bool:
                return str(val).lower() in ("true", "1", "yes")
            return val_type(val)
        except Exception as e:
            logger.warning(f"Error loading setting '{key}' ({e}); using default {default}")
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting("hmm_regime_enabled", True, bool)

    @property
    def transition_persistence(self) -> float:
        return float(self._get_setting("hmm_transition_persistence", self.DEFAULT_PERSISTENCE, float))

    @property
    def min_confidence_threshold(self) -> float:
        return float(self._get_setting("hmm_min_confidence_threshold", self.DEFAULT_MIN_CONFIDENCE, float))

    @property
    def vix_bear_threshold(self) -> float:
        return float(self._get_setting("hmm_vix_bear_threshold", self.DEFAULT_VIX_BEAR_THRESHOLD, float))

    @property
    def vix_bull_threshold(self) -> float:
        return float(self._get_setting("hmm_vix_bull_threshold", self.DEFAULT_VIX_BULL_THRESHOLD, float))

    def get_transition_matrix(self, persistence: Optional[float] = None) -> list[list[float]]:
        """
        Construct 3x3 state transition matrix A where A[i][j] = P(S_t = j | S_{t-1} = i).
        State order: [0: BULL, 1: NEUTRAL, 2: BEAR].
        """
        p = float(persistence if persistence is not None else self.transition_persistence)
        p = max(0.50, min(0.99, p))
        rem = 1.0 - p

        # Off-diagonal transitions are conditioned on market topology:
        # Bull transitions primarily to Neutral (85% of rem), rarely straight to Bear (15% of rem).
        # Neutral transitions equally to Bull (50%) and Bear (50%).
        # Bear transitions primarily to Neutral (85% of rem), rarely straight to Bull (15% of rem).
        matrix = [
            [p, rem * 0.85, rem * 0.15],         # From BULL
            [rem * 0.50, p, rem * 0.50],         # From NEUTRAL
            [rem * 0.15, rem * 0.85, p],         # From BEAR
        ]
        return matrix

    @staticmethod
    def _gaussian_pdf(x: float, mean: float, std: float) -> float:
        """Compute 1D Gaussian probability density with numerical floor."""
        std = max(1e-4, std)
        coeff = 1.0 / (math.sqrt(2.0 * math.pi) * std)
        exponent = -0.5 * (((x - mean) / std) ** 2)
        # Avoid underflow beyond 700
        if exponent < -700.0:
            return 1e-15
        return max(1e-15, coeff * math.exp(exponent))

    def compute_emission_likelihood(self, obs: RegimeObservation, state: RegimeState) -> float:
        """
        Compute joint emission likelihood P(O_t | S_t = state) across trend, VIX, and returns.
        """
        profile = self.EMISSION_PROFILES[state]
        
        # Adaptive VIX mean tuning if user overridden via settings
        vix_mean, vix_std = profile["vix"]
        if state == RegimeState.BEAR and self.settings_repo:
            vix_mean = max(vix_mean, self.vix_bear_threshold)
        elif state == RegimeState.BULL and self.settings_repo:
            vix_mean = min(vix_mean, self.vix_bull_threshold)

        p_trend = self._gaussian_pdf(obs.trend_ratio, profile["trend_ratio"][0], profile["trend_ratio"][1])
        p_vix = self._gaussian_pdf(obs.vix, vix_mean, vix_std)
        p_ret = self._gaussian_pdf(obs.return_5d, profile["return_5d"][0], profile["return_5d"][1])

        # Joint likelihood under conditional independence assumption
        joint_likelihood = p_trend * p_vix * p_ret
        return max(1e-20, joint_likelihood)

    def update_beliefs(
        self,
        observation: RegimeObservation | dict[str, float],
        prior_probs: Optional[dict[str, float]] = None,
    ) -> RegimePosterior:
        """
        Execute Bayesian online forward filtering step:
        1. Predict prior state: p(S_t = j) = sum_i p(S_{t-1} = i) * A_{i, j}
        2. Update with emission likelihood: alpha(j) = p(S_t = j) * P(O_t | S_t = j)
        3. Normalize: pi_t(j) = alpha(j) / sum_k alpha(k)
        """
        if isinstance(observation, dict):
            obs = RegimeObservation(
                spy_price=float(observation.get("spy_price", 0.0)),
                spy_sma200=float(observation.get("spy_sma200", 0.0)),
                vix=float(observation.get("vix", 20.0)),
                return_5d=float(observation.get("return_5d", 0.0)),
                realized_vol_20d=float(observation.get("realized_vol_20d", 0.16)),
            )
        else:
            obs = observation

        states = [RegimeState.BULL, RegimeState.NEUTRAL, RegimeState.BEAR]
        num_states = len(states)

        # Initialize uniform prior if not provided
        if not prior_probs:
            prior_vec = [1.0 / num_states] * num_states
        else:
            raw = [float(prior_probs.get(s.value, 1.0 / num_states)) for s in states]
            s_raw = sum(raw) if sum(raw) > 0 else 1.0
            prior_vec = [r / s_raw for r in raw]

        # 1. Prediction step via Transition Matrix
        A = self.get_transition_matrix()
        predicted_priors = [0.0] * num_states
        for j in range(num_states):
            for i in range(num_states):
                predicted_priors[j] += prior_vec[i] * A[i][j]

        # 2. Update step via Emission Likelihood
        unnorm_posteriors = [0.0] * num_states
        for j, state in enumerate(states):
            likelihood = self.compute_emission_likelihood(obs, state)
            unnorm_posteriors[j] = predicted_priors[j] * likelihood

        # 3. Normalization
        total_mass = sum(unnorm_posteriors)
        if total_mass <= 0.0 or math.isnan(total_mass):
            normalized_posteriors = [1.0 / num_states] * num_states
        else:
            normalized_posteriors = [p / total_mass for p in unnorm_posteriors]

        prob_dict = {
            RegimeState.BULL.value: normalized_posteriors[0],
            RegimeState.NEUTRAL.value: normalized_posteriors[1],
            RegimeState.BEAR.value: normalized_posteriors[2],
        }

        # 4. Dominant Regime Determination
        best_state = max(states, key=lambda s: prob_dict[s.value])

        # 5. Shannon Entropy & Confidence Calculation
        # H(pi) = - sum pi * log2(pi)
        entropy = 0.0
        for p in normalized_posteriors:
            if p > 1e-12:
                entropy -= p * math.log2(p)

        max_entropy = math.log2(num_states)  # log2(3) ~ 1.585
        confidence = max(0.0, min(1.0, 1.0 - (entropy / max_entropy)))

        # 6. Continuous Soft Mixture Policy Blending
        w_bull = prob_dict[RegimeState.BULL.value]
        w_neutral = prob_dict[RegimeState.NEUTRAL.value]
        w_bear = prob_dict[RegimeState.BEAR.value]

        blended_cash = (
            w_bull * self.REGIME_POLICIES[RegimeState.BULL]["cash_reserve_pct"]
            + w_neutral * self.REGIME_POLICIES[RegimeState.NEUTRAL]["cash_reserve_pct"]
            + w_bear * self.REGIME_POLICIES[RegimeState.BEAR]["cash_reserve_pct"]
        )

        blended_beta = (
            w_bull * self.REGIME_POLICIES[RegimeState.BULL]["target_beta"]
            + w_neutral * self.REGIME_POLICIES[RegimeState.NEUTRAL]["target_beta"]
            + w_bear * self.REGIME_POLICIES[RegimeState.BEAR]["target_beta"]
        )

        return RegimePosterior(
            probabilities=prob_dict,
            dominant_regime=best_state,
            entropy=round(entropy, 4),
            confidence=round(confidence, 4),
            blended_cash_reserve_pct=round(blended_cash, 2),
            blended_target_beta=round(blended_beta, 3),
            transition_matrix=A,
            observation_summary=obs.to_dict(),
        )

    def blend_weights(
        self,
        bull_weights: dict[str, float],
        neutral_weights: dict[str, float],
        bear_weights: dict[str, float],
        probs: dict[str, float],
    ) -> dict[str, float]:
        """
        Seamlessly blend arbitrary weight dictionaries across regime probabilities.
        w_blended[k] = p_bull * w_bull[k] + p_neutral * w_neutral[k] + p_bear * w_bear[k]
        """
        p_bull = float(probs.get(RegimeState.BULL.value, 0.0))
        p_neu = float(probs.get(RegimeState.NEUTRAL.value, 0.0))
        p_bear = float(probs.get(RegimeState.BEAR.value, 0.0))

        # Normalize probabilities if sum deviates from 1.0
        total_p = p_bull + p_neu + p_bear
        if total_p > 0:
            p_bull /= total_p
            p_neu /= total_p
            p_bear /= total_p

        all_keys = set(bull_weights.keys()) | set(neutral_weights.keys()) | set(bear_weights.keys())
        blended: dict[str, float] = {}

        for k in all_keys:
            wb = float(bull_weights.get(k, 0.0))
            wn = float(neutral_weights.get(k, 0.0))
            we = float(bear_weights.get(k, 0.0))
            blended[k] = round(p_bull * wb + p_neu * wn + p_bear * we, 4)

        return blended

    def predict_next_regime(
        self,
        current_probs: dict[str, float],
        horizon_days: int = 1,
    ) -> dict[str, float]:
        """
        Forecast regime distribution k days ahead via Markov chain powers A^k:
        pi_{t+k} = pi_t * A^k
        """
        horizon = max(1, min(60, int(horizon_days)))
        states = [RegimeState.BULL, RegimeState.NEUTRAL, RegimeState.BEAR]
        prob_vec = [float(current_probs.get(s.value, 1.0 / 3.0)) for s in states]

        A = self.get_transition_matrix()

        # Repeated vector-matrix multiplication
        cur = list(prob_vec)
        for _ in range(horizon):
            nxt = [0.0] * len(states)
            for j in range(len(states)):
                for i in range(len(states)):
                    nxt[j] += cur[i] * A[i][j]
            cur = nxt

        total_sum = sum(cur) if sum(cur) > 0 else 1.0
        return {
            RegimeState.BULL.value: round(cur[0] / total_sum, 4),
            RegimeState.NEUTRAL.value: round(cur[1] / total_sum, 4),
            RegimeState.BEAR.value: round(cur[2] / total_sum, 4),
        }

    def batch_filter(
        self,
        observations: list[RegimeObservation | dict[str, float]],
    ) -> list[RegimePosterior]:
        """
        Filter a historical sequence of observations chronologically, passing forward posterior beliefs.
        """
        posteriors: list[RegimePosterior] = []
        prior: Optional[dict[str, float]] = None

        for obs in observations:
            posterior = self.update_beliefs(observation=obs, prior_probs=prior)
            posteriors.append(posterior)
            prior = posterior.probabilities

        return posteriors
