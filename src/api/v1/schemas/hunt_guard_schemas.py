"""
Pydantic Schemas for Intraday Liquidity Hole & Stop-Hunt Guard (E4 Engine).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.services.intraday_liquidity_hunt_guard_service import (
    GuardAction,
    GuardState,
    KeyLevelType,
)


class OrderBookSnapshotSchema(BaseModel):
    """Snapshot of top-of-book quotes and depth."""
    symbol: str = Field(..., description="Asset ticker symbol, e.g. AAPL")
    bid_price: float = Field(..., gt=0, description="Best bid price")
    ask_price: float = Field(..., gt=0, description="Best ask price")
    bid_size: float = Field(..., ge=0, description="Aggregate shares/contracts on bid")
    ask_size: float = Field(..., ge=0, description="Aggregate shares/contracts on ask")
    timestamp: Optional[datetime] = Field(None, description="Observation timestamp")


class TradeBarSchema(BaseModel):
    """Intraday OHLCV trade bar."""
    symbol: str = Field(..., description="Asset ticker symbol")
    open_price: float = Field(..., gt=0, description="Bar open price")
    high_price: float = Field(..., gt=0, description="Bar high price")
    low_price: float = Field(..., gt=0, description="Bar low price")
    close_price: float = Field(..., gt=0, description="Bar close price")
    volume: float = Field(..., ge=0, description="Traded volume within bar window")
    timestamp: Optional[datetime] = Field(None, description="Bar close timestamp")


class KeyLevelSchema(BaseModel):
    """Technical support or resistance level."""
    level_type: KeyLevelType = Field(..., description="SUPPORT or RESISTANCE")
    price: float = Field(..., gt=0, description="Price level threshold")
    description: Optional[str] = Field(None, description="Context, e.g. 'Daily High'")


class LiquidityHoleAssessmentSchema(BaseModel):
    """Assessment of order book depth vacuum."""
    is_hole_detected: bool
    depth_depletion_ratio: float = Field(..., description="Normalized depth reduction (0.0 to 1.0)")
    current_depth: float = Field(..., description="Current top-of-book depth")
    baseline_depth: float = Field(..., description="Rolling baseline depth")
    spread_bps: float = Field(..., description="Effective bid-ask spread in basis points")
    spread_expansion_ratio: float = Field(..., description="Current spread relative to baseline")
    details: str


class StopHuntAssessmentSchema(BaseModel):
    """Assessment of predatory stop-loss sweep."""
    is_hunt_detected: bool
    stop_hunt_score: float = Field(..., description="Composite hunt score (0.0 to 1.0)")
    swept_level: Optional[float] = None
    level_type: Optional[KeyLevelType] = None
    penetration_pct: float = Field(0.0, description="Penetration beyond level in %")
    reversion_ratio: float = Field(0.0, description="Mean-reversion retracement ratio")
    volume_spike_ratio: float = Field(1.0, description="Volume relative to baseline")
    details: str


class GuardEvaluationRequest(BaseModel):
    """Request payload to evaluate microstructure liquidity hole & stop hunt."""
    symbol: str = Field(..., description="Target ticker symbol, e.g. NVDA")
    snapshot: Optional[OrderBookSnapshotSchema] = Field(None, description="Latest quote snapshot")
    bar: Optional[TradeBarSchema] = Field(None, description="Latest completed OHLCV bar")
    key_levels: Optional[List[KeyLevelSchema]] = Field(None, description="Key price levels")


class GuardEvaluationResponse(BaseModel):
    """Full microstructure evaluation result."""
    symbol: str
    state: GuardState
    action: GuardAction
    liquidity_hole: LiquidityHoleAssessmentSchema
    stop_hunt: StopHuntAssessmentSchema
    recommended_delay_seconds: int
    adverse_slippage_buffer_bps: float
    evaluated_at: datetime


class SymbolGuardStatusSchema(BaseModel):
    """Summary status of a monitored symbol."""
    symbol: str
    current_state: str
    in_cooldown: bool
    remaining_cooldown_seconds: int
    last_state_change: str
    last_trigger_details: str
    snapshot_count: int
    trade_bar_count: int


class GuardStatusListResponse(BaseModel):
    """List of all symbol statuses."""
    total_symbols: int
    symbols: Dict[str, SymbolGuardStatusSchema]


class GuardResetRequest(BaseModel):
    """Request to manually reset symbol guard state."""
    symbol: str = Field(..., description="Symbol to reset to NORMAL")
