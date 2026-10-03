"""
Regime-Conditioned Dynamic Multi-Factor Alpha Ensemble Service
體制感知動態多因子 Alpha 融合服務
=============================================================================
Computes cross-sectional standardized factor scores across 5 core pillars:
1. Momentum Factor (F_mom): 12-1M momentum, 60d relative strength vs SPY, RSI-14.
2. Quality Factor (F_qual): ROE, Gross/Operating Margin, Debt-to-Equity safety.
3. Value Factor (F_val): PEG ratio, forward P/E valuation percentile.
4. Low Volatility Factor (F_low_vol): 60d historical volatility & downside semi-variance.
5. Smart Money Factor (F_smart_money): Anchored VWAP premium & Volume Profile POC stability.

Dynamically adapts factor allocation weights conditioned on market regimes:
- Bull Trend: Momentum (40%) & Smart Money (25%) leading.
- Neutral / Sideways: Quality (35%) & Value (25%) leading.
- Bear / Crisis: Low Volatility (40%) & Quality (35%) leading.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


@dataclass
class RawFactorMetrics:
    """Raw underlying factor inputs for a single ticker."""
    ticker: str
    momentum_12_1: float = 0.0
    relative_strength_60d: float = 0.0
    rsi_14: float = 50.0
    roe: float = 0.15
    gross_margin: float = 0.30
    debt_to_equity: float = 0.80
    peg_ratio: float = 1.50
    forward_pe: float = 20.0
    annualized_vol_60d: float = 0.25
    downside_dev_60d: float = 0.18
    avwap_distance_pct: float = 0.02
    poc_support_pct: float = 0.03


@dataclass
class StandardizedFactorScores:
    """Normalized cross-sectional factor scores [0.0 to 1.0] for 5 pillars."""
    ticker: str
    momentum_score: float = 0.50
    quality_score: float = 0.50
    value_score: float = 0.50
    low_vol_score: float = 0.50
    smart_money_score: float = 0.50

    def to_dict(self) -> dict[str, float]:
        return {
            "momentum_score": round(self.momentum_score, 4),
            "quality_score": round(self.quality_score, 4),
            "value_score": round(self.value_score, 4),
            "low_vol_score": round(self.low_vol_score, 4),
            "smart_money_score": round(self.smart_money_score, 4),
        }


@dataclass
class EnsembleAlphaResult:
    """Final regime-conditioned composite alpha score and breakdown."""
    ticker: str
    composite_alpha_score: float
    regime: str
    factor_scores: StandardizedFactorScores
    factor_weights: dict[str, float]
    factor_contributions: dict[str, float]
    rank: int = 1
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "composite_alpha_score": round(self.composite_alpha_score, 4),
            "regime": self.regime,
            "factor_scores": self.factor_scores.to_dict(),
            "factor_weights": {k: round(v, 4) for k, v in self.factor_weights.items()},
            "factor_contributions": {k: round(v, 4) for k, v in self.factor_contributions.items()},
            "rank": self.rank,
            "reason": self.reason,
        }


class MultiFactorEnsembleService:
    """
    Orchestrates cross-sectional factor ranking and regime-conditioned dynamic alpha ensembling.
    體制感知動態多因子融合核心服務。
    """

    DEFAULT_WINSORIZE_STD = 3.0
    DEFAULT_MOM_WEIGHT_BULL = 0.40
    DEFAULT_QUAL_WEIGHT_NEUTRAL = 0.35
    DEFAULT_LOW_VOL_WEIGHT_BEAR = 0.40

    def __init__(
        self,
        user_id: str = "default_user",
        settings_service: Any | None = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service is not None:
            try:
                val = self.settings_service.get_setting(key)
                if val is not None:
                    return type(default)(val)
            except Exception as e:  # noqa: BLE001
                logger.debug("Failed to read setting %s: %s", key, e)
        return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("factor_ensemble_enabled", True))

    @property
    def winsorize_std(self) -> float:
        return float(self._get_setting("factor_winsorize_std", self.DEFAULT_WINSORIZE_STD))

    @property
    def mom_weight_bull(self) -> float:
        return float(self._get_setting("factor_momentum_weight_bull", self.DEFAULT_MOM_WEIGHT_BULL))

    @property
    def qual_weight_neutral(self) -> float:
        return float(self._get_setting("factor_quality_weight_neutral", self.DEFAULT_QUAL_WEIGHT_NEUTRAL))

    @property
    def low_vol_weight_bear(self) -> float:
        return float(self._get_setting("factor_low_vol_weight_bear", self.DEFAULT_LOW_VOL_WEIGHT_BEAR))

    def get_regime_weights(self, regime: str) -> dict[str, float]:
        """
        Return dynamic factor weights conditioned on macro regime:
        [momentum, quality, value, low_vol, smart_money]
        """
        regime_upper = regime.upper().strip()
        if "BULL" in regime_upper:
            w_mom = self.mom_weight_bull
            # Bullish allocation: momentum 40%, smart money 25%, quality 15%, value 10%, low vol 10%
            return {
                "momentum": w_mom,
                "smart_money": 0.25,
                "quality": 0.15,
                "value": 0.10,
                "low_vol": max(0.05, 1.0 - (w_mom + 0.25 + 0.15 + 0.10)),
            }
        elif "BEAR" in regime_upper or "CRISIS" in regime_upper:
            w_low_vol = self.low_vol_weight_bear
            # Defensive allocation: low vol 40%, quality 35%, value 15%, smart money 5%, momentum 5%
            return {
                "low_vol": w_low_vol,
                "quality": 0.35,
                "value": 0.15,
                "smart_money": 0.05,
                "momentum": max(0.05, 1.0 - (w_low_vol + 0.35 + 0.15 + 0.05)),
            }
        else:
            # Neutral / Sideways: Quality 35%, Value 25%, Low Vol 15%, Smart Money 15%, Momentum 10%
            w_qual = self.qual_weight_neutral
            return {
                "quality": w_qual,
                "value": 0.25,
                "low_vol": 0.15,
                "smart_money": 0.15,
                "momentum": max(0.05, 1.0 - (w_qual + 0.25 + 0.15 + 0.15)),
            }

    def _normalize_cross_section(
        self,
        values: list[float],
        higher_is_better: bool = True,
    ) -> list[float]:
        """
        Winsorize outliers at +/- k standard deviations, then map to percentile ranks [0.0, 1.0].
        """
        n = len(values)
        if n == 0:
            return []
        if n == 1:
            return [0.50]

        arr = np.array(values, dtype=float)
        mean_val = float(np.mean(arr))
        std_val = float(np.std(arr, ddof=1)) if n > 1 else 0.0

        if std_val > 1e-7:
            k = self.winsorize_std
            lower_bound = mean_val - k * std_val
            upper_bound = mean_val + k * std_val
            clipped = np.clip(arr, lower_bound, upper_bound)
        else:
            clipped = arr

        # Rank array to obtain percentile scores in [0.0, 1.0]
        # argsort gives rank order
        ranks = np.argsort(np.argsort(clipped))
        normalized = ranks / float(max(1, n - 1))

        if not higher_is_better:
            normalized = 1.0 - normalized

        return [round(float(x), 4) for x in normalized]

    def score_factor_pillars(
        self,
        metrics_list: list[RawFactorMetrics],
    ) -> list[StandardizedFactorScores]:
        """
        Compute cross-sectional standardized scores for all 5 factor pillars across candidates.
        """
        if not metrics_list:
            return []

        tickers = [m.ticker for m in metrics_list]

        # 1. Momentum Sub-metrics
        norm_mom_12_1 = self._normalize_cross_section([m.momentum_12_1 for m in metrics_list], higher_is_better=True)
        norm_rel_strength = self._normalize_cross_section([m.relative_strength_60d for m in metrics_list], higher_is_better=True)
        # RSI optimal zone around 55-65: distance from 60
        rsi_scores = [1.0 - min(1.0, abs(m.rsi_14 - 60.0) / 40.0) for m in metrics_list]
        norm_rsi = self._normalize_cross_section(rsi_scores, higher_is_better=True)

        # 2. Quality Sub-metrics
        norm_roe = self._normalize_cross_section([m.roe for m in metrics_list], higher_is_better=True)
        norm_margin = self._normalize_cross_section([m.gross_margin for m in metrics_list], higher_is_better=True)
        norm_debt = self._normalize_cross_section([m.debt_to_equity for m in metrics_list], higher_is_better=False)

        # 3. Value Sub-metrics
        # PEG ratio: positive values close to 1.0 are best; lower positive is better
        peg_vals = [max(0.1, m.peg_ratio) for m in metrics_list]
        norm_peg = self._normalize_cross_section(peg_vals, higher_is_better=False)
        norm_pe = self._normalize_cross_section([m.forward_pe for m in metrics_list], higher_is_better=False)

        # 4. Low Volatility Sub-metrics
        norm_vol = self._normalize_cross_section([m.annualized_vol_60d for m in metrics_list], higher_is_better=False)
        norm_downside = self._normalize_cross_section([m.downside_dev_60d for m in metrics_list], higher_is_better=False)

        # 5. Smart Money Sub-metrics
        norm_avwap = self._normalize_cross_section([m.avwap_distance_pct for m in metrics_list], higher_is_better=True)
        norm_poc = self._normalize_cross_section([m.poc_support_pct for m in metrics_list], higher_is_better=True)

        results = []
        for i, t in enumerate(tickers):
            # Weighted average per pillar
            f_mom = 0.40 * norm_mom_12_1[i] + 0.40 * norm_rel_strength[i] + 0.20 * norm_rsi[i]
            f_qual = 0.45 * norm_roe[i] + 0.35 * norm_margin[i] + 0.20 * norm_debt[i]
            f_val = 0.60 * norm_peg[i] + 0.40 * norm_pe[i]
            f_low_vol = 0.60 * norm_vol[i] + 0.40 * norm_downside[i]
            f_smart = 0.60 * norm_avwap[i] + 0.40 * norm_poc[i]

            results.append(StandardizedFactorScores(
                ticker=t,
                momentum_score=round(f_mom, 4),
                quality_score=round(f_qual, 4),
                value_score=round(f_val, 4),
                low_vol_score=round(f_low_vol, 4),
                smart_money_score=round(f_smart, 4),
            ))

        return results

    def compute_ensemble_alphas(
        self,
        metrics_list: list[RawFactorMetrics],
        current_regime: str = "NEUTRAL_SIDEWAYS",
    ) -> list[EnsembleAlphaResult]:
        """
        Synthesize 5-pillar factor scores into a final composite alpha score conditioned on regime.
        """
        if not metrics_list:
            return []

        weights = self.get_regime_weights(current_regime)
        scores_list = self.score_factor_pillars(metrics_list)

        results: list[EnsembleAlphaResult] = []
        for s in scores_list:
            contrib_mom = weights.get("momentum", 0.0) * s.momentum_score
            contrib_qual = weights.get("quality", 0.0) * s.quality_score
            contrib_val = weights.get("value", 0.0) * s.value_score
            contrib_vol = weights.get("low_vol", 0.0) * s.low_vol_score
            contrib_smart = weights.get("smart_money", 0.0) * s.smart_money_score

            contributions = {
                "momentum": contrib_mom,
                "quality": contrib_qual,
                "value": contrib_val,
                "low_vol": contrib_vol,
                "smart_money": contrib_smart,
            }

            raw_sum = sum(contributions.values())
            # Scale to range [0.10, 1.00]
            composite_score = round(max(0.10, min(1.00, raw_sum)), 4)

            top_factor = max(contributions.keys(), key=lambda k: contributions[k])
            reason = (
                f"體制 [{current_regime}] 因子融合：總分 {composite_score:.2f}，"
                f"主導因子 [{top_factor}] (貢獻 {contributions[top_factor]:.2f})"
            )

            results.append(EnsembleAlphaResult(
                ticker=s.ticker,
                composite_alpha_score=composite_score,
                regime=current_regime,
                factor_scores=s,
                factor_weights=weights,
                factor_contributions=contributions,
                reason=reason,
            ))

        # Rank candidates by composite alpha score descending
        results.sort(key=lambda r: r.composite_alpha_score, reverse=True)
        for rank_idx, r in enumerate(results, start=1):
            r.rank = rank_idx

        return results
