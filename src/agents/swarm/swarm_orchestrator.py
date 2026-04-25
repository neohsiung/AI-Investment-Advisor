import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Set
from src.utils.logger import setup_logger
from src.agents.base_agent import BaseAgent
from src.repositories.agent_repository import AlchemyAgentRepository
from src.agents.swarm.strategies import (
    AggregationStrategy, ConcatStrategy, MajorityVoteStrategy,
    WeightedVoteStrategy, DegradationChain, VoteResult, get_strategy,
)

logger = setup_logger("SwarmOrchestrator")

class SwarmOrchestrator:
    """
    Unified Sub-Agent Orchestration Framework.
    統一子智能體編排框架。
    
    Responsibilities:
    1. Parallel Dispatch (Fan-out)
    2. Result Aggregation (Fan-in)
    3. Critical Path Monitoring (Simple timeout/retry)
    4. [New] Adaptive Evolution (Reward/Penalty)
    """

    def __init__(self, timeout_seconds: int = 60, reward_delta: float = 0.01, penalty_delta: float = -0.1):
        self.timeout_seconds = timeout_seconds
        self.reward_delta = reward_delta
        self.penalty_delta = penalty_delta
        self.agent_repo = AlchemyAgentRepository()

    async def broadcast(self, agents: List[BaseAgent], task: str, context: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Execute task across multiple agents in parallel.
        在多個 Agent 上並行執行任務。
        """
        if not agents:
            logger.warning("SwarmOrchestrator: No agents provided for broadcast.")
            return {}

        logger.info(f"SwarmOrchestrator: Broadcasting task to {len(agents)} agents: {[a.name for a in agents]}")
        
        tasks = []
        start_time = time.time()
        
        for agent in agents:
            tasks.append(self.run_agent(agent, task, context))
        
        # Execute with timeout
        results = []
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            logger.error("SwarmOrchestrator: Broadcast timed out.")
            # Record timeout failure for all? Or just return error.
            return {a.name: "Error: Timeout" for a in agents}
            
        output = {}
        for agent, res in zip(agents, results):
            latency = time.time() - start_time
            
            if isinstance(res, Exception):
                logger.error(f"SwarmOrchestrator: Agent {agent.name} failed: {res}")
                output[agent.name] = f"Error: {str(res)}"
                self.agent_repo.update_performance(agent.name, "unknown", success=False, latency=latency, weight_delta=self.penalty_delta)
            else:
                output[agent.name] = res
                self.agent_repo.update_performance(agent.name, "unknown", success=True, latency=latency, weight_delta=self.reward_delta)
        
        return output

    async def batch_run(self, agents: List[BaseAgent], tasks: List[str], contexts: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Execute different tasks/contexts across multiple agents in parallel.
        """
        if not agents:
            return {}
            
        logger.info(f"SwarmOrchestrator: Batch run for {len(agents)} agents.")
        
        async_tasks = []
        start_time = time.time()
        
        for agent, task, ctx in zip(agents, tasks, contexts):
            async_tasks.append(self.run_agent(agent, task, ctx))
            
        try:
             results = await asyncio.wait_for(asyncio.gather(*async_tasks, return_exceptions=True), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
             logger.error("SwarmOrchestrator: Batch run timed out.")
             return {a.name: "Error: Timeout" for a in agents}
             
        output = {}
        for agent, res in zip(agents, results):
             latency = time.time() - start_time
             if isinstance(res, Exception):
                 output[agent.name] = f"Error: {str(res)}"
                 self.agent_repo.update_performance(agent.name, "unknown", success=False, latency=latency, weight_delta=self.penalty_delta)
             else:
                 output[agent.name] = res
                 self.agent_repo.update_performance(agent.name, "unknown", success=True, latency=latency, weight_delta=self.reward_delta)
        return output

    async def run_agent(self, agent: BaseAgent, task: str, context: Dict[str, Any]) -> str:
        """
        Execute agent run asynchronously.
        """
        ctx = context.copy() if context else {}
        ctx["user_request"] = task
        return await agent.run(ctx)

    def aggregate_results(self, results: Dict[str, str], strategy: str = "concat", weights: Optional[Dict[str, float]] = None) -> str:
        """
        Aggregate results using pluggable strategy.
        使用可插拔策略聚合結果。

        Args:
            results: Agent name → response text
            strategy: Strategy name ('concat', 'majority_vote', 'weighted_vote')
            weights: Optional agent weights
        """
        kwargs = {}
        if strategy == "weighted_vote":
            kwargs["agent_repo"] = self.agent_repo
        strat = get_strategy(strategy, **kwargs)
        return strat.aggregate(results, weights)

    def run_consensus(self, results: Dict[str, str], weights: Optional[Dict[str, float]] = None) -> VoteResult:
        """
        Run council consensus vote and return structured result.
        執行委員會共識投票並回傳結構化結果。
        """
        strat = MajorityVoteStrategy()
        return strat.vote(results, weights)

    def evaluate_outcome(self, agent_name: str, score: float, tier: str = "unknown"):
        """
        Manual evaluation from higher-level logic.
        score: -1.0 to 1.0
        """
        self.agent_repo.update_performance(
            agent_name=agent_name, 
            tier=tier, 
            success=(score > 0), 
            weight_delta=score * 0.1
        )
    async def run_subtasks(
        self, 
        sub_tasks: List[Any], 
        user_context: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """
        Execute a set of SubTasks, respecting dependencies.
        執行一組 SubTask，並遵守其依賴關係。
        """
        if not sub_tasks:
            return {}

        from src.agents.factory import AgentFactory
        
        results = {}
        pending = {t.id: t for t in sub_tasks}
        completed: Set[str] = set()
        
        # Simple topological sort/execution loop
        while pending:
            # 1. Identity tasks ready to run (no dependencies or all deps completed)
            ready_to_run = [
                t for tid, t in pending.items() 
                if not t.depends_on or all(d in completed for d in t.depends_on)
            ]
            
            if not ready_to_run:
                logger.error(f"SwarmOrchestrator: Circular dependency or missing task detected in {pending.keys()}")
                break
            
            # 2. Run ready tasks in parallel
            logger.info(f"SwarmOrchestrator: Running batch of {len(ready_to_run)} sub-tasks")
            
            async_tasks = []
            task_ids = []
            for t in ready_to_run:
                # Create agent dynamically for the role
                try:
                    agent = AgentFactory.create_agent(t.agent_role, user_id=self.user_id)
                    # Inject results of dependencies into context
                    dep_results = {d: results.get(d, "") for d in t.depends_on}
                    ctx = (user_context or {}).copy()
                    ctx["dependency_results"] = dep_results
                    
                    async_tasks.append(self.run_agent(agent, t.task_description, ctx))
                    task_ids.append(t.id)
                except Exception as e:
                    logger.error(f"SwarmOrchestrator: Failed to create agent for role {t.agent_role}: {e}")
                    results[t.id] = f"Error: Failed to initialize agent role {t.agent_role}"
                    completed.add(t.id)
                    del pending[t.id]

            if async_tasks:
                batch_results = await asyncio.gather(*async_tasks, return_exceptions=True)
                
                for tid, res in zip(task_ids, batch_results):
                    if isinstance(res, Exception):
                        results[tid] = f"Error: {str(res)}"
                    else:
                        results[tid] = res
                    
                    completed.add(tid)
                    del pending[tid]
        
        return results

    def _get_user_id(self) -> str:
        # Helper to get user_id if needed, though usually passed to constructor
        return getattr(self, 'user_id', 'system')
