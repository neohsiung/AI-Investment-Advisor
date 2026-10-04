"""
Pydantic Schemas for Adaptive Council Meta-Learning API (A1 Engine).
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class AgentAttributionSchema(BaseModel):
    agent_name: str = Field(..., description="專家 Agent 名稱")
    total_calls: int = Field(0, description="歷史總決策數")
    correct_calls: int = Field(0, description="命中正 Alpha/保全次數")
    rolling_win_rate: float = Field(0.5, description="滾動勝率 [0, 1]")
    avg_alpha_contribution: float = Field(0.0, description="平均貢獻超額報酬 Alpha")
    regime_win_rates: Dict[str, float] = Field(default_factory=dict, description="各體制下之勝率分佈")


class MetaLearningStatusResponse(BaseModel):
    status: str = "success"
    current_regime: str = Field(..., description="當前 HMM 預測市場體制")
    regime_confidence: float = Field(..., description="體制預測置信度 [0, 1]")
    black_swan_alert_level: str = Field(..., description="O2 EVT 尾部黑天鵝告警層級")
    var_999: float = Field(..., description="99.9% 閉式解 1日極值損失 (VaR)")
    cvar_999: float = Field(..., description="99.9% 閉式解 預期尾部損失 (CVaR)")
    fat_tail_ratio: float = Field(..., description="肥尾放大倍數")
    health_score: float = Field(..., description="D1 五維健康總分 [0, 100]")
    health_rating: str = Field(..., description="D1 評級 (OPTIMAL, BALANCED, CAUTION, CRITICAL)")
    target_cash_buffer: float = Field(..., description="建議防禦現金水位 [0, 1]")
    target_beta: float = Field(..., description="目標總體組合 Beta")
    meta_weights: Dict[str, float] = Field(..., description="當前體制與歸因校準後之專家權重")
    prompt_guidance: str = Field(..., description="注入給 LLM 評議會的結構化前置先驗文字")
    veto_power_active: bool = Field(False, description="Risk Agent 是否啟動黑天鵝一票否決權")


class MetaLearningAttributionsResponse(BaseModel):
    status: str = "success"
    attributions: Dict[str, AgentAttributionSchema] = Field(..., description="各專家事後歸因指標清單")
