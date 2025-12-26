from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.dispatcher import DispatcherAgent
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
        """Enable DSPy if installed and credentials are present."""
        if cls._dspy_configured or not has_dspy:
            return

        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        model = os.getenv("LLM_MODEL_SMART", "google/gemini-2.0-flash-exp")

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
            logger.warning("DSPy installed but LLM_API_KEY missing.")

    @staticmethod
    def create_agent(agent_name, use_cache=True, **kwargs):
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
            return MomentumAgent(use_cache=use_cache, **kwargs)
            
        elif name_lower == 'fundamental':
            return FundamentalAgent(use_cache=use_cache, **kwargs)
            
        elif name_lower == 'macro':
            return MacroAgent(use_cache=use_cache, **kwargs)
            
        elif name_lower == 'cio':
            # CIO might need repositories injected via kwargs
            return CIOAgent(use_cache=use_cache, **kwargs)
            
        elif name_lower == 'dispatcher':
            return DispatcherAgent(use_cache=use_cache, **kwargs)
        
        elif name_lower == 'engineer':
            return SystemEngineerAgent(use_cache=use_cache, **kwargs)
            
        elif name_lower == 'sentiment':
            return SentimentAgent(use_cache=use_cache, **kwargs)
            
        else:
            raise ValueError(f"Unknown agent type: {agent_name}")


    @staticmethod
    def create_momentum_agent(use_cache=True, **kwargs):
        AgentFactory._configure_dspy()
        return MomentumAgent(use_cache=use_cache, **kwargs)

    @staticmethod
    def create_fundamental_agent(use_cache=True, **kwargs):
        return FundamentalAgent(use_cache=use_cache, **kwargs)
        
    @staticmethod
    def create_macro_agent(use_cache=True, **kwargs):
        return MacroAgent(use_cache=use_cache, **kwargs)

    @staticmethod
    def create_sentiment_agent(use_cache=True, **kwargs):
        return SentimentAgent(use_cache=use_cache, **kwargs)

    @staticmethod
    def create_cio_agent(use_cache=True, transaction_repo=None, mode="weekly", **kwargs):
        prompt_map = {
            "daily": "prompts/cio_daily.txt",
            "weekly": "prompts/cio_weekly.txt"
        }
        prompt_path = prompt_map.get(mode, "prompts/cio_weekly.txt")
        return CIOAgent(use_cache=use_cache, transaction_repo=transaction_repo, prompt_path=prompt_path, **kwargs)
