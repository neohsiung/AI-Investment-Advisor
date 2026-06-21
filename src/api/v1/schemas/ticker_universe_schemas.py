"""Pydantic schemas for Ticker Universe API."""
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, validator
from typing import Optional, List, Dict, Any


# ── Ticker Universe ──

class TickerUniverseRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    id: str
    user_id: str
    ticker: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    status: str = "active"
    added_at: str
    updated_at: Optional[str] = None
    removal_reason: Optional[str] = None
    last_reviewed_at: Optional[str] = None


class TickerUniverseListResponse(BaseModel):
    status: str = "success"
    data: List[TickerUniverseRecord]


class TickerUniverseAddRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker (e.g., NVDA)")
    company_name: str = ""
    sector: str = ""
    industry: str = ""

    @validator("ticker")
    def uppercase(cls, v):
        return v.upper()


class TickerUniverseUpdateRequest(BaseModel):
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    status: Optional[str] = None


class TickerUniverseRemoveRequest(BaseModel):
    reason: str = ""


# ── Research ──

class ResearchRecord(BaseModel):
    id: str
    ticker: str
    agent_name: str
    research_type: str
    confidence_score: Optional[float] = None
    target_weight: Optional[float] = None
    expected_return: Optional[float] = None
    risk_score: Optional[float] = None
    thesis: Optional[str] = None
    risks: Optional[List[str]] = None
    created_at: Optional[str] = None


class ResearchListResponse(BaseModel):
    status: str = "success"
    data: List[ResearchRecord]


class ResearchSubmitRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker")
    agent_name: str = Field(..., description="Agent that produced the research")
    research_type: str = Field(..., description="periodic_review | new_discovery | risk_alert")
    confidence_score: float = Field(..., ge=0, le=1)
    target_weight: Optional[float] = None
    expected_return: Optional[float] = None
    risk_score: Optional[float] = None
    thesis: str = ""
    risks: Optional[List[str]] = None

    @validator("ticker")
    def uppercase(cls, v):
        return v.upper()


# ── Target Allocations ──

class TargetAllocationRecord(BaseModel):
    ticker: str
    target_weight: float
    confidence_score: float
    expected_return: Optional[float] = None
    risk_adjusted_return: Optional[float] = None
    min_weight: float = 0.05
    max_weight: float = 0.25
    last_optimized_at: Optional[str] = None


class TargetAllocationListResponse(BaseModel):
    status: str = "success"
    data: List[TargetAllocationRecord]


# ── Audit Logs ──

class LogRecord(BaseModel):
    id: str
    ticker: Optional[str] = None
    action: str
    agent_name: Optional[str] = None
    reasoning: Optional[str] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    created_at: Optional[str] = None


class LogListResponse(BaseModel):
    status: str = "success"
    data: List[LogRecord]


# ── Generic ──

class ActionResponse(BaseModel):
    status: str = "success"
    message: str


class TickerInfoResponse(BaseModel):
    status: str = "success"
    data: Any