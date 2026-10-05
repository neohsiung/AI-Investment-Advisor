"""
Pydantic V2 Schemas for A6: Counterfactual Reasoning & Stress Scenario Generation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CounterfactualScenarioSchema(BaseModel):
    scenario_id: str = Field(..., description="Unique scenario ID, e.g. CF_INFLATION_SURGE")
    title: str = Field(..., description="Short descriptive title of the stress scenario")
    category: str = Field(..., description="MACRO, GEOPOLITICAL, LIQUIDITY, or IDIOSYNCRATIC")
    shock_hypothesis: str = Field(..., description="The counterfactual 'What-if' premise")
    assumed_market_impact: str = Field(..., description="Estimated directional market impact")
    targeted_vulnerabilities: List[str] = Field(default_factory=list, description="Specific risk vulnerabilities probed")
    challenge_questions_for_experts: List[str] = Field(default_factory=list, description="Mandatory probing questions for council agents")
    severity_level: str = Field(..., description="MODERATE, HIGH, or EXTREME_TAIL")


class CounterfactualInoculationRequest(BaseModel):
    symbol: str = Field(..., description="Ticker symbol under deliberation, e.g. NVDA, AAPL")
    consensus_stance: str = Field("BUY", description="Dominant council consensus stance (BUY / HOLD / SELL)")
    conviction: float = Field(0.85, description="Council consensus conviction score in [0.0, 1.0]")
    key_drivers: Optional[List[str]] = Field(None, description="Primary bullish or bearish arguments cited by council")
    sector: Optional[str] = Field(None, description="Asset sector, e.g. Technology, Consumer Discretionary")
    max_scenarios: Optional[int] = Field(3, description="Maximum number of counterfactual scenarios to generate")


class CounterfactualInoculationResponse(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    consensus_stance: str = Field(..., description="Consensus stance evaluated")
    scenarios: List[CounterfactualScenarioSchema] = Field(default_factory=list, description="Generated counterfactual stress scenarios")
    cio_inoculation_prompt: str = Field(..., description="Formatted markdown text ready for rigid injection into CIO deliberative prompt")
    required_defense_checkpoints: List[str] = Field(default_factory=list, description="Mandatory checkpoints CIO must satisfy before final approval")
    is_stress_tested: bool = Field(..., description="Whether counterfactual scenarios were generated and injected")
    evaluated_at: str = Field(..., description="ISO 8601 evaluation timestamp")
