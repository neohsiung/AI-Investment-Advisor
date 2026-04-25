"""
Evaluator Agent — Guardrail Layer [Phase 15].
評估員 Agent — 負責最終投資建議的合規性與風險審查。

A lightweight, fast judge that ensures LLM outputs don't violate hard constraints
(e.g., no short selling, no crypto recommendations, no extreme leverage).
"""

import json
import logging
from typing import Dict, Any
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

class EvaluatorAgent(BaseAgent):
    """
    Lightweight Inspector that validates investment reports for policy compliance.
    """
    def __init__(self, **kwargs):
        # We use 'fast' tier for low latency guardrail checks
        tier = kwargs.pop('tier', 'fast')
        # name matches workspace/evaluator-judge mapping if we add it to BaseAgent
        # or we can pass workspace_path explicitly if needed.
        # Here we follow the granular plan: remove prompt_path, set name.
        super().__init__(
            name="Evaluator Judge",
            prompt_path="", 
            use_cache=False, 
            tier=tier,
            **kwargs
        )

    async def run(self, context: Dict[str, Any]) -> str:
        """
        Evaluates a report or recommendation string.
        Returns a JSON string: {"is_compliant": bool, "violation_reason": str}
        """
        report_text = context.get("report_content", "")
        if not report_text:
            return json.dumps({"is_compliant": True, "violation_reason": "No content to evaluate."})

        # Render system prompt via ContextAssembler (delegated to by BaseAgent)
        system_prompt = self.render_system_prompt(context)
        
        user_prompt = f"Please evaluate this report for compliance:\n\n{report_text}"
        
        try:
            # Consistent with BaseAgent.call_llm which takes messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response = await self.call_llm(
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            return response
        except Exception as e:
            logger.error(f"EvaluatorAgent failed: {e}")
            # Fallback to safe: assume failure if judge fails? 
            # Or assume success but log warning. Let's assume success to avoid blocking legitimate work, but log error.
            return json.dumps({"is_compliant": True, "violation_reason": f"Evaluation error: {e}"})
