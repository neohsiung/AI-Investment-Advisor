from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.engineer import SystemEngineerAgent
from src.agents.sentiment import SentimentAgent
import os
import logging

try:
    import dspy
    has_dspy = True
except ImportError:
    has_dspy = False

logger = logging.getLogger(__name__)

class AgentFactory:
    """
    Factory for creating Agent instances with consistent configuration.
    Supports Dependency Injection and standardizing Cache/TTL settings.
    """
    
    _dspy_configured = False

    @classmethod
    def _configure_dspy(cls):
        """Enable DSPy if installed and credentials are present (Env > DB)."""
        if cls._dspy_configured or not has_dspy:
            return

        # 1. Try Environment Variables
        api_key = os.getenv("LLM_API_KEY") or os.getenv("API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        model = os.getenv("LLM_MODEL_SMART", "google/gemini-2.0-flash-exp")

        # 2. Try DB if Env missing (via SettingsRepository)
        # Note: Factory is static, so we instantiate repo just for this check if needed.
        if not api_key:
            try:
                from src.repositories.settings_repository import SqliteSettingsRepository
                repo = SqliteSettingsRepository()
                # Check Global or System settings
                # Assuming 'system' user_id or global key
                rows = repo.get_global()
                for row in rows:
                     # Adapt to return type of get_global which might be Row or Tuple
                     k = row._mapping['key'] if hasattr(row, '_mapping') else row[0]
                     v = row._mapping['value'] if hasattr(row, '_mapping') else row[1]
                     if k == "API_KEY" and v:
                         api_key = v
                         logger.info("Loaded API_KEY from DB for DSPy.")
                         break
            except Exception as e:
                logger.warning(f"Failed to load API_KEY from DB for DSPy: {e}")

        if api_key:
            try:
                # Configure DSPy with OpenRouter (OpenAI compatible)
                lm = dspy.OpenAI(
                    model=model,
                    api_key=api_key,
                    api_base=base_url,
                    max_tokens=2048
                )
                dspy.settings.configure(lm=lm)
                cls._dspy_configured = True
                logger.info(f"DSPy configured with model: {model}")
            except Exception as e:
                logger.warning(f"Failed to configure DSPy: {e}")
        else:
            logger.warning("DSPy installed but API_KEY missing (Env & DB).")

    @staticmethod
    def create_agent(agent_name, use_cache=True, user_id="system", **kwargs):
        AgentFactory._configure_dspy()
        """
        Create an agent by name.
        
        Args:
            agent_name (str): Name of the agent ('Momentum', 'Fundamental', 'Macro', 'CIO', 'Dispatcher', 'Engineer').
            use_cache (bool): Whether to enable caching for this agent instance.
            **kwargs: Additional arguments to pass to the agent constructor.
            
        Returns:
            BaseAgent: An instance of the requested agent.
        """
        name_lower = agent_name.lower()
        
        if name_lower == 'momentum':
            return MomentumAgent(use_cache=use_cache, user_id=user_id, **kwargs)
            
        elif name_lower == 'fundamental':
            return FundamentalAgent(use_cache=use_cache, user_id=user_id, **kwargs)
            
        elif name_lower == 'macro':
            return MacroAgent(use_cache=use_cache, user_id=user_id, **kwargs)
            
        elif name_lower == 'cio':
            return CIOAgent(use_cache=use_cache, user_id=user_id, **kwargs)
            
        elif name_lower == 'engineer':
            return SystemEngineerAgent(use_cache=use_cache, user_id=user_id, **kwargs)
            
        elif name_lower == 'sentiment':
            return SentimentAgent(use_cache=use_cache, user_id=user_id, **kwargs)
            
        else:
            raise ValueError(f"Unknown agent type: {agent_name}")


    @staticmethod
    def create_momentum_agent(use_cache=True, user_id="system", **kwargs):
        AgentFactory._configure_dspy()
        # Force Fast Tier
        return MomentumAgent(use_cache=use_cache, tier="fast", user_id=user_id, **kwargs)

    @staticmethod
    def create_fundamental_agent(use_cache=True, user_id="system", **kwargs):
        # Force Smart Tier
        return FundamentalAgent(use_cache=use_cache, tier="smart", user_id=user_id, **kwargs)
        
    @staticmethod
    def create_macro_agent(use_cache=True, user_id="system", **kwargs):
        # Force Smart Tier
        return MacroAgent(use_cache=use_cache, tier="smart", user_id=user_id, **kwargs)

    @staticmethod
    def create_sentiment_agent(use_cache=True, user_id="system", **kwargs):
        # Force Fast Tier
        return SentimentAgent(use_cache=use_cache, tier="fast", user_id=user_id, **kwargs)

    @staticmethod
    def create_cio_agent(use_cache=True, transaction_repo=None, mode="weekly", user_id="system", **kwargs):
        prompt_map = {
            "daily": "prompts/cio_daily.txt",
            "weekly": "prompts/cio_weekly.txt"
        }
        prompt_path = prompt_map.get(mode, "prompts/cio_weekly.txt")
        # Force Smart Tier
        return CIOAgent(use_cache=use_cache, transaction_repo=transaction_repo, prompt_path=prompt_path, tier="smart", user_id=user_id, **kwargs)
