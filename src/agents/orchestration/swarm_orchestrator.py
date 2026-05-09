import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
import typing
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
        # [PAD Phase 2] BaseAgent.run is now async, so we await it directly
        return await agent.run(ctx)

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

    async def run_subtasks(
        self, 
        sub_tasks: List[Any], 
        user_context: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """
        Execute a set of SubTasks, respecting dependencies (Topological Sort).
        """
        if not sub_tasks:
            return {}

        from src.agents.factory import AgentFactory
        
        results = {}
        pending = {t.id: t for t in sub_tasks}
        completed: typing.Set[str] = set()
        
        while pending:
            ready_to_run = [
                t for tid, t in pending.items() 
                if not t.depends_on or all(d in completed for d in t.depends_on)
            ]
            
            if not ready_to_run:
                logger.error(f"SwarmOrchestrator: Circular dependency detected in {pending.keys()}")
                break
            
            async_tasks = []
            task_ids = []
            for t in ready_to_run:
                try:
                    agent = AgentFactory.create_agent(t.agent_role, user_id=self.user_id)
                    dep_results = {d: results.get(d, "") for d in t.depends_on}
                    ctx = (user_context or {}).copy()
                    ctx["dependency_results"] = dep_results
                    async_tasks.append(self.run_agent_async(agent, t.task_description, ctx))
                    task_ids.append(t.id)
                except Exception as e:
                    logger.error(f"SwarmOrchestrator: Failed to create agent for role {t.agent_role}: {e}")
                    results[t.id] = f"Error: {e}"
                    completed.add(t.id)
                    del pending[t.id]

            if async_tasks:
                batch_results = await asyncio.gather(*async_tasks, return_exceptions=True)
                for tid, res in zip(task_ids, batch_results):
                    results[tid] = str(res) if not isinstance(res, Exception) else f"Error: {res}"
                    completed.add(tid)
                    del pending[tid]
        
        return results

    def update_performance(self, agent_name: str, success: bool, latency: float, weight_delta: float):
        """Update agent performance in the repository."""
        self.agent_repo.update_performance(agent_name, "unknown", success=success, latency=latency, weight_delta=weight_delta)

    # --- Legacy Aliases ---
    async def broadcast(self, agents: List[BaseAgent], task: str, context: Dict[str, Any]) -> Dict[str, str]:
        """Legacy alias for broadcast_tier."""
        return await self.broadcast_tier("General", agents, task, context)

    async def batch_run(self, agents: List[BaseAgent], tasks: List[str], contexts: List[Dict[str, Any]]) -> Dict[str, str]:
        """Legacy alias for batch execution."""
        logger.info(f"SwarmOrchestrator: Batch running {len(agents)} agents...")
        async_tasks = []
        for agent, task, ctx in zip(agents, tasks, contexts):
            async_tasks.append(self.run_agent_async(agent, task, ctx))
        results = await asyncio.gather(*async_tasks, return_exceptions=True)
        batch_results = {}
        for agent, res in zip(agents, results):
            batch_results[agent.name] = str(res) if not isinstance(res, Exception) else f"Error: {res}"
        return batch_results

    def aggregate_results(self, results: Dict[str, str], strategy: str = "concat") -> str:
        """Legacy alias for fuse_results."""
        return self.fuse_results({"General": results}, strategy=strategy)

    async def map_reduce(
        self, 
        items: List[Any], 
        map_role: str,
        reduce_role: str,
        map_context_builder: Callable[[Any], Dict[str, Any]],
        reduce_context_builder: Callable[[Dict[str, str]], Dict[str, Any]],
        tier: str = "fast"
    ) -> str:
        """
        Generic Map-Reduce implementation for agent swarms.
        """
        logger.info(f"SwarmOrchestrator: Starting Map-Reduce ({len(items)} items)")
        
        # 1. Map Phase
        map_tasks = []
        for item in items:
            sub_ctx = map_context_builder(item)
            from src.agents.factory import AgentFactory
            agent = AgentFactory.create_agent(map_role, user_id=self.user_id)
            map_tasks.append(self.run_agent_async(agent, "Map Analysis", sub_ctx))
        
        map_results_list = await asyncio.gather(*map_tasks, return_exceptions=True)
        
        # Collect results
        map_results_dict = {}
        for i, res in enumerate(map_results_list):
            item_key = str(items[i]) # Basic key
            map_results_dict[item_key] = str(res) if not isinstance(res, Exception) else f"Error: {res}"
            
        # 2. Reduce Phase
        reduce_ctx = reduce_context_builder(map_results_dict)
        from src.agents.factory import AgentFactory
        reducer = AgentFactory.create_agent(reduce_role, user_id=self.user_id)
        
        logger.info("SwarmOrchestrator: Map phase complete. Starting Reduce phase.")
        return await reducer.run(reduce_ctx)
