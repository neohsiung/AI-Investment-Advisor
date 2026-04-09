import sys
import os
sys.path.append(os.getcwd())

from src.agents.factory import AgentFactory
from unittest.mock import patch, MagicMock

# Correcting the patch targets
with patch('src.agents.factory.AgentFactory._configure_dspy'), \
     patch('src.agents.factory.create_market_server', return_value=MagicMock()), \
     patch('src.agents.base_agent.BaseAgent._load_config', return_value={"model": "test", "provider": "test"}), \
     patch('src.agents.base_agent.AlchemySettingsRepository'), \
     patch('src.agents.base_agent.AlchemyAgentStateRepository'), \
     patch('src.agents.base_agent.AlchemyFeedbackRepository'), \
     patch('src.agents.base_agent.HybridMemory'), \
     patch('src.services.cognitive_memory_manager.CognitiveMemoryManager'), \
     patch('src.repositories.prompt_repository.AlchemyPromptRepository'):

    # Avoid injecting real dependencies that might fail
    with patch.object(AgentFactory, '_inject_dependencies', side_effect=lambda x: x):
        mom = AgentFactory.create_momentum_agent(user_id="test")
        print(f"Momentum Tier: {mom.tier}")

        fund = AgentFactory.create_fundamental_agent(user_id="test")
        print(f"Fundamental Tier: {fund.tier}")

        cio = AgentFactory.create_cio_agent(user_id="test")
        print(f"CIO Tier: {cio.tier}")
