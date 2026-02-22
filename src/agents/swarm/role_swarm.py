import asyncio
from typing import Any, Dict, List
from src.utils.logger import setup_logger
from src.agents.base_agent import BaseAgent
from .swarm_orchestrator import SwarmOrchestrator

logger = setup_logger("RoleSwarm")

class RoleSwarm(BaseAgent):
    """
    Role-Based Swarm Agent (e.g., FundamentalSwarm, MarketSwarm).
    Manages a tiered fleet of micro-agents to execute tasks with adaptive compute.
    """

    def __init__(
        self, 
        name: str, 
        user_id: str = "system", 
        prompt_path: str = None, 
        **kwargs
    ):
        super().__init__(name=name, user_id=user_id, prompt_path=prompt_path or "prompts/common/default_system.j2", **kwargs)
        
        self.orchestrator = SwarmOrchestrator()
        self.tiers: Dict[str, List[BaseAgent]] = {
            "col_fast": [],     # ⚡ High speed, low cost
            "col_smart": [],    # 🧠 Balanced
            "col_adv": []       # 🚀 High intelligence
        }

    def register_agent(self, tier: str, agent: BaseAgent):
        if tier in self.tiers:
            self.tiers[tier].append(agent)
            logger.info(f"RoleSwarm {self.name}: Registered {agent.name} to {tier}")
        else:
            logger.warning(f"RoleSwarm {self.name}: Invalid tier {tier}")

    def run(self, context: Any) -> str:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(self._run_async(context))
        else:
            return loop.run_until_complete(self._run_async(context))

    async def _run_async(self, context: Any) -> str:
        task = context.get("user_request", "")
        
        fast_candidates = self._select_top_k(self.tiers.get("col_fast", []), k=5)
        smart_candidates = self._select_top_k(self.tiers.get("col_smart", []), k=3)
        adv_candidates = self._select_top_k(self.tiers.get("col_adv", []), k=2)
        
        logger.info(f"RoleSwarm {self.name}: 🚀 Dispatching to Fast({len(fast_candidates)}), Smart({len(smart_candidates)}), Adv({len(adv_candidates)})")
        
        async def run_tier(tier_name, agents, ctx):
            if not agents: return {}
            logger.info(f"RoleSwarm {self.name}: Starting {tier_name} Tier Analysis...")
            return await self.orchestrator.broadcast(agents, task, ctx)
            
        fast_task = asyncio.create_task(run_tier("Fast", fast_candidates, context))
        smart_task = asyncio.create_task(run_tier("Smart", smart_candidates, context))
        adv_task = asyncio.create_task(run_tier("Advanced", adv_candidates, context))
        
        fast_results = await fast_task
        fast_summary = self.orchestrator.aggregate_results(fast_results, strategy="concat")
        
        fast_summary_upper = fast_summary.upper()
        if "CRITICAL DANGER" in fast_summary_upper or "EMERGENCY STOP" in fast_summary_upper or "SYSTEM PAUSE" in fast_summary_upper:
            logger.warning(f"RoleSwarm {self.name}: 🚨 Fast Tier triggered GRACEFUL DEGRADATION. Preempting.")
            smart_task.cancel()
            adv_task.cancel()
            return f"🚨 **EMERGENCY STOP TRIGGERED BY FAST TIER**:\n\n{fast_summary}"
            
        results = await asyncio.gather(smart_task, adv_task, return_exceptions=True)
        smart_results = results[0] if not isinstance(results[0], Exception) else {}
        adv_results = results[1] if not isinstance(results[1], Exception) else {}
        
        final_output = f"## Role Swarm Synthesis: {self.name}\n\n"
        if fast_results:
            final_output += "### 1. ⚡ Fast Tier Insights\n" + fast_summary + "\n"
        if smart_results:
            final_output += "### 2. 🧠 Smart Tier Analysis\n" + self.orchestrator.aggregate_results(smart_results, strategy="concat") + "\n"
        if adv_results:
            final_output += "### 3. 🚀 Advanced Tier Deep Dive\n" + self.orchestrator.aggregate_results(adv_results, strategy="concat") + "\n"
        
        return final_output

    def _select_top_k(self, candidates, k=3):
        if not candidates: 
            return []
        weighted_agents = []
        for agent in candidates:
            w = self.orchestrator.agent_repo.get_agent_weight(agent.name, default=1.0)
            weighted_agents.append((w, agent))
            
        weighted_agents.sort(key=lambda x: x[0], reverse=True)
        return [a for w, a in weighted_agents[:k]]
