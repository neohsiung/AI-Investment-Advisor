"""
Pydantic Schemas for Cognitive Blindspot Detector API (A2 Engine).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BlindspotSchema(BaseModel):
    id: str = Field(..., description="盲區記錄識別碼")
    user_id: str = Field(..., description="使用者 ID")
    agent_name: str = Field(..., description="專家 Agent 名稱")
    bias_pattern: str = Field(..., description="偏誤模式 (如 TREND_OVERCONFIDENCE, REGIME_MISMATCH)")
    regime: str = Field(..., description="發生偏誤之市場體制")
    consecutive_failures: int = Field(2, description="連續預測失誤次數")
    avg_alpha_loss: float = Field(0.0, description="平均損失之超額報酬 Alpha (%)")
    severity: str = Field("MEDIUM", description="嚴重度 (LOW, MEDIUM, HIGH, CRITICAL)")
    corrective_guidance: str = Field(..., description="注入之反省約束與提示詞引導")
    is_active: bool = Field(True, description="是否仍在作用中")
    detected_at: Optional[datetime] = Field(None, description="偵測發現時間")
    resolved_at: Optional[datetime] = Field(None, description="解除校準時間")


class BlindspotListResponse(BaseModel):
    status: str = "success"
    total_active: int = Field(0, description="活躍盲區總數")
    blindspots: List[BlindspotSchema] = Field(default_factory=list, description="盲區清單")


class BlindspotScanResponse(BaseModel):
    status: str = "success"
    scanned_agents: int = Field(..., description="掃描之專家數量")
    new_blindspots_detected: int = Field(..., description="新增偵測到的盲區數量")
    active_blindspots: List[BlindspotSchema] = Field(default_factory=list, description="當前有效之盲區")


class BlindspotResolveRequest(BaseModel):
    resolution_note: Optional[str] = Field(None, description="解除註記或人工校準說明")


class BlindspotResolveResponse(BaseModel):
    status: str = "success"
    blindspot_id: str = Field(..., description="已解除之盲區 ID")
    resolved_at: datetime = Field(..., description="解除時間")
