"""
Pydantic Schemas for Dynamic Debate Termination & Marginal Information Gain (A5 Engine).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from src.services.dynamic_debate_termination_service import TerminationStatus


class AgentDebateTurnSchema(BaseModel):
    """Single agent's argument and vote in a debate round."""
    agent_name: str = Field(..., description="Name of the expert agent, e.g. Technical")
    stance: str = Field(..., description="BUY, HOLD, or SELL")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Conviction score")
    arguments: str = Field(..., description="Detailed argument rationale")
    key_points: Optional[List[str]] = Field(default_factory=list, description="Core bullet points")


class DebateRoundSnapshotSchema(BaseModel):
    """Snapshot of a completed debate round."""
    round_number: int = Field(..., ge=1, description="Round number index (1-based)")
    turns: List[AgentDebateTurnSchema] = Field(..., description="List of turns in this round")
    timestamp: Optional[datetime] = Field(None, description="Round timestamp")


class DebateTerminationEvaluationRequest(BaseModel):
    """Request payload to evaluate if an ongoing debate should terminate early."""
    symbol: Optional[str] = Field(None, description="Target asset ticker symbol, e.g. AAPL")
    history_rounds: List[DebateRoundSnapshotSchema] = Field(..., min_length=1, description="Debate round history")


class DebateTerminationEvaluationResponse(BaseModel):
    """Evaluation result for debate termination and efficiency savings."""
    round_number: int
    decision: TerminationStatus
    marginal_info_gain: float = Field(..., description="Marginal information gain Delta I in [0.0, 1.0]")
    semantic_similarity: float = Field(..., description="Argument semantic similarity in [0.0, 1.0]")
    stance_drift: float = Field(..., description="Stance and confidence drift in [0.0, 1.0]")
    estimated_tokens_saved: int = Field(..., description="Estimated tokens saved by early termination")
    estimated_latency_saved_seconds: float = Field(..., description="Estimated latency saved in seconds")
    rationale: str
    evaluated_at: datetime
