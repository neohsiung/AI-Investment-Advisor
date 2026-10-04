"""
Pydantic schemas for Order Book Toxicity and VPIN Detector (E3).
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class RecordQuoteRequest(BaseModel):
    """Payload to record Level-1/Level-2 top of book snapshot."""
    symbol: str = Field(..., description="Ticker symbol")
    bid_price: float = Field(..., gt=0, description="Best bid price")
    ask_price: float = Field(..., gt=0, description="Best ask price")
    bid_size: float = Field(..., ge=0, description="Depth quantity at best bid")
    ask_size: float = Field(..., ge=0, description="Depth quantity at best ask")


class RecordTradeRequest(BaseModel):
    """Payload to record an executed trade tick."""
    symbol: str = Field(..., description="Ticker symbol")
    price: float = Field(..., gt=0, description="Fill price")
    volume: float = Field(..., gt=0, description="Fill size in shares")
    direction: Optional[str] = Field(None, description="Trade direction (BUY/SELL/UNKNOWN)")


class ToxicityAssessmentResponse(BaseModel):
    """Microstructure toxicity assessment payload."""
    symbol: str = Field(..., description="Ticker symbol")
    vpin: float = Field(..., description="Volume-Synchronized Probability of Toxicity [0.0, 1.0]")
    order_book_imbalance: float = Field(..., description="Normalized Order Book Imbalance (OBI) [-1.0, 1.0]")
    toxicity_level: str = Field(..., description="NORMAL, ELEVATED_TOXICITY, or CRITICAL_TOXICITY")
    is_toxic: bool = Field(..., description="True if toxicity exceeds elevated or critical thresholds")
    recommended_action: str = Field(..., description="PROCEED, THROTTLE_SLICES, or HALT_AGGRESSIVE_FLOW")
    recommended_slippage_boost: float = Field(..., description="Extra multiplier boost for slippage compensator")
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic book and bucket metrics")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")
