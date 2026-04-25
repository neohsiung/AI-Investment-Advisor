import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from src.utils.logger import setup_logger
from src.agents.base_agent import BaseAgent
from src.repositories.agent_repository import AlchemyAgentRepository
from src.agents.swarm.strategies import get_strategy

logger = setup_logger("SwarmOrchestrator")

class SwarmOrchestrator:
    """
    v7.0 Multi-Tier Parallel Orchestrator.
    編排 3-Tier (Advanced/Smart/Fast) 並行執行的核心引擎。
    """

    def __init__(
        self, 
        user_id: str = "system",
        timeout_seconds: int = 120,
        fusion_strategy: str = "weighted_vote"
    ):
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds
        self.fusion_strategy = fusion_strategy
        self.agent_repo = AlchemyAgentRepository()

    async def run_parallel_tiers(
        self, 
        tiers: Dict[str, List[BaseAgent]], 
        task: str, 
        context: Dict[str, Any] = None
    ) -> Dict[str, Dict[str, str]]:
        """
        Execute tasks across 3 tiers simultaneously.
        同時在三個層級執行任務。
        """
        logger.info(f"SwarmOrchestrator ({self.user_id}): Dispatching parallel tiers for task: {task[:50]}...")
        
        start_time = time.time()
        
        # Parallel dispatch all tiers
        tier_tasks = {}
        for tier_name, agents in tiers.items():
            if agents:
                tier_tasks[tier_name] = asyncio.create_task(
                    self.broadcast_tier(tier_name, agents, task, context)
                )

        if not tier_tasks:
            logger.warning("No agents available in any tier.")
            return {}

        # Wait for all tiers with global timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tier_tasks.values(), return_exceptions=True),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error("SwarmOrchestrator: Global 3-tier execution timed out.")
            return {name: {"error": "Global Timeout"} for name in tier_tasks}

        # Combine results
        combined_results = {}
        for tier_name, result in zip(tier_tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"SwarmOrchestrator: Tier {tier_name} failed: {result}")
                combined_results[tier_name] = {"error": str(result)}
            else:
                combined_results[tier_name] = result

        latency = time.time() - start_time
        logger.info(f"SwarmOrchestrator: Parallel tiers finished in {latency:.2f}s")
        
        return combined_results

    async def broadcast_tier(
        self, 
        tier_name: str, 
        agents: List[BaseAgent], 
        task: str, 
        context: Dict[str, Any]
    ) -> Dict[str, str]:
        """Broadcast task to agents within a specific tier."""
        logger.debug(f"Broadcasting to {tier_name} Tier ({len(agents)} agents)")
        
        # In a real implementation, we use a separate orchestrator or reuse broadcast logic
        # For v7.0 we'll run them as individual tasks
        tasks = []
        for agent in agents:
            tasks.append(self.run_agent_async(agent, task, context))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        tier_results = {}
        for agent, res in zip(agents, results):
            if isinstance(res, Exception):
                tier_results[agent.name] = f"Error: {res}"
            else:
                tier_results[agent.name] = res
        return tier_results

    async def run_agent_async(self, agent: BaseAgent, task: str, context: Dict[str, Any]) -> str:
        """Run a single agent's logic asynchronously."""
        loop = asyncio.get_event_loop()
        ctx = (context or {}).copy()
        ctx["user_request"] = task
        # BaseAgent.run is typically sync, so we wrap it
        return await loop.run_in_executor(None, agent.run, ctx)

    def fuse_results(
        self, 
        tier_results: Dict[str, Dict[str, str]], 
        strategy: str = None
    ) -> str:
        """
        Fuses results from all tiers into a final decision/summary.
        將三層級的結果匯聚為最終決策。
        """
        strat_name = strategy or self.fusion_strategy
        strat = get_strategy(strat_name, agent_repo=self.agent_repo)
        
        # Flatten all results for the strategy
        flattened = {}
        tier_weights = {
            "Advanced": 1.0, # 🚀
            "Smart": 0.6,    # 🧠
            "Fast": 0.3      # ⚡
        }
        
        final_weights = {}
        
        for tier_name, agents_res in tier_results.items():
            weight_factor = tier_weights.get(tier_name, 0.5)
            for agent_name, response in agents_res.items():
                flattened[agent_name] = response
                # Combine layer weight with agent performance weight
                base_w = self.agent_repo.get_agent_weight(agent_name, default=1.0)
                final_weights[agent_name] = base_w * weight_factor

        return strat.aggregate(flattened, weights=final_weights)
