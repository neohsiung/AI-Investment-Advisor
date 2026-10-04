"""
Pydantic Schemas for Council Debate Memory & Vector Retrieval API (A3 Engine).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DebateOutcomeSchema(BaseModel):
    outcome_id: str = Field(..., description="決策結算紀錄 ID")
    ticker: str = Field(..., description="標的代號")
    agent_name: str = Field(..., description="專家 Agent 名稱")
    signal: str = Field(..., description="推薦訊號 (BUY, HOLD, SELL)")
    realized_return_pct: Optional[float] = Field(None, description="實現報酬率 (%)")
    benchmark_return_pct: Optional[float] = Field(None, description="基準報酬率 (%)")
    alpha_pct: Optional[float] = Field(None, description="超額報酬率 Alpha (%)")
    lesson: Optional[str] = Field(None, description="事後歸因覆盤經驗教訓")
    resolved_at: Optional[str] = Field(None, description="結算時間")


class DebatePrecedentSchema(BaseModel):
    minute_id: str = Field(..., description="歷史辯論紀要 ID")
    session_id: str = Field(..., description="歷史評議會會議 ID")
    topic: str = Field(..., description="辯論議題")
    consensus: str = Field(..., description="歷史共識裁決摘要")
    created_at: str = Field(..., description="辯論時間")
    similarity: float = Field(..., description="語意嵌入向量相似度")
    relevance_score: float = Field(..., description="多因子複合排序評分")
    has_attribution: bool = Field(False, description="是否具備事後 Alpha 結算紀錄")
    avg_alpha_pct: Optional[float] = Field(None, description="平均超額報酬率 (%)")
    outcomes: List[DebateOutcomeSchema] = Field(default_factory=list, description="關聯之決策結算歷程")
    participants: Optional[str] = Field(None, description="參與辯論專家清單")
    transcript_preview: Optional[str] = Field(None, description="辯論逐字稿預覽")


class CouncilMemorySearchRequest(BaseModel):
    query: str = Field(..., description="搜尋關鍵字或議題描述 (例如: 'AI 晶片庫存週期與估值擴張')")
    ticker: Optional[str] = Field(None, description="選填標的代號篩選 (例如: NVDA)")
    min_alpha: Optional[float] = Field(None, description="選填最小超額報酬率 Alpha 門檻 (%)")
    limit: int = Field(5, ge=1, le=50, description="回傳前例數量上限")


class CouncilMemorySearchResponse(BaseModel):
    status: str = "success"
    query: str = Field(..., description="搜尋條件")
    total_found: int = Field(..., description="檢索到之歷史先例筆數")
    synthesized_prompt_context: str = Field(..., description="合成之提示詞上下文區塊")
    precedents: List[DebatePrecedentSchema] = Field(default_factory=list, description="前例清單")


class CouncilMemoryDetailResponse(BaseModel):
    status: str = "success"
    minute_id: str = Field(..., description="辯論紀要 ID")
    session_id: str = Field(..., description="會議 Session ID")
    user_id: str = Field(..., description="租戶識別碼")
    topic: str = Field(..., description="辯論議題")
    participants: Optional[str] = Field(None, description="參與專家清單")
    consensus: Optional[str] = Field(None, description="共識裁決完整紀錄")
    transcript: Optional[str] = Field(None, description="辯論逐字稿完整紀錄")
    created_at: Optional[str] = Field(None, description="建立時間")
    outcomes: List[DebateOutcomeSchema] = Field(default_factory=list, description="關聯之決策結算明細")
