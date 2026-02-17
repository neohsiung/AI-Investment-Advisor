import json
import logging
import asyncio
from typing import Any, List, Dict
from src.agents.swarm.role_swarm import RoleSwarm
from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class MomentumScanner(BaseAgent):
    """
    Fast Tier Agent for Technical/Momentum Scanning.
    Analyzes price action and indicators for a single ticker.
    """
    def __init__(self, user_id="system", **kwargs):
        kwargs.pop('tier', None)
        super().__init__(
            name="MomentumScanner", 
            prompt_path="prompts/momentum_agent.txt", 
            tier="fast", 
            user_id=user_id, 
            **kwargs
        )
        
    def run(self, context):
        """
        Expects context with 'ticker', 'price_data', 'indicators'.
        """
        return self.run_tool_loop(context)

class MomentumSwarm(RoleSwarm):
    """
    Momentum Analysis Swarm.
    Parallel processing of technical indicators using Fast Tier agents.
    """
    def __init__(self, user_id: str = "system", **kwargs):
        super().__init__(name="MomentumSwarm", user_id=user_id, tier="fast", **kwargs)
        
        # Register default pool
        for _ in range(3):
            self.register_agent("col_fast", MomentumScanner(user_id=user_id))
            
    async def _run_async(self, context: Any) -> str:
        """
        Batch process technical analysis for multiple tickers.
        """
        tickers = context.get("tickers", [])
        ticker = context.get("ticker")
        
        if ticker and ticker != "UNKNOWN":
            tickers = [ticker]
            
        if not tickers:
            return "No tickers provided for Momentum Analysis."
            
        market_data = context.get("market_data", {})
        
        # Dynamic creation of scanners
        adhoc_agents = []
        tasks_list = []
        contexts_list = []
        
        for t in tickers:
            agent = MomentumScanner(user_id=self.user_id)
            agent.name = f"Momentum_{t}"
            adhoc_agents.append(agent)
            
            # Prepare context
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
        
        # Batch Run
        results_dict = await self.orchestrator.batch_run(adhoc_agents, tasks_list, contexts_list)
        
        # Aggregate
        summary = self.orchestrator.aggregate_results(results_dict)
        
        return summary
