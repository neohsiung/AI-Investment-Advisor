"""
Pydantic schemas for Council Diversity Entropy and Groupthink Shielder (A4).
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentVoteSchema(BaseModel):
    """Payload representing a single council agent's vote."""
    agent_name: str = Field(..., description="Name of the voting agent (e.g. Technical, Fundamental)")
    stance: str = Field(..., description="Voting stance: BUY, HOLD, or SELL")
    weight: float = Field(default=1.0, gt=0, description="Voting weight")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Agent confidence score")
    rationale: Optional[str] = Field(default=None, description="Reasoning provided by the agent")


class DevilsAdvocateChallengeSchema(BaseModel):
    """Challenge packet produced by the Devil's Advocate inoculation engine."""
    dominant_stance: str = Field(..., description="The herd consensus stance (BUY/SELL/HOLD)")
    challenge_headline: str = Field(..., description="Summary headline of the challenge")
    counter_arguments: List[str] = Field(..., description="Detailed counter-arguments to majority view")
    required_checkpoints: List[str] = Field(..., description="Mandatory questions for the CIO arbitrator")


class DiversityEvaluationRequest(BaseModel):
    """Request payload to evaluate council debate diversity."""
    symbol: Optional[str] = Field(default=None, description="Target asset ticker symbol")
    votes: List[AgentVoteSchema] = Field(..., description="List of votes from participating agents")


class DiversityEvaluationResponse(BaseModel):
    """Response containing Shannon Diversity Entropy metrics and groupthink assessment."""
    symbol: Optional[str] = Field(default=None, description="Target asset ticker symbol")
    shannon_entropy: float = Field(..., description="Calculated Shannon Diversity Entropy")
    normalized_entropy: float = Field(..., description="Normalized entropy in [0.0, 1.0]")
    distribution: Dict[str, float] = Field(..., description="Normalized vote probability distribution")
    dominant_stance: str = Field(..., description="Stance with the largest weighted share")
    dominant_ratio: float = Field(..., description="Proportion of the dominant stance [0.0, 1.0]")
    diversity_level: str = Field(..., description="DIVERSE, MODERATE_CONSENSUS, or GROUPTHINK_WARNING")
    groupthink_detected: bool = Field(..., description="True if herd consensus exceeds safety thresholds")
    recommended_haircut_pct: float = Field(..., description="Suggested position haircut ratio")
    devils_advocate_challenge: Optional[DevilsAdvocateChallengeSchema] = Field(
        default=None, description="Devil's Advocate review packet if groupthink detected"
    )
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic metrics")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")
