import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from src.agents.base_agent import BaseAgent
from src.repositories.agent_repository import AgentRepository

logger = logging.getLogger(__name__)

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

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds
        self.agent_repo = AgentRepository()

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
            # For strictness, we can penalize them, but let's keep it simple for now.
            return {a.name: "Error: Timeout" for a in agents}
            
        output = {}
        for agent, res in zip(agents, results):
            latency = time.time() - start_time # Approximate latency for the batch, individual would be better but requires wrapper
            
            if isinstance(res, Exception):
                logger.error(f"SwarmOrchestrator: Agent {agent.name} failed: {res}")
                output[agent.name] = f"Error: {str(res)}"
                # Penalty for crash
                self.agent_repo.update_performance(agent.name, "unknown", success=False, latency=latency, weight_delta=-0.1)
            else:
                output[agent.name] = res
                # Reward for completion (basic)
                # True validation happens in "Fusion" phase which is not here yet.
                # We just record availability here.
                # We reserve weight_delta=0.01 for successful return to encourage activity.
                self.agent_repo.update_performance(agent.name, "unknown", success=True, latency=latency, weight_delta=0.01)
        
        return output

    # Implementation moved to specialized method below to include performance tracking.

    # ... (Keep existing batch_run code but add metrics if possible, or leave as is)
    # Re-implementing batch_run to include metrics:
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
                 self.agent_repo.update_performance(agent.name, "unknown", success=False, latency=latency, weight_delta=-0.1)
             else:
                 output[agent.name] = res
                 self.agent_repo.update_performance(agent.name, "unknown", success=True, latency=latency, weight_delta=0.01)
        return output

    async def run_agent(self, agent: BaseAgent, task: str, context: Dict[str, Any]) -> str:
        """
        Wrapper to run synchronous BaseAgent.run in a thread.
        """
        loop = asyncio.get_event_loop()
        ctx = context.copy() if context else {}
        ctx["user_request"] = task
        return await loop.run_in_executor(None, agent.run, ctx)

    def aggregate_results(self, results: Dict[str, str], strategy: str = "concat") -> str:
        """
        Simple aggregation.
        """
        if strategy == "concat":
            summary = "### Swarm Results\n"
            for name, res in results.items():
                summary += f"#### {name}\n{res}\n\n"
            return summary
        else:
            raise NotImplementedError(f"Strategy {strategy} not implemented")
            
    def evaluate_outcome(self, agent_name: str, score: float, tier: str = "unknown"):
        """
        Manual evaluation from higher-level logic (e.g. RoleSwarm Fusion).
        score: -1.0 to 1.0
        """
        self.agent_repo.update_performance(
            agent_name=agent_name, 
            tier=tier, 
            success=(score > 0), 
            weight_delta=score * 0.1 # Scaling factor
        )
