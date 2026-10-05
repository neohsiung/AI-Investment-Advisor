"""
Pydantic V2 Schemas for M8: Macro Surprise Index & Liquidity Beta Dampener.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MacroIndicatorSurpriseSchema(BaseModel):
    indicator: str = Field(..., description="Indicator identifier, e.g. CPI, NFP, GDP, FEDFUNDS, 10Y2Y_Spread")
    actual_value: float = Field(..., description="Reported or latest actual value")
    expected_value: float = Field(..., description="Consensus or baseline expected value")
    raw_surprise: float = Field(..., description="Actual minus expected difference")
    rolling_std: float = Field(..., description="Rolling standard deviation of surprises")
    standardized_surprise: float = Field(..., description="Z-score normalized surprise")
    weight: float = Field(..., description="Category weighting in aggregate index")
    impact_direction: str = Field(..., description="HAWKISH, DOVISH, or EXPANSIONARY / CONTRACTIONARY")


class MacroSurpriseAssessmentResponse(BaseModel):
    macro_surprise_index: float = Field(..., description="Composite Macro Surprise Index in [-3.0, +3.0]")
    regime_shock_level: str = Field(..., description="NORMAL, MODERATE_SURPRISE, HAWKISH_TIGHTENING_SHOCK, RECESSIONARY_SHOCK")
    liquidity_beta_multiplier: float = Field(..., description="Beta dampener multiplier in [0.40, 1.25]")
    recommended_cash_adjustment_pct: float = Field(..., description="Additional cash buffer adjustment in [-0.05, +0.20]")
    is_dampener_active: bool = Field(..., description="True if dampener is active (beta dampened or extra cash required)")
    indicators: Dict[str, MacroIndicatorSurpriseSchema] = Field(default_factory=dict, description="Detailed indicator breakdown")
    rationale: str = Field(..., description="Detailed explanation of macro surprise state and dampener reasoning")
    evaluated_at: str = Field(..., description="ISO 8601 evaluation timestamp")


class MacroSurpriseEvaluateRequest(BaseModel):
    custom_indicators: Optional[Dict[str, Dict[str, float]]] = Field(
        None,
        description="Optional overrides for indicators: {'CPI': {'actual': 3.6, 'expected': 3.1, 'std': 0.25}}",
    )
    user_id: Optional[str] = Field(None, description="Optional tenant or user identifier")
