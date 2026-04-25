"""
Sensory Agent — Proactive Layer [Phase 17].
感測員 Agent — 負責全天候掃描市場異動，主動觸發預警。

A highly specialized, low-cost agent designed for high-frequency scanning.
It doesn't perform deep analysis but identifies 'interest points' (Actionable alerts).
"""

import json
import logging
from typing import Dict, Any, List
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

class SensoryAgent(BaseAgent):
    """
    Market Watchdog that scans price movements or news for immediate alpha.
    """
    def __init__(self, **kwargs):
        # Sensory agents MUST use 'nano' or 'fast' to keep background scanning costs low.
        tier = kwargs.pop('tier', 'fast')
        super().__init__(
            name="Sensory Watchdog",
            prompt_path="", 
            use_cache=False, 
            tier=tier,
            **kwargs
        )

    async def run(self, context: Dict[str, Any]) -> str:
        """
        Scans a target (ticker/news) and determines if an alert is needed.
        Returns a JSON: {"alert_needed": bool, "reason": str, "urgency": "low|med|high"}
        """
        ticker = context.get("ticker", "UNKNOWN")
        price_info = context.get("price_info", "N/A")
        recent_news = context.get("recent_news", "N/A")

        # Render system prompt via ContextAssembler (delegated to by BaseAgent)
        system_prompt = self.render_system_prompt(context)
        
        user_prompt = f"Ticker: {ticker}\nPrice Data: {price_info}\nRecent News: {recent_news}"
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response = await self.call_llm(
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            return response
        except Exception as e:
            logger.error(f"SensoryAgent failed to scan {ticker}: {e}")
            return json.dumps({"alert_needed": False, "reason": f"Error: {e}", "urgency": "low"})
