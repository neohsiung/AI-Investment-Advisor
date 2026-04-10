import os
import json
import uuid
import difflib
try:
    import dspy
    has_dspy = True
except ImportError:
    dspy = None
    has_dspy = False

from src.utils.logger import setup_logger
from src.repositories.settings_repository import AlchemySettingsRepository
from src.repositories.feedback_repository import AlchemyFeedbackRepository
from src.agents.swarm.momentum_swarm import MomentumSwarm
from src.agents.swarm.fundamental_swarm import FundamentalSwarm
from src.agents.swarm.sentiment_swarm import SentimentSwarm
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.engineer import SystemEngineerAgent
from src.agents.risk import RiskAgent
from src.agents.sentinel import SentinelAgent

logger = setup_logger("AgentFactory")

class AgentFactory:
    """
    Factory for creating Agent instances with consistent configuration.
    Implements **Factory Pattern** and **Dependency Injection**.
    建立 Agent 實例的工廠，確保配置一致。
    實作 **工廠模式 (Factory Pattern)** 與 **依賴注入 (Dependency Injection)**。
    """
    
    _dspy_configured = False

    @classmethod
    def _configure_dspy(cls, user_id: str = None):
        """
        Enable DSPy if installed and credentials are present (Env > User DB > Global DB).
        若已安裝 DSPy 且憑證存在 (Env > User DB > Global DB)，則啟用之。
        """
        if cls._dspy_configured:
            return
            
        if not has_dspy:
            cls._dspy_configured = True
            return

        api_key = os.getenv("LLM_API_KEY") or os.getenv("API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        model = os.getenv("LLM_MODEL_SMART", "google/gemini-2.0-flash-exp")

        if not api_key:
            try:
                repo = AlchemySettingsRepository()
                # 1. Try User Specific Key
                if user_id:
                    api_key = repo.get(user_id, "API_KEY") or repo.get(user_id, "LLM_API_KEY")
            except Exception as e:
                logger.warning(f"Failed to load API_KEY from DB for DSPy: {e}")

        if api_key:
            try:
                if hasattr(dspy, 'OpenAI'):
                    lm = dspy.OpenAI(model=model, api_key=api_key, api_base=base_url, max_tokens=2048)
                    dspy.settings.configure(lm=lm)
                    logger.info(f"DSPy configured with model: {model} for user: {user_id}")
                else:
                     logger.warning("DSPy module present but missing OpenAI class.")
            except Exception as e:
                logger.warning(f"Failed to configure DSPy: {e}")
        
        cls._dspy_configured = True

    @staticmethod
    def _inject_dependencies(agent):
        """
        Helper to inject common dependencies.
        注入通用依賴的輔助函數。
        """
        if not hasattr(agent, 'feedback_repo') or agent.feedback_repo is None:
             agent.feedback_repo = AlchemyFeedbackRepository()
        
        return agent

    @staticmethod
    def create_agent(agent_name, use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        name_lower = agent_name.lower()
        
        agent = None
        if name_lower == 'momentum':
            agent = MomentumSwarm(user_id=user_id, **kwargs)
        elif name_lower == 'fundamental':
            agent = FundamentalSwarm(user_id=user_id, **kwargs)
        elif name_lower == 'macro':
            agent = MacroAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'cio':
            agent = CIOAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'engineer':
            agent = SystemEngineerAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'sentiment':
            agent = SentimentSwarm(user_id=user_id, **kwargs)
        elif name_lower == 'risk':
            agent = RiskAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'thematic':
            from src.agents.thematic import ThematicAgent
            agent = ThematicAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'sentinel':
            agent = SentinelAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'conversation':
            # Support conversation role (uses CIO agent logic for general interaction)
            agent = CIOAgent(use_cache=use_cache, user_id=user_id, mode="daily", **kwargs)
        else:
            raise ValueError(f"Unknown agent type: {agent_name}")
            
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_thematic_agent(use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        from src.agents.thematic import ThematicAgent
        agent = ThematicAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_momentum_agent(use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        # tier = kwargs.pop('tier', 'fast') # Swarm manages tiers
        agent = MomentumSwarm(user_id=user_id, use_cache=use_cache, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_fundamental_agent(use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        # tier = kwargs.pop('tier', 'smart')
        agent = FundamentalSwarm(user_id=user_id, use_cache=use_cache, **kwargs)
        return AgentFactory._inject_dependencies(agent)
        
    @staticmethod
    def create_macro_agent(use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        tier = kwargs.pop('tier', 'smart')
        agent = MacroAgent(use_cache=use_cache, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_sentiment_agent(use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        # tier = kwargs.pop('tier', 'fast')
        agent = SentimentSwarm(user_id=user_id, use_cache=use_cache, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_risk_agent(use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        tier = kwargs.pop('tier', 'fast')
        agent = RiskAgent(use_cache=use_cache, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_cio_agent(use_cache=True, transaction_repo=None, mode="weekly", tier="smart", user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        prompt_map = {
            "daily": "prompts/cio_daily.txt",
            "weekly": "prompts/cio_weekly.txt",
            "sentinel": "prompts/cio_sentinel.txt"
        }
        prompt_path = prompt_map.get(mode, "prompts/cio_weekly.txt")
        agent = CIOAgent(use_cache=use_cache, transaction_repo=transaction_repo, prompt_path=prompt_path, mode=mode, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_sentinel_agent(use_cache=True, user_id=None, **kwargs):
        user_id = user_id or "system"
        AgentFactory._configure_dspy(user_id=user_id)
        agent = SentinelAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

