"""
Cognitive Issue Types and Routing Specifications.
認知議題類型與模型階層路由規格。

Defines the domain classification for tasks and issues across the system,
mapping them to optimal cognitive tiers (reflex, fast, smart, advanced).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class CognitiveIssueType(str, Enum):
    """
    Standard issue categories across the quantitative platform.
    系統各子系統標準議題類別。
    """
    # ── Level 0: Reflex Tier (TypeSafe Jev 1.13) ──
    INTENT_ROUTING = "intent_routing"                    # 用戶自然語言意圖分類與技能選擇
    NEWS_RELEVANCE = "news_relevance"                    # 市場新聞與監控標的二元相關度初篩
    SENTINEL_BREACH = "sentinel_breach"                  # 哨兵集中度/回撤風控門檻越界判定
    EVENT_PRIORITIZATION = "event_prioritization"        # 事件佇列緊急度分級 (P0/P1/P2/P3)
    STATE_TRANSITION = "state_transition"                # 工作流 DAG 節點資料完備性與終止裁決

    # ── Level 1: Fast Tier (Claude Haiku / GPT-4o-mini) ──
    NEWS_SUMMARIZATION = "news_summarization"            # 市場快訊觀點與情緒快速摘要
    TECH_SIGNAL_EXTRACTION = "tech_signal_extraction"    # 技術面指標多空特徵描述
    NOTIFICATION_TONE_ADAPT = "notification_tone_adapt"  # LINE/Discord/Telegram 渠道語氣轉譯
    ROUTINE_DIGEST = "routine_digest"                    # 每日無交易常規營運摘要

    # ── Level 2: Smart Tier (Claude Sonnet / GPT-4o) ──
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"        # 個股基本面深度財報審計與評分
    RISK_HEDGING_EVAL = "risk_hedging_eval"              # 宏觀體制倒掛下的對沖策略評估
    ARBITRATION_ESCALATION = "arbitration_escalation"    # Jev 置信度不足時的慢思覆核
    RESEARCH_SYNTHESIS = "research_synthesis"            # 多方資料交叉驗證研報產出

    # ── Level 3: Advanced Tier (o1 / o3 / Claude Opus) ──
    STRATEGY_SYNTHESIS = "strategy_synthesis"            # 智庫評議會 10 代理人辯論終局仲裁
    CIO_DECISION = "cio_decision"                        # 投資長最終總裁決與黑天鵝緊急應變


class IssueRoutingSpec(BaseModel):
    """
    Routing configuration for a specific issue type.
    單一議題的認知層級路由規範。
    """
    issue_type: str = Field(..., description="Issue type identifier")
    default_tier: str = Field(..., description="Target model tier: reflex, nano, fast, smart, advanced")
    description: str = Field("", description="Human-readable description of this issue")
    confidence_threshold: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for reflex/fast escalation"
    )
    fallback_tier: Optional[str] = Field(
        default=None,
        description="Target tier if reflex escalates or fails"
    )
    timeout_ms: int = Field(
        default=800,
        description="Timeout in milliseconds for reflex calls"
    )
    is_reflex_eligible: bool = Field(
        default=False,
        description="Whether this issue is suitable for non-generative Jev arbiter"
    )
