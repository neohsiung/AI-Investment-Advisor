import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DynamicModelRouter:
    """
    Decides the optimal LLM Tier (Fast vs Smart) based on context.
    Implements the 'Cost Optimization' strategy for the Agent Council.
    """
    
    TIER_ADVANCED = "advanced" # Level 3+ (戰略): e.g., Deep Research, Strategy Refinement
    TIER_SMART = "smart"      # Level 2  (智囊): e.g., Council Debate, Complex Analysis
    TIER_FAST = "fast"        # Level 1  (前鋒): e.g., Sentinel ticks, simple tasks

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

        # Rule 4: Strategic / Deep Research
        elif "deep research" in topic.lower() or "strategy" in topic.lower():
            tier = self.TIER_ADVANCED
            reason.append("Strategic / Deep Research Request")
            
        if tier == self.TIER_SMART:
            logger.info(f"Router: Escalated to SMART tier. Reason: {', '.join(reason)}")
        else:
            # logger.debug("Router: Selected FAST tier.")
            pass
            
        return tier
