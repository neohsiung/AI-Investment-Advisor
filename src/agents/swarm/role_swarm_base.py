from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.agents.base_agent import BaseAgent
from src.agents.orchestration.swarm_orchestrator import SwarmOrchestrator
from src.utils.logger import setup_logger

logger = setup_logger("RoleSwarmBase")

class RoleSwarmBase(BaseAgent, ABC):
    """
    v7.0 Role × Multi-Tier Swarm Base Class.
    智能體集群基底類別：負責將任務 Fan-out 到不同層級並匯聚結果。
    """

    def __init__(self, name: str, user_id: str, prompt_path: str = None, **kwargs):
        super().__init__(
            name=name, 
            user_id=user_id, 
            prompt_path=prompt_path or "prompts/common/default_system.j2", 
            **kwargs
        )
        self.orchestrator = SwarmOrchestrator(user_id=user_id)
        
        # 3-Tier Registry
        self.advanced_agents: List[BaseAgent] = [] # 🚀 Strategic (Opus/Gemini Pro)
        self.smart_agents: List[BaseAgent] = []    # 🧠 Analytical (GPT-4/Gemini Pro)
        self.fast_agents: List[BaseAgent] = []     # ⚡ Operational (Flash/GPT-3.5)

    def register_sub_agent(self, tier: str, agent: BaseAgent):
        """Register a sub-agent to a specific tier."""
        tier = tier.lower()
        if tier == "advanced" or tier == "adv":
            self.advanced_agents.append(agent)
        elif tier == "smart":
            self.smart_agents.append(agent)
        elif tier == "fast":
            self.fast_agents.append(agent)
        else:
            logger.warning(f"{self.name}: Unknown tier '{tier}' for sub-agent {agent.name}")
        
        logger.info(f"{self.name}: Registered {agent.name} to {tier} tier.")

    async def run_swarm(self, context: Any) -> str:
        """
        Execute the swarm logic: Parallel Fan-out + Fusion Fan-in.
        """
        task = context.get("user_request", "Analyze current context.")
        
        tiers = {
            "Advanced": self.advanced_agents,
            "Smart": self.smart_agents,
            "Fast": self.fast_agents
        }
        
        # 1. Dispatch Parallel Tiers
        tier_results = await self.orchestrator.run_parallel_tiers(tiers, task, context)
        
        # 2. Fuse Results (Fan-in)
        final_summary = self.orchestrator.fuse_results(tier_results)
        
        return final_summary

    @abstractmethod
    def run(self, context: Any) -> str:
        """
        Inherited agents must implement run, usually just calling await run_swarm.
        """
        pass
