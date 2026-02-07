import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DynamicModelRouter:
    """
    Decides the optimal LLM Tier (Fast vs Smart) based on context.
    Implements the 'Cost Optimization' strategy for the Agent Council.
    """
    
    TIER_FAST = "fast"   # e.g., Gemini 1.5 Flash, GPT-4o-mini
    TIER_SMART = "smart" # e.g., Gemini 1.5 Pro, GPT-4o

    def __init__(self):
        self.complex_keywords = [
            "crash", "crisis", "panic", "collapse", 
            "fraud", "audit", "restructure", "unprecedented",
            "black swan", "recession"
        ]

    def select_tier(self, topic: str, round_num: int = 1, market_volatility: float = 0.0) -> str:
        """
        Selects the LLM tier.
        
        Args:
            topic: The debate topic or question.
            round_num: The current round of the debate (1-indexed).
            market_volatility: Current VIX or similar volatility metric.
            
        Returns:
            "fast" or "smart"
        """
        reason = []
        tier = self.TIER_FAST

        # Rule 1: High Market Volatility (Crisis Protocol)
        if market_volatility > 25.0:
            tier = self.TIER_SMART
            reason.append(f"High Volatility (VIX={market_volatility})")

        # Rule 2: Deep Debate Arbitration (Round > 3)
        # If we can't agree after 3 rounds, we need the smartest model to arbitrate.
        elif round_num > 3:
            tier = self.TIER_SMART
            reason.append(f"Deep Debate (Round {round_num})")

        # Rule 3: Complex/Dangerous Topics
        elif any(w in topic.lower() for w in self.complex_keywords):
            tier = self.TIER_SMART
            reason.append(f"Complex Topic Keyword found")

        # Rule 4: Explicit "Deep Research" Request
        elif "deep research" in topic.lower() or "detailed analysis" in topic.lower():
            tier = self.TIER_SMART
            reason.append("Explicit Deep Research Request")
            
        if tier == self.TIER_SMART:
            logger.info(f"Router: Escalated to SMART tier. Reason: {', '.join(reason)}")
        else:
            # logger.debug("Router: Selected FAST tier.")
            pass
            
        return tier
