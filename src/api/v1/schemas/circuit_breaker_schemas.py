"""
Pydantic Schemas for Intraday Liquidity Shock & Volatility Circuit Breaker API (P7 Engine).
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CircuitBreakerStatusSchema(BaseModel):
    symbol: str = Field(..., description="標的代碼 (或 GLOBAL)")
    state: str = Field(..., description="熔斷狀態 (NORMAL, WARNING, TRIGGERED, COOLDOWN)")
    trigger_type: Optional[str] = Field(None, description="衝擊觸發類型 (SPREAD_EXPANSION, PRICE_GAP_SHOCK, VOLATILITY_SURGE, MANUAL)")
    reason: Optional[str] = Field(None, description="觸發原因或冷卻狀態說明")
    spread_bps: float = Field(0.0, description="即時點差 (bps)")
    spread_multiplier: float = Field(1.0, description="點差相對於基線之倍數")
    price_shock_pct: float = Field(0.0, description="瞬時價格偏離或跳空幅度 (%)")
    vol_sigma: float = Field(0.0, description="日內波動率異常 Sigma 倍數")
    triggered_at: Optional[str] = Field(None, description="熔斷觸發時間 (ISO-8601)")
    cooldown_until: Optional[str] = Field(None, description="冷卻結束時間 (ISO-8601)")
    actions_taken: List[str] = Field(default_factory=list, description="已採取防護處置動作")


class CircuitBreakerStatusListResponse(BaseModel):
    status: str = "success"
    total: int = Field(..., description="總監控標的數")
    circuit_breakers: Dict[str, CircuitBreakerStatusSchema] = Field(default_factory=dict, description="熔斷狀態表")


class CircuitBreakerTriggerRequest(BaseModel):
    symbol: str = Field("GLOBAL", description="熔斷標的代號 (例如 TSLA 或 GLOBAL)")
    reason: str = Field("Manual operator emergency trigger", description="手動熔斷原因說明")
    cooldown_minutes: int = Field(15, ge=1, le=240, description="冷卻觀察時間 (分鐘)")


class CircuitBreakerResumeRequest(BaseModel):
    symbol: str = Field("GLOBAL", description="手動恢復標的代號 (例如 TSLA 或 GLOBAL)")


class CircuitBreakerActionResponse(BaseModel):
    status: str = "success"
    symbol: str = Field(..., description="標的代號")
    state: str = Field(..., description="處置後之熔斷狀態")
    message: str = Field(..., description="處置結果說明")


class CircuitBreakerQuoteEvaluationRequest(BaseModel):
    symbol: str = Field(..., description="標的代碼")
    bid_price: float = Field(..., gt=0, description="買一價 (Bid)")
    ask_price: float = Field(..., gt=0, description="賣一價 (Ask)")
    last_price: float = Field(..., gt=0, description="最新成交價")
    bid_size: Optional[float] = Field(None, description="買一量")
    ask_size: Optional[float] = Field(None, description="賣一量")
    intraday_volatility: Optional[float] = Field(None, description="盤中實時年化波動率")


class CircuitBreakerQuoteEvaluationResponse(BaseModel):
    status: str = "success"
    circuit_breaker: CircuitBreakerStatusSchema = Field(..., description="評估後之最新熔斷狀態")
