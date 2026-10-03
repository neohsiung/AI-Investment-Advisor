"""
Pydantic Schemas for Portfolio Adaptive Intelligence API (D1 Engine).
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class HealthRadarSchema(BaseModel):
    regime_alignment: float = Field(..., description="體制適應度評分 [0, 100]")
    diversification_efficiency: float = Field(..., description="分散化效率評分 [0, 100]")
    factor_balance: float = Field(..., description="因子風格平衡評分 [0, 100]")
    tail_risk_resilience: float = Field(..., description="尾部風險抗跌評分 [0, 100]")
    capital_safety: float = Field(..., description="資本安全與槓桿評分 [0, 100]")


class AdaptiveHealthSummaryResponse(BaseModel):
    status: str = "success"
    health_score: float = Field(..., description="綜合投組健康總評分 [0, 100]")
    health_rating: str = Field(..., description="評級 (OPTIMAL, BALANCED, CAUTION, CRITICAL)")
    radar: HealthRadarSchema
    current_regime: str = Field(..., description="當前 HMM 預測市場體制")
    regime_confidence: float = Field(..., description="體制預測置信度 [0, 1]")
    needs_rebalance: bool = Field(..., description="是否建議啟動再平衡調倉")
    summary_insights: List[str] = Field(..., description="核心洞察分析摘要")


class DiagnosePortfolioRequest(BaseModel):
    current_weights: Optional[Dict[str, float]] = Field(
        None,
        description="當前持倉權重字典 (例: {'AAPL': 0.3, 'MSFT': 0.3, 'CASH': 0.4})。若未提供則從系統持倉自動提取。",
    )
    portfolio_value: Optional[float] = Field(100000.0, description="投組總淨資產 (USD)")
    asset_prices: Optional[Dict[str, float]] = Field(None, description="標的最新價格字典")
    asset_advs: Optional[Dict[str, float]] = Field(None, description="標的 20 日均成交量字典 (ADV)")
    market_observation: Optional[Dict[str, float]] = Field(
        None,
        description="市場即時觀測向量 {'spy_trend_ratio': 1.02, 'vix': 18.5, 'return_5d': 0.015}",
    )
    current_drawdown: Optional[float] = Field(0.05, description="投組當前自歷史高點回撤幅度 (0.0~1.0)")
    recent_win_rate: Optional[float] = Field(0.55, description="近期調倉/交易勝率")
    recent_payoff_ratio: Optional[float] = Field(1.8, description="近期賺賠比")


class DiagnosePortfolioResponse(BaseModel):
    status: str = "success"
    data: Dict[str, Any]


class RebalancePlanRequest(BaseModel):
    current_weights: Dict[str, float] = Field(..., description="當前持倉權重字典")
    portfolio_value: float = Field(..., description="投組總資產 (USD)")
    target_weights: Optional[Dict[str, float]] = Field(
        None, description="自定義目標權重 (若未提供則自動依 HRP+O1 生成)"
    )
    asset_prices: Optional[Dict[str, float]] = Field(None, description="標的最新市價")
    asset_advs: Optional[Dict[str, float]] = Field(None, description="標的 20 日均量")


class RebalancePlanResponse(BaseModel):
    status: str = "success"
    data: Dict[str, Any]
