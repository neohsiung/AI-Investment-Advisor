from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class DashboardMetrics(BaseModel):
    """Core financial metrics for the dashboard summary."""
    total_valuation: float = Field(..., description="Net Liquidation Value (NLV)")
    uninvested_cash: float = Field(..., description="Available cash balance")
    gross_exposure: float = Field(..., description="Total value of holdings")
    leverage_ratio: float = Field(..., description="Gross exposure divided by NLV")
    active_agents: int = Field(..., description="Number of currently running agents")
    risk_exposure: str = Field(..., description="Current risk level (e.g., MODERATE, CONSERVATIVE)")
    total_pnl: float = Field(..., description="Total profit and loss")
    unrealized_pnl: float = Field(..., description="Current unrealized profit and loss")
    roi_percentage: float = Field(..., description="Return on Investment percentage")
    performance_change: str = Field(..., description="Simulated performance change string (e.g., +1.2%)")

class DashboardSummaryResponse(BaseModel):
    """Standardized response for the dashboard overview."""
    status: str = "success"
    data: DashboardMetrics

class PositionItem(BaseModel):
    """Individual portfolio position detail."""
    ticker: str
    name: Optional[str] = None
    quantity: float
    avg_price: float
    market_price: float
    market_value: float
    pnl: float
    pnl_percent: float
    weight: float

class PositionListResponse(BaseModel):
    """Standardized response for the positions list."""
    status: str = "success"
    data: List[PositionItem]

class SentimentMetric(BaseModel):
    """Individual sentiment score from intelligence scanning."""
    label: str
    value: float = 0
    score: Optional[float] = None
    trend: Optional[str] = None # 'up', 'down', 'stable'
    color: str = "bg-secondary"

class IntelligenceBriefing(BaseModel):
    """AI-generated market intelligence briefing."""
    executive_summary: str
    recommendation: str
    ai_note: str
    observation_window: str
    sentiment_metrics: List[SentimentMetric] = []

class IntelligenceResponse(BaseModel):
    """Standardized response for information briefings."""
    status: str = "success"
    data: IntelligenceBriefing

class AgentStatus(BaseModel):
    """Detailed status and performance for a swarm agent."""
    id: str
    name: str
    strategy: str
    performance: str
    accuracy: float
    status: str = "Active"
    color: str = "bg-secondary"
    recommendation_count: int = 0

class AgentListResponse(BaseModel):
    """Standardized response for all agents in the swarm."""
    status: str = "success"
    data: List[AgentStatus]
