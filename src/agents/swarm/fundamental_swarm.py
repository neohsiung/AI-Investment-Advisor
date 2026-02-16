import json
import asyncio
from typing import Any, List, Dict
from src.agents.swarm.role_swarm import RoleSwarm
from src.agents.base_agent import BaseAgent
import logging

logger = logging.getLogger(__name__)

class FundamentalScanner(BaseAgent):
    """
    Fast Tier Agent for quick financial scanning.
    """
    def __init__(self, user_id="system", **kwargs):
        # Use a simplified prompt or the same one with Flash model
        super().__init__(
            name="FundamentalScanner", 
            prompt_path="prompts/fundamental_agent.txt", # Refine pointer later
            tier="fast", 
            user_id=user_id, 
            **kwargs
        )
        
    def run(self, context):
        # Specific wrapper if needed or just inherit BaseAgent.run
        return self.run_tool_loop(context)

class FundamentalAnalyst(BaseAgent):
    """
    Smart Tier Agent for deep dive.
    """
    def __init__(self, user_id="system", **kwargs):
        super().__init__(
            name="FundamentalAnalyst", 
            prompt_path="prompts/fundamental_agent.txt", 
            tier="smart", 
            user_id=user_id, 
            **kwargs
        )

    def run(self, context):
        return self.run_tool_loop(context)

class FundamentalSwarm(RoleSwarm):
    """
    Fundamental Analysis Swarm.
    Parallel processing of tickers using Fast/Smart tiers.
    """
    def __init__(self, user_id: str = "system", **kwargs):
        super().__init__(name="FundamentalSwarm", user_id=user_id, **kwargs)
        
        # Pre-register some agents? 
        # Actually for Swarm, we might want dynamic instantiation per task to avoid state pollution.
        # But RoleSwarm expects self.tiers to be populated.
        # Let's populate a default pool.
        for _ in range(3): # Minimum 3 agents
            self.register_agent("col_fast", FundamentalScanner(user_id=user_id))
            
        self.register_agent("col_smart", FundamentalAnalyst(user_id=user_id))
        
    async def _run_async(self, context: Any) -> str:
        """
        Specialized flow for Fundamental Analysis.
        Handles 'tickers' list for batch processing.
        """
        tickers = context.get("tickers", [])
        ticker = context.get("ticker")
        
        if ticker and ticker != "UNKNOWN":
            tickers = [ticker]
            
        if not tickers:
            return "No tickers provided."
            
        # Dynamic Scaling: If more tickers than agents, expand pool or queue.
        # For this MVP, we create a temporary fleet if needed or reuse pool.
        # Since BaseAgent is stateful (history), we should create FRESH agents for each ticker 
        # to ensure isolation, OR clear history.
        # Optimized: Create lightweight ad-hoc agents.
        
        adhoc_fast_agents = []
        for t in tickers:
            # Create a dedicated scanner for this ticker
            agent = FundamentalScanner(user_id=self.user_id)
            agent.name = f"Scanner_{t}"
            adhoc_fast_agents.append(agent)
            
        # Fan-out
        logger.info(f"FundamentalSwarm: ⚡ Scanning {len(tickers)} tickers in parallel...")
        
        # We need to map tasks to agents.
        # Orchestrator.broadcast sends SAME task to all agents? Spec check.
        # BaseAgent.run(context). context["user_request"] is the task.
        # But each agent needs specific context (Ticker Data).
        # SwarmOrchestrator._run_single_agent copies context.
        # We need to pass DIFFERENT context to each agent.
        
        # Overriding Orchestrator broadcast for specific mapped contexts?
        # Or loop here using orchestrator helper?
        
        tasks_list = []
        contexts_list = []
        market_data = context.get("market_data", {})
        
        for t in tickers:
            # Prepare specific context
            t_data = market_data.get(t, {})
            fin = t_data.get("financials", {})
            news = t_data.get("news", [])
            
            sub_context = {
                "ticker": t,
                "financials": json.dumps(fin, indent=2, ensure_ascii=False),
                "news": json.dumps(news, indent=2, ensure_ascii=False),
                "user_request": f"Analyze fundamental data for {t}"
            }
            tasks_list.append(sub_context["user_request"])
            contexts_list.append(sub_context)
            
        # Execute Batch Run
        results_dict = await self.orchestrator.batch_run(adhoc_fast_agents, tasks_list, contexts_list)
                
        # Aggregate
        summary = self.orchestrator.aggregate_results(results_dict)
        
        # Depth-First: Check if any analysis requires Deep Dive (e.g. if Scanner was unsure)
        # For MVP, just return summary of Fast Tier (which is 'Analyze' with generic prompt).
        
        return summary
