from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.dispatcher import DispatcherAgent
from src.agents.engineer import SystemEngineerAgent

class AgentFactory:
    """
    Factory for creating Agent instances with consistent configuration.
    Supports Dependency Injection and standardizing Cache/TTL settings.
    """
    
    @staticmethod
    def create_agent(agent_name, use_cache=True, **kwargs):
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
            
        else:
            raise ValueError(f"Unknown agent type: {agent_name}")

    @staticmethod
    def create_momentum_agent(use_cache=True, **kwargs):
        return MomentumAgent(use_cache=use_cache, **kwargs)

    @staticmethod
    def create_fundamental_agent(use_cache=True, **kwargs):
        return FundamentalAgent(use_cache=use_cache, **kwargs)
        
    @staticmethod
    def create_macro_agent(use_cache=True, **kwargs):
        return MacroAgent(use_cache=use_cache, **kwargs)

    @staticmethod
    def create_cio_agent(use_cache=True, transaction_repo=None, **kwargs):
        return CIOAgent(use_cache=use_cache, transaction_repo=transaction_repo, **kwargs)
