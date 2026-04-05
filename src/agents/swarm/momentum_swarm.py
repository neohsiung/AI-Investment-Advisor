import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Any
from src.utils.logger import setup_logger
from src.agents.base_agent import BaseAgent
from .role_swarm import RoleSwarm

logger = setup_logger("MomentumSwarm")

class MomentumScanner(BaseAgent):
    """
    Fast Tier Agent for Technical/Momentum Scanning.
    Analyzes price action and indicators for a single ticker.
    """
    def __init__(self, user_id, **kwargs):
        kwargs.pop('tier', None)
        super().__init__(
            name="MomentumScanner", 
            prompt_path="prompts/momentum_agent.txt", 
            tier="fast", 
            user_id=user_id, 
            **kwargs
        )
        
    async def run(self, context):
        return await self.run_tool_loop(context)

class MomentumSwarm(RoleSwarm):
    """
    Momentum Analysis Swarm.
    """
    def __init__(self, user_id: str = None, **kwargs):
        if not user_id:
            raise ValueError("MomentumSwarm: user_id is required.")
        super().__init__(name="MomentumSwarm", user_id=user_id, tier="fast", **kwargs)
        
        # Register default pool
        for _ in range(3):
            self.register_agent("col_fast", MomentumScanner(user_id=user_id))
            
    async def _run_async(self, context: Any) -> str:
        tickers = context.get("tickers", [])
        ticker = context.get("ticker")
        
        if ticker and ticker != "UNKNOWN":
            tickers = [ticker]
            
        if not tickers:
            return "No tickers provided for Momentum Analysis."
            
        market_data = context.get("market_data", {})
        
        adhoc_agents = []
        tasks_list = []
        contexts_list = []
        
        for t in tickers:
            agent = MomentumScanner(user_id=self.user_id)
            agent.name = f"Momentum_{t}"
            adhoc_agents.append(agent)
            
            t_data = market_data.get(t, {})
            price_data = t_data.get("price_data", {})
            indicators = t_data.get("indicators", {})
            
            sub_context = {
                "ticker": t,
                "price_data": json.dumps(price_data, indent=2, ensure_ascii=False),
                "indicators": json.dumps(indicators, indent=2, ensure_ascii=False),
                "user_request": f"Analyze technical momentum for {t}"
            }
            
            tasks_list.append(sub_context["user_request"])
            contexts_list.append(sub_context)
            
        logger.info(f"MomentumSwarm: ⚡ Scanning {len(tickers)} tickers...")
        results_dict = await self.orchestrator.batch_run(adhoc_agents, tasks_list, contexts_list)
        return self.orchestrator.aggregate_results(results_dict)
