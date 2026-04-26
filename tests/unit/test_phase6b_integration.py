import pytest
from dataclasses import dataclass, field
from typing import Dict, Any
from unittest.mock import MagicMock, patch, AsyncMock
from src.infrastructure.llm.resilient_pipeline import ModelCandidate
from src.domain.interfaces import LLMConfig


def _make_candidate(model_code: str, tier: str = "smart") -> ModelCandidate:
    from src.infrastructure.llm.llm_gateway import MockLLMGateway
    return ModelCandidate(
        model_id=f"mock-{tier}",
        provider_code="mock",
        model_code=model_code,
        gateway_class=MockLLMGateway,
        base_url="",
        api_key="mock-key",
    )


@pytest.mark.asyncio
async def test_conversation_agent_uses_router_budget():
    """Budget=$21 (>hard limit): get_config_chain should return fast-tier candidate."""
    from src.agents.conversation_agent import ConversationAgent

    fast_candidate = _make_candidate("google/gemini-2.5-flash", tier="fast")

    with patch("src.agents.base_agent.BudgetAwareModelRouter") as MockRouter:
        inst = MockRouter.return_value
        # Simulate budget-aware downgrade: chain returns fast model
        inst.get_config_chain.return_value = [fast_candidate]

        agent_wrapper = ConversationAgent(user_id="test_user", tier="smart")
        await agent_wrapper._ensure_agent()

        inner_config = agent_wrapper._agent.config
        assert "gemini-2.5-flash" in inner_config["model"]


@pytest.mark.asyncio
async def test_conversation_agent_normal_budget():
    """Budget=$5 (<soft limit): get_config_chain should return smart-tier candidate."""
    from src.agents.conversation_agent import ConversationAgent

    smart_candidate = _make_candidate("google/gemini-2.5-pro", tier="smart")

    with patch("src.agents.base_agent.BudgetAwareModelRouter") as MockRouter:
        inst = MockRouter.return_value
        inst.get_config_chain.return_value = [smart_candidate]

        agent_wrapper = ConversationAgent(user_id="test_user", tier="smart")
        await agent_wrapper._ensure_agent()

        inner_config = agent_wrapper._agent.config
        assert "gemini-2.5-pro" in inner_config["model"]
