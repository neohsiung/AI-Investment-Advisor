from .base_agent import BaseAgent

class RiskAgent(BaseAgent):
    """
    Risk Agent: Focuses on Portfolio Risk, Volatility (VIX), and Capital Preservation.
    Member of the Agent Council.
    """
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 4
        tier = kwargs.pop('tier', 'fast')
        super().__init__(name="Risk", prompt_path="prompts/risk_agent.txt", use_cache=use_cache, ttl_hours=ttl, tier=tier, **kwargs)

    def run(self, context):
        """
        context: {
            "ticker": "SPY",
            "market_data": { "vix": 25.5, ... },
            "portfolio": { "beta": 1.2, ... }
        }
        """
        # Prepare data for prompt
        # We assume context is a dict that can be passed to prompt renderer
        response = self.run_tool_loop(context=context)
        
        return response
