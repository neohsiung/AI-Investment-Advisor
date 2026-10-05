"""
Pydantic V2 Schemas for A7: Cross-Market Contagion & Inter-Asset Transmission Engine.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AssetSpilloverImpactSchema(BaseModel):
    channel: str = Field(..., description="Transmission channel, e.g. RATES_YIELD_CURVE, FX_LIQUIDITY")
    source_indicator: str = Field(..., description="External market trigger indicator and jump magnitude")
    indicator_delta_pct: float = Field(..., description="Indicator percentage change")
    sensitivity_factor: float = Field(..., description="Sector/ticker sensitivity factor (-1.0 to 1.0)")
    estimated_price_impact_pct: float = Field(..., description="Estimated directional price impact in percent")
    transmission_mechanism: str = Field(..., description="Macroeconomic and financial transmission rationale")
    risk_level: str = Field(..., description="Risk severity: LOW, MEDIUM, HIGH, or CRITICAL")


class ContagionAssessmentRequest(BaseModel):
    symbol: str = Field(..., description="Ticker symbol under deliberation, e.g. NVDA, AAPL")
    sector: Optional[str] = Field("Technology", description="Sector classification, e.g. Technology, Energy, Financials")
    macro_signals: Optional[Dict[str, float]] = Field(
        None,
        description="Observed market macro jumps (e.g. {'US10Y': 5.0, 'DXY': 1.8, 'BRENT': 4.2, 'VIX': 12.0})",
    )
    custom_shocks: Optional[Dict[str, float]] = Field(
        None,
        description="Hypothetical or stress shock overrides to test resilience",
    )


class ContagionAssessmentResponse(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    sector: str = Field(..., description="Sector evaluated")
    overall_contagion_risk_score: float = Field(..., description="Aggregated contagion risk score in [0.0, 1.0]")
    contagion_regime: str = Field(..., description="Regime: BENIGN, DIVERGENT, ACUTE_SPILLOVER, or SYSTEMIC_CONTAGION")
    channel_impacts: List[AssetSpilloverImpactSchema] = Field(default_factory=list, description="Detailed impacts across the 4 transmission channels")
    recommended_hedging_overlays: List[str] = Field(default_factory=list, description="Actionable institutional hedging overlays")
    markdown_contagion_card: str = Field(..., description="Formatted markdown card suitable for council and CIO dashboard injection")
    is_contagion_alert: bool = Field(..., description="Whether contagion risk exceeds dynamic threshold")
    assessed_at: str = Field(..., description="ISO 8601 evaluation timestamp")
