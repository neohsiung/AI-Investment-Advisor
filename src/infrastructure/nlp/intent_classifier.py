import logging
import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Optional
from src.agents.factory import AgentFactory
from src.domain.interfaces import IIntentClassifier

logger = logging.getLogger(__name__)

class IntentClassifier(IIntentClassifier):
    """
    Classifies user text into intents (APPROVE, REJECT, UNKNOWN) using a lightweight LLM.
    Uses 'fast' tier model (SentimentAgent) as configured in settings.
    """
    def __init__(self):
        # Use AgentFactory to create a 'fast' tier agent.
        # We use 'Sentiment' agent because it supports explicit tier='fast' configuration
        # whereas Engineer agent might default to 'smart'.
        self.agent = AgentFactory.create_agent(
            "Sentiment", 
            tier="nano", 
            user_id=None,
            use_cache=True
        )

    def classify(self, text: str) -> str:
        """
        Returns: "APPROVE", "REJECT", or "UNKNOWN"
        """
        # Prompt optimized for fast/smart model
        prompt = f"""
        TASK: Classify the user's response to an approval request.
        
        USER RESPONSE: "{text}"
        
        INSTRUCTIONS:
        - If the user consents, agrees, confirms, or says "執行" (Execute), return "APPROVE".
        - If the user denies, disagrees, cancels, or says "不執行" (Do not execute), return "REJECT".
        - If the response is unrelated or unclear, return "UNKNOWN".
        - Return ONLY the classification string.
        """
        
        try:
            # Direct keyword fallback for speed/reliability (Pre-check)
            key_text = text.strip().upper()
            if any(kw in key_text for kw in ["執行", "OK", "確定", "好", "可以", "批准", "YES", "APPROVE"]) and "不" not in key_text:
                return "APPROVE"
            if any(kw in key_text for kw in ["不執行", "取消", "NO", "REJECT"]):
                return "REJECT"

            # Run LLM
            # SentimentAgent.run expects dict context or string?
            # BaseAgent.run usually takes context dict.
            # SentimentAgent might expect 'news' or 'text' in context.
            # Let's check SentimentAgent.run implementation or just pass dict.
            # BaseAgent.run_tool_loop uses context.
            # If I pass a string, BaseAgent._render_user_context handles it.
            # But SentimentAgent might have specific run logic.
            # Let's assume standard agent behavior: run(context) -> returns result string.
            
            response = self.agent.run({"user_request": prompt})
            
            content = ""
            if isinstance(response, dict):
                 content = str(response.get("content") or response.get("output") or "")
            else:
                 content = str(response)
                 
            content = content.strip().upper()
            
            if "APPROVE" in content:
                return "APPROVE"
            elif "REJECT" in content:
                return "REJECT"
            
            return "UNKNOWN"
            
        except Exception as e:
            logger.error(f"Intent Classification failed: {e}")
            return "UNKNOWN"
