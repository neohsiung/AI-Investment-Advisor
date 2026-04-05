"""
Meta-Prompt Agent — Cognition Layer [Phase 18].
元提示詞 Agent — 負責分析用戶反饋，動態優化 Agent 的 System Prompt。

This agent acts as a supervisor that implements Reinforcement Learning from Human 
Feedback (RLHF) logic by rewriting prompts based on user dissatisfaction (+1/-1).
"""

import json
import logging
from typing import Dict, Any, List
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

class MetaPromptAgent(BaseAgent):
    """
    Cognitive Optimizer that rewrites instructions for other agents.
    """
    def __init__(self, **kwargs):
        # Meta-prompting requires higher reasoning capability.
        tier = kwargs.pop('tier', 'smart')
        super().__init__(
            name="MetaPrompt",
            prompt_path="prompts/meta_prompt_agent.txt", 
            use_cache=False, 
            tier=tier,
            **kwargs
        )

    async def optimize_prompt(
        self, 
        agent_name: str, 
        current_prompt: str, 
        negative_feedback: List[Dict[str, Any]]
    ) -> str:
        """
        Takes current prompt and negative feedback examples, 
        returns a new, improved system prompt string.
        """
        if not negative_feedback:
            return current_prompt

        system_prompt = (
            "You are the Meta-Prompt Engineering Expert. "
            "Your goal is to optimize a System Prompt based on recent negative user feedback. "
            "You must ensure the new prompt retains the core logic of the agent but corrects the specific pain points mentioned. "
            "Respond ONLY with the full NEW system prompt text."
        )
        
        feedback_summary = "\n".join([
            f"- User Feedback: '{f.get('comment', 'N/A')}' (Score: {f.get('vote')})"
            for f in negative_feedback
        ])
        
        user_prompt = (
            f"Optimizing Agent: {agent_name}\n\n"
            f"--- [Current System Prompt] ---\n{current_prompt}\n\n"
            f"--- [User Dissatisfaction Summary] ---\n{feedback_summary}\n\n"
            "Please provide the NEW system prompt that resolves these issues:"
        )
        
        try:
            # High-tier reasoning call
            new_prompt = self.call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            return new_prompt
        except Exception as e:
            logger.error(f"MetaPromptAgent failed: {e}")
            return current_prompt
