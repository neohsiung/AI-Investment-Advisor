import asyncio
import logging
from typing import List, Dict, Any, Optional
from src.agents.base_agent import BaseAgent
from src.agents.swarm.swarm_orchestrator import SwarmOrchestrator

logger = logging.getLogger(__name__)

class RoleSwarm(BaseAgent):
    """
    Role-Based Swarm Agent (e.g., FundamentalSwarm, MarketSwarm).
    Manages a tiered fleet of micro-agents to execute tasks with adaptive compute.
    角色基礎 Swarm Agent (例如: 基本面 Swarm, 市場 Swarm)。
    管理分層的微型 Agent 用於自適應計算執行任務。
    """

    def __init__(
        self, 
        name: str, 
        user_id: str = "system", 
        prompt_path: str = None, 
        **kwargs
    ):
        # Initialize BaseAgent with dummy prompt if not provided, 
        # as Swarm logic is code-driven, though it might use LLM for synthesis.
        super().__init__(name=name, user_id=user_id, prompt_path=prompt_path or "prompts/common/default_system.j2", **kwargs)
        
        self.orchestrator = SwarmOrchestrator()
        self.tiers: Dict[str, List[BaseAgent]] = {
            "col_fast": [],     # ⚡ High speed, low cost (Search, Scan)
            "col_smart": [],    # 🧠 Balanced (Reasoning, Synthesis)
            "col_adv": []       # 🚀 High intelligence (Deep Dive, Complex Logic)
        }

    def register_agent(self, tier: str, agent: BaseAgent):
        """
        Register a micro-agent to a specific tier.
        """
        if tier in self.tiers:
            self.tiers[tier].append(agent)
            logger.info(f"RoleSwarm {self.name}: Registered {agent.name} to {tier}")
        else:
            logger.warning(f"RoleSwarm {self.name}: Invalid tier {tier}")

    def run(self, context: Any) -> str:
        """
        Execute Swarm Logic (Sync Wrapper).
        """
        # Get existing loop or create new
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            # If already in async loop (e.g. from FastAPI or another agent), 
            # we should return a Future or handle appropriately.
            # But BaseAgent.run is designed to return str.
            # This is a known architectural bridge issue. 
            # ideally BaseAgent should be async.
            # For now, we assume we are at top level or threaded.
            # Use run_coroutine_threadsafe if in another thread, 
            # or strictly rely on nest_asyncio if strictly needed.
            # SIMPLEST MVP: create a new task if valid, but we need return value.
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(self._run_async(context))
        else:
            return loop.run_until_complete(self._run_async(context))

    async def _run_async(self, context: Any) -> str:
        """
        Core Swarm Execution Flow (Breadth-First -> Selection -> Depth-First).
        核心 Swarm 執行流程 (廣度優先 -> 篩選 -> 深度優先)。
        """
        task = context.get("user_request", "")
        # 1. Breadth-First: Fan-out to Fast Tier
        # 廣度優先：分發至 Fast Tier
        candidates = self.tiers["col_fast"]
        
        if candidates:
            # [Evolution] Adaptive Selection
            # Sort candidates by weight (descending)
            weighted_agents = []
            for agent in candidates:
                w = self.orchestrator.agent_repo.get_agent_weight(agent.name, default=1.0)
                weighted_agents.append((w, agent))
            
            # Sort by weight desc
            weighted_agents.sort(key=lambda x: x[0], reverse=True)
            
            # Select Top K (e.g., Top 5 or all if fewer)
            top_k = 5
            selected_agents = [a for w, a in weighted_agents[:top_k]]
            
            logger.info(f"RoleSwarm {self.name}: ⚡ Fast Tier Scan ({len(selected_agents)}/{len(candidates)} agents)...")
            logger.debug(f"Selected Agents: {[(a.name, w) for w, a in weighted_agents[:top_k]]}")
            
            fast_results = await self.orchestrator.broadcast(selected_agents, task, context)
            
            # TODO: Implement Selection / Filtering Logic here
            # For MVP, we aggregate and pass to Smart Tier if exists, or return.
            
            summary = self.orchestrator.aggregate_results(fast_results)
        else:
            summary = "No Fast Tier agents registered."

        # 2. Depth-First: Drill-down with Smart Tier (if needed/configured)
        # 深度優先：使用 Smart Tier 進行深入分析
        smart_agents = self.tiers["col_smart"]
        if smart_agents:
            logger.info(f"RoleSwarm {self.name}: 🧠 Smart Tier Analysis ({len(smart_agents)} agents)...")
            
            # Inject fast tier results into context for smart tier
            drill_context = context.copy() if isinstance(context, dict) else {}
            drill_context["preliminary_insights"] = summary
            
            smart_results = await self.orchestrator.broadcast(smart_agents, task, drill_context)
            final_output = self.orchestrator.aggregate_results(smart_results)
        else:
            final_output = summary

        # 3. Final Synthesis (Optional: Use Orchestrator LLM)
        # For now return the aggregated result.
        
        return final_output
