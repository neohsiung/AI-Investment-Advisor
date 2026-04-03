"""
Council Tier Router — Context-Aware LLM Tier Selection for Agent Council.
委員會層級路由器 — 為 Agent 委員會提供情境感知的 LLM 層級選擇。

職責:
  根據市場情境（VIX 波動率、辯論主題複雜度、辯論輪次）動態決定
  使用哪個模型層級 (Tier)。
"""

import logging
from typing import List
from src.infrastructure.llm.tier_router_base import ITierRouter, RoutingContext

logger = logging.getLogger(__name__)


class CouncilTierRouter(ITierRouter):
    """
    Context-aware LLM Tier Router for Agent Council Sessions.

    Tier Priority Rules (高 → 低):
      1. 高市場波動 (VIX > 25)       → smart
      2. 深度辯論 (round_num > 3)    → smart
      3. 複雜/危機 topic 關鍵字       → smart
      4. 戰略/深研究 topic 關鍵字     → advanced
      5. 預設                         → fast
    """

    TIER_NANO = "nano"
    TIER_FAST = "fast"
    TIER_SMART = "smart"
    TIER_ADVANCED = "advanced"

    DEFAULT_COMPLEX_KEYWORDS: List[str] = [
        "crash", "crisis", "panic", "collapse",
        "fraud", "audit", "restructure", "unprecedented",
        "black swan", "recession", "systemic risk",
    ]

    DEFAULT_STRATEGIC_KEYWORDS: List[str] = [
        "deep research", "strategy", "long-term thesis",
        "portfolio restructure", "macro regime change",
    ]

    def __init__(
        self,
        complex_keywords: List[str] = None,
        strategic_keywords: List[str] = None,
    ):
        self.complex_keywords = complex_keywords or self.DEFAULT_COMPLEX_KEYWORDS
        self.strategic_keywords = strategic_keywords or self.DEFAULT_STRATEGIC_KEYWORDS

    def select_tier(self, context: RoutingContext) -> str:
        """
        Select the optimal LLM Tier for the given context.
        """
        topic_lower = context.topic.lower()
        reasons = []
        tier = self.TIER_FAST

        # Rule 1: High Market Volatility
        if context.market_volatility > 25.0:
            tier = self.TIER_SMART
            reasons.append(f"High Volatility (VIX={context.market_volatility:.1f})")

        # Rule 2: Deep Debate
        elif context.round_num > 3:
            tier = self.TIER_SMART
            reasons.append(f"Deep Debate (Round {context.round_num})")

        # Rule 3: Complex Keywords
        elif any(kw in topic_lower for kw in self.complex_keywords):
            matched = next(kw for kw in self.complex_keywords if kw in topic_lower)
            tier = self.TIER_SMART
            reasons.append(f"Complex Keyword: '{matched}'")

        # Rule 4: Strategic Keywords
        elif any(kw in topic_lower for kw in self.strategic_keywords):
            matched = next(kw for kw in self.strategic_keywords if kw in topic_lower)
            tier = self.TIER_ADVANCED
            reasons.append(f"Strategic Keyword: '{matched}'")

        if reasons:
            logger.info(f"CouncilTierRouter: Escalated to {tier.upper()}. Reason: {', '.join(reasons)}")

        return tier

    def select_tier_legacy(
        self,
        topic: str,
        round_num: int = 1,
        market_volatility: float = 0.0,
    ) -> str:
        """
        [DEPRECATED] Legacy interface for backward compatibility.
        """
        import warnings
        warnings.warn(
            "select_tier_legacy() is deprecated. Use select_tier(RoutingContext(...)) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.select_tier(
            RoutingContext(
                topic=topic,
                round_num=round_num,
                market_volatility=market_volatility,
            )
        )
