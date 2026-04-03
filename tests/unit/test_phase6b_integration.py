import pytest
from unittest.mock import MagicMock, patch
from src.agents.conversation_agent import ConversationAgent
from src.domain.interfaces import LLMConfig

@pytest.fixture
def mock_spending():
    with patch("src.services.token_logger_service.TokenLoggerService.get_user_spending") as m:
        yield m

@pytest.fixture
def mock_router():
    with patch("src.agents.base_agent.BudgetAwareModelRouter") as m:
        # Create an instance mock
        inst = m.return_value
        yield inst

def test_conversation_agent_uses_router_budget(mock_spending, mock_router):
    # Case: Budget is high ($21), should downgrade to Fast
    mock_spending.return_value = {"total_cost": 21.0}
    
    # Setup router mock to return an LLMConfig for 'fast' tier
    mock_router.get_config.return_value = LLMConfig(provider="OpenRouter", model="google/gemini-2.5-flash")
    
    # Initialize ConversationAgent (tier=smart)
    agent_wrapper = ConversationAgent(user_id="test_user", tier="smart")
    agent_wrapper._ensure_agent()
    
    # The inner agent should have its config determined by BudgetAwareModelRouter
    inner_config = agent_wrapper._agent.config
    
    # 'smart' should be downgraded to 'fast'
    assert "gemini-2.5-flash" in inner_config["model"]

def test_conversation_agent_normal_budget(mock_spending, mock_router):
    # Case: Budget is low ($5), should keep Smart
    mock_spending.return_value = {"total_cost": 5.0}
    
    # Setup router mock to return an LLMConfig for 'smart' tier
    mock_router.get_config.return_value = LLMConfig(provider="OpenRouter", model="google/gemini-2.5-pro")
    
    agent_wrapper = ConversationAgent(user_id="test_user", tier="smart")
    agent_wrapper._ensure_agent()
    
    inner_config = agent_wrapper._agent.config
    
    # 'smart' should remain 'smart'
    assert "gemini-2.5-pro" in inner_config["model"]
