"""
Semantic Judge — LLM-as-a-Judge for Testing.
語義評判器 — 用於測試的 LLM-as-a-Judge。

v1.0 (Phase 6): 支援從 TierConfig 獲取 Nano/Fast 模型進行語義斷言。
"""

import os
import json
import logging
from typing import List, Optional, Any, Dict
from src.domain.interfaces import Message, LLMConfig
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
from src.infrastructure.llm.tier_config import TierConfig

logger = logging.getLogger(__name__)

def assert_semantic_match(actual: str, expected_intent: str, tier: str = "nano", 
                          provider: str = "OpenRouter") -> bool:
    """
    Perform a semantic match between a generated response and an expected intent description.
    透過 LLM 進行語義對照，取代脆弱的字串匹配。

    Args:
        actual (str): The actual generated content from the agent.
        expected_intent (str): A description of the expected meaning or information.
        tier (str, optional): LLM tier to use (cheapest recommended). Default: "nano".
        provider (str, optional): LLM provider to use. Default: "OpenRouter".

    Returns:
        bool: True if the LLM judges them as semantically matching.
    """
    # 1. Resolve model configuration
    # Note: Using TierConfig directly to ensure we stay within project standards.
    tier_cfg = TierConfig()
    model_name = tier_cfg.resolve(tier)
    
    # Priority: AI_TEST_API_KEY (CI/Testing) > OPENROUTER_API_KEY (Default)
    api_key = os.getenv("AI_TEST_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    
    if not api_key:
        # Fallback to simple keyword check if no API key is available
        # This keeps tests running but warns that semantic depth is reduced.
        logger.warning("SemanticJudge: No API key found. Falling back to simple keyword check.")
        # If expected_intent contains certain keywords, we check for them.
        keywords = [w for w in expected_intent.split() if len(w) > 4]
        if not keywords:
             return True
        return any(k.lower() in actual.lower() for k in keywords)

    # 2. Setup Gateway
    try:
        gateway = LLMGatewayFactory.create(provider)
        config = LLMConfig(
            provider=provider,
            model=model_name,
            api_key=api_key,
            temperature=0.0 # Strict classification
        )
    except Exception as e:
        logger.error(f"SemanticJudge: Setup failure: {e}")
        return expected_intent.lower() in actual.lower()

    # 3. Formulate Semantic Evaluation Prompt
    system_prompt = (
        "You are an objective AI quality judge. Your goal is to determine if the ACTUAL CONTENT "
        "semantically matches the EXPECTED INTENT description.\n\n"
        "Criteria:\n"
        "1. Focus on core meaning and information rather than literal wording.\n"
        "2. If the intent specifies a rejection, check if the content is a rejection.\n"
        "3. If the intent specifies a plan, check if the content outlines a plan.\n\n"
        "Respond with a JSON object: {\"match\": true/false, \"reason\": \"brief explanation\"}"
    )
    
    user_prompt = (
        f"EXPECTED INTENT: {expected_intent}\n"
        f"ACTUAL CONTENT: {actual}\n\n"
        f"Does it match?"
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt)
    ]

    # 4. Execute and Parse
    try:
        raw_response = gateway.chat(messages, config)
        
        # Clean and parse JSON
        clean_res = raw_response.strip().replace("```json", "").replace("```", "").strip()
        try:
             res_data = json.loads(clean_res)
             is_match = bool(res_data.get("match", False))
             reason = res_data.get("reason", "No reason provided.")
             
             if not is_match:
                 logger.info(f"SemanticJudge: Match failed. Reason: {reason}")
             
             return is_match
        except json.JSONDecodeError:
             # Fallback: Check for boolean strings if JSON fails
             return "TRUE" in raw_response.upper() and ("FALSE" not in raw_response.upper() or "NOT MATCH" not in raw_response.upper())

    except Exception as e:
        logger.error(f"SemanticJudge: LLM execution failure: {e}")
        return expected_intent.lower() in actual.lower()
