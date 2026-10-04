"""
Pydantic Schemas for Adaptive Execution Slippage & Feedback API (P6 Engine).
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ExecutionFillRequest(BaseModel):
    """Payload for submitting an order execution fill report."""
    order_id: str = Field(..., description="訂單或子委託 ID")
    symbol: str = Field(..., description="標的代碼 (e.g. AAPL)")
    action: str = Field("BUY", description="訂單方向 (BUY / SELL)")
    venue: str = Field("COMPOSITE", description="執行市場或經紀商 (IBKR, ETORO, PAPER, COMPOSITE)")
    fill_price: float = Field(..., description="實際成交價格")
    fill_quantity: float = Field(..., description="實際成交股數")
    arrival_price: float = Field(..., description="決策或抵達市場基準價格")
    market_price_at_fill: Optional[float] = Field(None, description="成交當下市場公允價格 (選填)")
    fee_usd: float = Field(0.0, description="佣金與手續費 (USD)")
    adv_20: Optional[float] = Field(None, description="該標的 20 日日均成交量 (ADV20)")
    parent_plan_id: Optional[str] = Field(None, description="母委託或拆單排程 ID (選填)")


class ExecutionFillResponse(BaseModel):
    """Response returned after recording execution fill and recalibrating."""
    status: str = "success"
    fill_id: str = Field(..., description="成交記錄 UUID")
    symbol: str = Field(..., description="標的代碼")
    realized_slippage_bps: float = Field(..., description="實際實現滑價 (bps)")
    is_anomaly: bool = Field(False, description="是否被標記為逆向選擇或毒性訂單流異常")
    anomaly_reason: Optional[str] = Field(None, description="異常標記原因")
    calibrated_multiplier: float = Field(..., description="校準後 EWMA 滑價補償乘數 (M_slip)")
    effective_slippage_bps: float = Field(..., description="該標的有效校準滑價 (bps)")


class SlippageMetricItemSchema(BaseModel):
    """Calibrated slippage state metrics for an individual asset."""
    symbol: str = Field(..., description="標的代碼")
    realized_slippage_bps_mean: float = Field(..., description="歷史平均實現滑價 (bps)")
    expected_slippage_bps_mean: float = Field(..., description="模型平均預期滑價 (bps)")
    slippage_multiplier: float = Field(..., description="EWMA 滑價偏離補償乘數 M_slip")
    adverse_selection_count: int = Field(0, description="逆向選擇異常次數")
    adverse_penalty_bps: float = Field(0.0, description="逆向選擇防護懲罰 (bps)")
    calibrated_effective_slippage_bps: float = Field(..., description="有效校準滑價 (bps)")
    calibrated_effective_slippage_pct: float = Field(..., description="有效校準滑價比例 (decimal)")
    sample_count: int = Field(0, description="成交樣本筆數")
    last_updated: str = Field(..., description="最後更新時間 (ISO 8601)")


class SlippageMetricsListResponse(BaseModel):
    """Response containing asset-level slippage metrics dictionary."""
    status: str = "success"
    metrics: Dict[str, SlippageMetricItemSchema] = Field(..., description="各標的之即時滑價補償指標字典")


class SORAdaptationResponse(BaseModel):
    """Response containing SOR dynamic parameter tuning recommendations."""
    status: str = "success"
    symbol: str = Field(..., description="標的代碼")
    recommended_slices: int = Field(..., description="建議拆單切片數")
    recommended_window_minutes: int = Field(..., description="建議執行時間視窗（分鐘）")
    recommended_max_slippage_bps: float = Field(..., description="動態自適應斷路器滑價門檻 (bps)")
    recommended_jitter_pct: float = Field(..., description="建議時間與數量隨機微擾比例")
    slippage_multiplier: float = Field(..., description="當前滑價偏離乘數")
    effective_slippage_bps: float = Field(..., description="當前有效滑價預期 (bps)")
    strategy_hint: str = Field(..., description="演算法調度策略提示 (AGGRESSIVE_SLICING / STANDARD_TWAP / STREAMLINED_EXECUTION)")
    reason: str = Field(..., description="調度參數決策原因")


class RoundtripFrictionResponse(BaseModel):
    """Response containing empirical two-way friction for opportunity cost evaluation."""
    status: str = "success"
    sell_ticker: str = Field(..., description="賣出標的")
    buy_ticker: str = Field(..., description="買入標的")
    sell_slippage_pct: float = Field(..., description="賣出標的有效滑價比例")
    buy_slippage_pct: float = Field(..., description="買入標的有效滑價比例")
    sell_fee_pct: float = Field(..., description="賣出手續費率")
    buy_fee_pct: float = Field(..., description="買入手續費率")
    total_roundtrip_friction: float = Field(..., description="雙向完整交易磨擦成本比例")
    friction_multiplier: float = Field(..., description="非線性摩擦倍數")
    hurdle_rate: float = Field(..., description="基礎超額要求門檻")
    calibrated_hurdle: float = Field(..., description="校準後最低機會成本置換門檻")
