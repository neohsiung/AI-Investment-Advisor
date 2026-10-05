"""
M8: Macro Surprise Index & Liquidity Beta Dampener Service
=============================================================================
Calculates standardized macroeconomic surprises relative to market expectations
(e.g., FRED indicators: CPI, Non-Farm Payrolls, GDP, Fed Funds, 10Y2Y Spread).
When macro data surprises to the extreme (hawkish tightening shock or stagflationary/
recessionary contraction), dynamically dampens portfolio target Beta exposure
and expands defensive cash buffers:
1. Standardized Indicator Surprises (Z-Score):
   z_k = (Actual_k - Expected_k) / sigma_k
2. Composite Macro Surprise Index (MSI):
   MSI = sum_k (w_k * z_k)
3. Four-tier Macro Shock State Machine:
   - NORMAL: |MSI| < 0.75, standard operations, multiplier 1.0x
   - MODERATE_SURPRISE: 0.75 <= |MSI| < 1.50, mild beta dampening (0.85x ~ 1.10x)
   - HAWKISH_TIGHTENING_SHOCK: MSI >= 1.50 (Hot CPI / High Rates), aggressive beta dampening (0.50x ~ 0.70x), cash +10% ~ +20%
   - RECESSIONARY_SHOCK: MSI <= -1.50 (Cold Growth / Inversion / Collapsing Payrolls), defensive beta dampening (0.40x ~ 0.65x), cash +15% ~ +25%
4. Liquidity Beta Dampener Multiplier (M_beta):
   TargetBeta_adjusted = TargetBeta_base * M_beta
5. Closed-loop Feedbacks:
   - Injects cash buffer adjustment into PortfolioAdaptiveIntelligenceService (D1)
   - Modulates target_beta in TickerUniverseService (M2) and MarketRegimeService (M1)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class MacroShockLevel(str, Enum):
    NORMAL = "NORMAL"
    MODERATE_SURPRISE = "MODERATE_SURPRISE"
    HAWKISH_TIGHTENING_SHOCK = "HAWKISH_TIGHTENING_SHOCK"
    RECESSIONARY_SHOCK = "RECESSIONARY_SHOCK"


@dataclass
class IndicatorSurpriseDetail:
    indicator: str
    actual_value: float
    expected_value: float
    raw_surprise: float
    rolling_std: float
    standardized_surprise: float
    weight: float
    impact_direction: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator": self.indicator,
            "actual_value": round(self.actual_value, 4),
            "expected_value": round(self.expected_value, 4),
            "raw_surprise": round(self.raw_surprise, 4),
            "rolling_std": round(self.rolling_std, 4),
            "standardized_surprise": round(self.standardized_surprise, 4),
            "weight": round(self.weight, 4),
            "impact_direction": self.impact_direction,
        }


@dataclass
class MacroSurpriseAssessment:
    macro_surprise_index: float
    regime_shock_level: MacroShockLevel
    liquidity_beta_multiplier: float
    recommended_cash_adjustment_pct: float
    is_dampener_active: bool
    indicators: Dict[str, IndicatorSurpriseDetail] = field(default_factory=dict)
    rationale: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "macro_surprise_index": round(self.macro_surprise_index, 4),
            "regime_shock_level": self.regime_shock_level.value,
            "liquidity_beta_multiplier": round(self.liquidity_beta_multiplier, 3),
            "recommended_cash_adjustment_pct": round(self.recommended_cash_adjustment_pct, 4),
            "is_dampener_active": self.is_dampener_active,
            "indicators": {k: v.to_dict() for k, v in self.indicators.items()},
            "rationale": self.rationale,
            "evaluated_at": self.evaluated_at,
        }


# Default statistical benchmarks and weights across key macro indicators
# Weights sum to 1.0
DEFAULT_INDICATOR_SPECS: Dict[str, Dict[str, Any]] = {
    "CPI": {
        "weight": 0.30,
        "default_expected": 3.0,
        "default_std": 0.35,
        "hawkish_positive": True,  # Positive surprise = higher inflation = hawkish
    },
    "FEDFUNDS": {
        "weight": 0.25,
        "default_expected": 4.5,
        "default_std": 0.50,
        "hawkish_positive": True,  # Higher rates = liquidity tightening
    },
    "NFP": {
        "weight": 0.20,
        "default_expected": 175.0,  # thousands
        "default_std": 45.0,
        "hawkish_positive": True,  # Overheating labor market = rate pressure
    },
    "GDP": {
        "weight": 0.15,
        "default_expected": 2.2,
        "default_std": 0.80,
        "hawkish_positive": True,  # Strong growth = neutral/bullish, but negative = recession
    },
    "10Y2Y_Spread": {
        "weight": 0.10,
        "default_expected": 0.20,
        "default_std": 0.30,
        "hawkish_positive": False,  # Deep inversion (negative) = recession warning
    },
}


class MacroSurpriseService:
    """
    Evaluates standardized macroeconomic surprises and calculates
    liquidity beta dampener multipliers and defensive cash adjustments.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        fred_service: Optional[Any] = None,
        settings_service: Optional[Any] = None,
        default_shock_threshold: float = 1.50,
        default_min_beta_multiplier: float = 0.50,
        default_max_cash_adjustment: float = 0.15,
    ) -> None:
        self.user_id = resolve_user_id(user_id)
        self.fred_service = fred_service
        self.settings_service = settings_service
        self._shock_threshold = default_shock_threshold
        self._min_beta_multiplier = default_min_beta_multiplier
        self._max_cash_adjustment = default_max_cash_adjustment

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service and hasattr(self.settings_service, "get"):
            try:
                val = self.settings_service.get(key)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to fetch setting '{key}': {e}. Using default {default}")
        return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("macro_surprise_enabled", True))

    @property
    def shock_threshold(self) -> float:
        return float(self._get_setting("macro_surprise_shock_threshold", self._shock_threshold))

    @property
    def min_beta_multiplier(self) -> float:
        return float(self._get_setting("macro_surprise_min_beta_multiplier", self._min_beta_multiplier))

    @property
    def max_cash_adjustment(self) -> float:
        return float(self._get_setting("macro_surprise_max_cash_adjustment", self._max_cash_adjustment))

    def evaluate_surprises(
        self,
        custom_indicators: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> MacroSurpriseAssessment:
        """
        Computes composite Macro Surprise Index (MSI) and derives
        beta dampener multiplier and defensive cash buffer adjustments.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        if not self.is_enabled:
            return MacroSurpriseAssessment(
                macro_surprise_index=0.0,
                regime_shock_level=MacroShockLevel.NORMAL,
                liquidity_beta_multiplier=1.0,
                recommended_cash_adjustment_pct=0.0,
                is_dampener_active=False,
                indicators={},
                rationale="Macro surprise dampener is disabled by configuration.",
                evaluated_at=now_iso,
            )

        # 1. Fetch raw macro indicators from FRED service if available
        fred_data: Dict[str, Any] = {}
        if self.fred_service and hasattr(self.fred_service, "get_macro_indicators"):
            try:
                fred_data = self.fred_service.get_macro_indicators() or {}
            except Exception as e:
                logger.warning(f"Error querying FRED macro indicators: {e}")

        # 2. Extract and standardize indicators
        details: Dict[str, IndicatorSurpriseDetail] = {}
        weighted_surprise_sum = 0.0
        total_weight = 0.0

        for ind_name, spec in DEFAULT_INDICATOR_SPECS.items():
            weight = spec["weight"]
            expected = spec["default_expected"]
            std = spec["default_std"]

            # Check custom override
            if custom_indicators and ind_name in custom_indicators:
                c_data = custom_indicators[ind_name]
                actual = float(c_data.get("actual", expected))
                expected = float(c_data.get("expected", expected))
                std = float(c_data.get("std", std))
            elif ind_name in fred_data:
                # Resolve from FRED payload
                raw_val = fred_data[ind_name].get("value")
                actual = float(raw_val) if raw_val is not None else expected
            else:
                actual = expected

            # Avoid division by zero
            safe_std = max(1e-4, std)
            raw_surprise = actual - expected
            z_score = raw_surprise / safe_std

            # Determine impact direction
            if ind_name in ["CPI", "FEDFUNDS"]:
                direction = "HAWKISH" if z_score > 0.5 else ("DOVISH" if z_score < -0.5 else "NEUTRAL")
            elif ind_name in ["NFP", "GDP"]:
                direction = "EXPANSIONARY" if z_score > 0.5 else ("CONTRACTIONARY" if z_score < -0.5 else "NEUTRAL")
            elif ind_name == "10Y2Y_Spread":
                direction = "INVERSION_WARNING" if actual < 0.0 else "NORMAL_CURVE"
            else:
                direction = "NEUTRAL"

            # Invert sign for indicators where negative surprise indicates contractionary risk
            effective_z = z_score
            if not spec.get("hawkish_positive", True):
                # E.g. 10Y2Y spread inversion is negative, so lower spread adds to risk
                effective_z = -z_score

            detail = IndicatorSurpriseDetail(
                indicator=ind_name,
                actual_value=actual,
                expected_value=expected,
                raw_surprise=raw_surprise,
                rolling_std=safe_std,
                standardized_surprise=z_score,
                weight=weight,
                impact_direction=direction,
            )
            details[ind_name] = detail

            weighted_surprise_sum += weight * effective_z
            total_weight += weight

        # Composite MSI
        msi = weighted_surprise_sum / total_weight if total_weight > 0 else 0.0
        # Bound MSI in [-3.5, +3.5]
        msi = max(-3.5, min(3.5, msi))

        # 3. Classify State Machine & Derive Dampener
        shock_th = self.shock_threshold
        moderate_th = shock_th * 0.50

        if msi >= shock_th:
            # Hawkish Tightening Shock (Hot inflation, surging policy rates)
            shock_level = MacroShockLevel.HAWKISH_TIGHTENING_SHOCK
            excess = min(2.0, msi - shock_th)
            # Dampen beta sharply towards min_beta_multiplier
            beta_mult = max(self.min_beta_multiplier, 0.70 - (0.20 * (excess / 2.0)))
            # Expand cash buffer
            cash_adj = min(self.max_cash_adjustment, 0.10 + (0.05 * (excess / 2.0)))
            dampener_active = True
            rationale = (
                f"Severe Hawkish Tightening Shock detected (MSI={msi:.2f} >= {shock_th:.2f}). "
                f"Aggressive inflation/rates surprise forces liquidity beta reduction ({beta_mult:.2f}x) "
                f"and defensive cash expansion (+{cash_adj*100:.1f}%)."
            )
        elif msi <= -shock_th:
            # Recessionary Shock (Collapsing growth, severe inversion, job losses)
            shock_level = MacroShockLevel.RECESSIONARY_SHOCK
            excess = min(2.0, abs(msi) - shock_th)
            beta_mult = max(self.min_beta_multiplier, 0.60 - (0.20 * (excess / 2.0)))
            cash_adj = min(self.max_cash_adjustment, 0.12 + (0.05 * (excess / 2.0)))
            dampener_active = True
            rationale = (
                f"Severe Recessionary Contraction Shock detected (MSI={msi:.2f} <= -{shock_th:.2f}). "
                f"Growth collapse and curve inversion triggers capital preservation dampener ({beta_mult:.2f}x) "
                f"and defensive cash expansion (+{cash_adj*100:.1f}%)."
            )
        elif abs(msi) >= moderate_th:
            # Moderate surprise
            shock_level = MacroShockLevel.MODERATE_SURPRISE
            ratio = (abs(msi) - moderate_th) / (shock_th - moderate_th)
            if msi > 0:
                beta_mult = 1.0 - (0.15 * ratio)
                cash_adj = 0.05 * ratio
                rationale = f"Moderate hawkish surprise (MSI={msi:.2f}). Mild beta dampening ({beta_mult:.2f}x)."
            else:
                beta_mult = 1.0 - (0.20 * ratio)
                cash_adj = 0.06 * ratio
                rationale = f"Moderate macroeconomic softening (MSI={msi:.2f}). Precautionary beta dampening ({beta_mult:.2f}x)."
            dampener_active = True
        else:
            # Normal macro environment
            shock_level = MacroShockLevel.NORMAL
            beta_mult = 1.0
            cash_adj = 0.0
            dampener_active = False
            rationale = f"Macro indicators within baseline expectations (MSI={msi:.2f}). Standard risk parameters."

        return MacroSurpriseAssessment(
            macro_surprise_index=msi,
            regime_shock_level=shock_level,
            liquidity_beta_multiplier=beta_mult,
            recommended_cash_adjustment_pct=cash_adj,
            is_dampener_active=dampener_active,
            indicators=details,
            rationale=rationale,
            evaluated_at=now_iso,
        )

    def apply_beta_dampener(
        self,
        base_beta: float,
        assessment: Optional[MacroSurpriseAssessment] = None,
    ) -> float:
        """
        Adjusts target or asset portfolio Beta according to the Macro Surprise Index.
        """
        if assessment is None:
            assessment = self.evaluate_surprises()

        adjusted = base_beta * assessment.liquidity_beta_multiplier
        return max(0.20, min(1.80, round(adjusted, 3)))
