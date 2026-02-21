from src.utils.logger import setup_logger
logger = setup_logger("RoleSwarm")

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
        Core Swarm Execution Flow (Parallel Dispatch -> Fusion Strategy).
        核心 Swarm 執行流程 (並發派發 -> 融合策略)。
        """
        task = context.get("user_request", "")
        
        # 1. Prepare candidate agents by tier
        fast_candidates = self._select_top_k(self.tiers.get("col_fast", []), k=5)
        smart_candidates = self._select_top_k(self.tiers.get("col_smart", []), k=3)
        adv_candidates = self._select_top_k(self.tiers.get("col_adv", []), k=2)
        
        # 2. Parallel Dispatch using asyncio.create_task
        logger.info(f"RoleSwarm {self.name}: 🚀 Dispatching to Fast({len(fast_candidates)}), Smart({len(smart_candidates)}), Adv({len(adv_candidates)})")
        
        async def run_tier(tier_name, agents, ctx):
            if not agents: return {}
            logger.info(f"RoleSwarm {self.name}: Starting {tier_name} Tier Analysis...")
            return await self.orchestrator.broadcast(agents, task, ctx)
            
        fast_task = asyncio.create_task(run_tier("Fast", fast_candidates, context))
        smart_task = asyncio.create_task(run_tier("Smart", smart_candidates, context))
        adv_task = asyncio.create_task(run_tier("Advanced", adv_candidates, context))
        
        # Phase 1: Await Fast Tier explicitly for Graceful Degradation / Preemption
        fast_results = await fast_task
        fast_summary = self.orchestrator.aggregate_results(fast_results, strategy="concat")
        
        # [Evolution] Graceful Degradation / Override check
        # If Fast Tier (e.g., Risk Agent) detects extreme danger, preempt the rest to save time and compute.
        fast_summary_upper = fast_summary.upper()
        if "CRITICAL DANGER" in fast_summary_upper or "EMERGENCY STOP" in fast_summary_upper or "SYSTEM PAUSE" in fast_summary_upper:
            logger.warning(f"RoleSwarm {self.name}: 🚨 Fast Tier triggered GRACEFUL DEGRADATION. Preempting.")
            smart_task.cancel()
            adv_task.cancel()
            return f"🚨 **EMERGENCY STOP TRIGGERED BY FAST TIER**:\n\n{fast_summary}"
            
        # Phase 2: Wait for Smart and Advanced Tiers (they were already running in the background)
        results = await asyncio.gather(smart_task, adv_task, return_exceptions=True)
        smart_results = results[0] if not isinstance(results[0], Exception) else {}
        adv_results = results[1] if not isinstance(results[1], Exception) else {}
        
        # 3. Fusion Strategy (Aggregate everything)
        final_output = f"## Role Swarm Synthesis: {self.name}\n\n"
        if fast_results:
            final_output += "### 1. ⚡ Fast Tier Insights\n" + fast_summary + "\n"
        if smart_results:
            final_output += "### 2. 🧠 Smart Tier Analysis\n" + self.orchestrator.aggregate_results(smart_results, strategy="concat") + "\n"
        if adv_results:
            final_output += "### 3. 🚀 Advanced Tier Deep Dive\n" + self.orchestrator.aggregate_results(adv_results, strategy="concat") + "\n"
        
        return final_output

    def _select_top_k(self, candidates, k=3):
        """Select top performing agents based on learned weights."""
        if not candidates: 
            return []
        weighted_agents = []
        for agent in candidates:
            # Default to 1.0 if no history
            w = self.orchestrator.agent_repo.get_agent_weight(agent.name, default=1.0)
            weighted_agents.append((w, agent))
            
        # Sort by weight desc
        weighted_agents.sort(key=lambda x: x[0], reverse=True)
        return [a for w, a in weighted_agents[:k]]
