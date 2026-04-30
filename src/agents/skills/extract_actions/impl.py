import json
import re
import os
import logging
from typing import List, Dict, Any, Optional

from src.utils.logger import setup_logger
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
from src.domain.interfaces import Message, LLMConfig
from src.repositories.settings_repository import AlchemySettingsRepository

logger = setup_logger("skill_extract_actions")

async def extract_actions(
    user_id: str,
    decision_text: str,
    portfolio: str = ""
) -> str:
    """
    Extract Actions Skill — Parses free-form AI text into structured trade JSON.
    從非結構化 AI 文字中提取結構化交易指令。
    
    Args:
        user_id: User context for API keys and settings
        decision_text: The decision text from CIO/Council
        portfolio: Current portfolio holdings for validation (optional)
        
    Returns:
        JSON string containing list of trade objects.
    """
    if not decision_text:
        return "[]"

    logger.info(f"Extracting actions for user {user_id}...")

    try:
        # 1. Resolve API Settings
        settings_repo = AlchemySettingsRepository()
        provider = settings_repo.get(user_id, "preferred_provider", "gemini")
        
        # Use tier-aware routing for model selection (nano tier for action extraction)
        from src.infrastructure.llm.tier_config import SettingsAwareModelRouter, TierConfig
        model_router = SettingsAwareModelRouter(settings_repo)
        if user_id:
            model = model_router.get_model(user_id, "nano")
        else:
            tier_config = TierConfig()
            model = tier_config.resolve("nano")
        api_key = settings_repo.get(user_id, f"source_{provider}_api_key", os.environ.get(f"{provider.upper()}_API_KEY"))

        if not api_key:
            logger.error(f"Missing API key for provider {provider}")
            return "[]"

        # 2. Prepare Prompt
        portfolio_block = ""
        if portfolio:
            portfolio_block = f"""
        
        PORTFOLIO HOLDINGS (Current):
        {portfolio}
        
        ⚠️ CRITICAL: Use the above holdings to determine quantity. 
        For SELL: quantity MUST NOT exceed the actual holding shown above.
        For BUY: quantity is in USD amount."""

        system_prompt = f"""
        You are an Action Extraction AI.
        Analyze the following investment council decision and extract any explicit trade recommendations or portfolio allocation changes.
        {portfolio_block}
        
        Rules:
        1. Only extract explicit trade recommendations (buying, selling, trimming, adding).
        2. 'action' must be exactly "BUY", "SELL", or "HOLD".
        3. Support TWO formats:
           a) Legacy: 'quantity' is numeric (shares/USD amount)
           b) v7.0: 'target_weight', 'current_weight', 'delta_weight' for weight-based position sizing
        4. 'confidence' must be an integer between 1 and 10, where 10 is highest conviction.
        5. 'intent' must be one of: "full_close", "partial_reduce", or omitted for BUY.
        6. Output ONLY a valid JSON array of objects, with NO surrounding markdown block quotes.
        7. If the decision mentions weights (percentages of portfolio), extract as v7.0 format:
           {{"ticker": "AAPL", "action": "BUY", "target_weight": 0.08, "current_weight": 0.05, "delta_weight": 0.03, "confidence": 9, "reason": "..."}}
        8. If no explicit trades are found, output an empty array [].
        
        Example Output (v7.0 weight-based):
        [
            {{"ticker": "NVDA", "action": "SELL", "target_weight": 0.10, "current_weight": 0.15, "delta_weight": -0.05, "confidence": 8, "reason": "Reason here"}},
            {{"ticker": "AAPL", "action": "BUY", "target_weight": 0.08, "current_weight": 0.05, "delta_weight": 0.03, "confidence": 9, "reason": "Reason here"}}
        ]
        """

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=f"Decision Text:\n{decision_text}")
        ]

        # 3. Call LLM (Gateway Factory creates a provider-specific gateway)
        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            temperature=0.0
        )
        
        gateway = LLMGatewayFactory.create(provider)
        response = await gateway.chat(messages, config)

        # 4. Parse Response
        response_clean = response.strip()
        match = re.search(r'\[\s*\{.*?\}\s*\]', response_clean, re.DOTALL)
        if match:
            response_clean = match.group(0)
        else:
            # Fallback to markdown cleaning
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:-3].strip()
            elif response_clean.startswith("```"):
                response_clean = response_clean[3:-3].strip()

        # Simple validation
        trades = json.loads(response_clean)
        if not isinstance(trades, list):
            logger.warning(f"Extracted result is not a list: {trades}")
            return "[]"
            
        return json.dumps(trades, ensure_ascii=False)

    except Exception as e:
        logger.error(f"extract_actions skill failed: {e}", exc_info=True)
        return "[]"
