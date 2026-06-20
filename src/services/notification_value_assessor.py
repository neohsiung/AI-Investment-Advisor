"""
NotificationValueAssessor — PAD Agent-based notification value assessment.

Uses the PAD LLM infrastructure (ResilientLLMPipeline + BudgetAwareModelRouter)
to assess whether a notification contains actionable, valuable information
worth sending to the user. Suppresses noise such as:
- Council failure / fail-safe mode messages
- "No action needed" / "hold all positions" verdicts
- Reports with no meaningful changes vs previous
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


async def assess_notification_value(
    title: str,
    content: str,
    category: str,
    user_id: str,
) -> Tuple[bool, str]:
    """
    Assess whether a notification is valuable enough to send.

    Uses a lightweight LLM call (FAST tier, single prompt) to classify
    the notification as VALUABLE or NOISE.

    Returns:
        (should_send: bool, reason: str)
    """
    # Truncate content to a reasonable size for classification
    MAX_CHARS = 3000
    truncated = content[:MAX_CHARS] if len(content) > MAX_CHARS else content

    system_prompt = (
        "You are a notification filter for a financial portfolio management system. "
        "Your job is to classify whether a notification has real value to the user.\n\n"
        "A notification is VALUABLE if it contains:\n"
        "- Actionable trading recommendations (buy/sell/reduce/hedge/trim)\n"
        "- Real-time alerts about market or portfolio changes\n"
        "- Risk warnings that require user attention\n"
        "- Report findings with concrete data changes\n\n"
        "A notification is NOISE if it contains:\n"
        "- System error messages, fail-safe mode notices, or LLM failure text\n"
        "- Vague statements like 'no action needed', 'everything is balanced', 'hold all'\n"
        "- Empty or boilerplate content without specific data\n"
        "- Duplicate information already seen"
    )

    user_prompt = (
        f"Category: {category}\n"
        f"Title: {title}\n"
        f"Content (first 3000 chars):\n{truncated}\n\n"
        "Respond with exactly one line: VALUABLE or NOISE, then a brief reason (10 words max).\n"
        "Examples:\n"
        "VALUABLE: Cash overweight 69% exceeds 25% limit, needs rebalancing\n"
        "NOISE: Council failed to reach consensus due to LLM error\n"
        "NOISE: No actionable changes detected in portfolio\n"
        "VALUABLE: S&P 500 +2.3%, NASDAQ +1.8%, actionable drift detected"
    )

    try:
        result = await _call_llm_assessment(system_prompt, user_prompt, user_id)

        result_lower = result.strip().lower()
        if result_lower.startswith("valuable"):
            logger.info(f"NotificationValueAssessor: VALUABLE — {result}")
            return True, result
        else:
            logger.info(f"NotificationValueAssessor: NOISE — {result}")
            return False, result

    except Exception as e:
        # If LLM assessment fails, err on the side of sending (don't suppress)
        logger.warning(f"NotificationValueAssessor: LLM call failed, sending anyway: {e}")
        return True, "LLM assessment unavailable"


async def _call_llm_assessment(
    system_prompt: str,
    user_prompt: str,
    user_id: str,
) -> str:
    """Make an LLM call through the existing PAD infrastructure using the FAST tier."""
    from src.services.settings_service import SettingsService
    from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter
    from src.domain.interfaces import LLMConfig, Message

    # Build router using the same pattern as base_agent.py
    settings_svc = SettingsService(user_id=user_id)
    from src.services.token_logger import TokenLoggerService
    router = BudgetAwareModelRouter(settings_svc, TokenLoggerService())

    # Get ResilientLLMPipeline for FAST tier
    pipeline = router.get_resilient_gateway(
        user_id=user_id,
        tier="fast",
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    response_text, attempts = await pipeline.execute(
        messages,
        temperature=0.1,
        max_tokens=60,
    )
    return response_text.strip()