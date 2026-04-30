"""
Agent Tier Mapping Loader
Load agent → tier mappings from config/agent_tier_mapping.yaml
"""

import yaml
import os
from typing import Dict, Optional

class AgentTierMappingLoader:
    """Load and provide agent-to-tier mappings."""
    
    _cache = None
    
    @classmethod
    def load(cls) -> Dict:
        """Load agent tier mapping from YAML."""
        if cls._cache is not None:
            return cls._cache
            
        # Try multiple possible paths
        possible_paths = [
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "config", "agent_tier_mapping.yaml"
            ),
            "config/agent_tier_mapping.yaml",
            "/workspace/config/agent_tier_mapping.yaml",
        ]
        
        config_path = None
        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break
        
        if not config_path:
            raise FileNotFoundError(f"Agent tier mapping config not found. Tried: {possible_paths}")
            
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            
        cls._cache = config
        return config
    
    @classmethod
    def get_agent_tier(cls, agent_name: str) -> str:
        """Get the assigned tier for an agent."""
        config = cls.load()
        agent_key = agent_name.lower().replace(" ", "_")
        
        if agent_key not in config.get("agents", {}):
            # Default fallback
            return "smart"
            
        return config["agents"][agent_key].get("tier", "smart")
    
    @classmethod
    def get_all_agents_by_tier(cls, tier: str) -> list:
        """Get all agents assigned to a specific tier."""
        config = cls.load()
        agents = []
        
        for agent_key, agent_cfg in config.get("agents", {}).items():
            if agent_cfg.get("tier") == tier:
                agents.append(agent_key)
                
        return agents


if __name__ == "__main__":
    # Test loading
    loader = AgentTierMappingLoader()
    print("Loaded agent tier mappings:")
    config = loader.load()
    
    for agent, cfg in config.get("agents", {}).items():
        print(f"  {agent}: {cfg.get('tier')}")
    
    print("\nAgents by tier:")
    for tier in ["nano", "fast", "smart", "advanced"]:
        agents = loader.get_all_agents_by_tier(tier)
        print(f"  {tier}: {agents}")
