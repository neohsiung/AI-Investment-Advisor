import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import create_engine

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_adaptive_swarm():
    print("--- Adaptive Swarm Verification ---")
    
    # 1. Setup In-Memory DB for Testing
    test_engine = create_engine("sqlite:///:memory:")
    
    # Patch get_db_engine to return our test engine
    with patch("src.data.database.get_db_engine", return_value=test_engine), \
         patch("src.agents.base_agent.BaseAgent._load_prompt", return_value="Mock Prompt"):
        
        from src.data.agent_repository import AgentRepository
        from src.agents.swarm.role_swarm import RoleSwarm
        from src.agents.base_agent import BaseAgent
        
        # Initialize Repo & Table
        repo = AgentRepository()
        
        # 2. Seed Agents with different weights
        # Agent A: High Performer
        repo.update_performance("Agent_A", "col_fast", success=True, weight_delta=0.5) # Weight -> 1.5
        repo.update_performance("Agent_A", "col_fast", success=True, weight_delta=0.0) # Ensure it exists
        
        # Agent B: Average
        repo.update_performance("Agent_B", "col_fast", success=True, weight_delta=0.0) # Weight -> 1.0
        
        # Agent C: Low Performer
        repo.update_performance("Agent_C", "col_fast", success=False, weight_delta=-0.5) # Weight -> 0.5
        
        print("\n[State] Initial Weights:")
        print(f"Agent_A: {repo.get_agent_weight('Agent_A')}")
        print(f"Agent_B: {repo.get_agent_weight('Agent_B')}")
        print(f"Agent_C: {repo.get_agent_weight('Agent_C')}")
        
        # 3. Setup RoleSwarm
        swarm = RoleSwarm(name="TestSwarm")
        
        class DummyAgent(BaseAgent):
            def run(self, context):
                return "Mock Result"

        # Create Dummy Agents
        a = DummyAgent(name="Agent_A", user_id="test", prompt_path="dummy")
        b = DummyAgent(name="Agent_B", user_id="test", prompt_path="dummy")
        c = DummyAgent(name="Agent_C", user_id="test", prompt_path="dummy")
        
        # Mock run method
        a.run = MagicMock(return_value="Result A")
        b.run = MagicMock(return_value="Result B")
        c.run = MagicMock(return_value="Result C")
        
        swarm.register_agent("col_fast", a)
        swarm.register_agent("col_fast", b)
        swarm.register_agent("col_fast", c)
        
        # 4. Verify Selection Logic (Top 2)
        # We need to hack the top_k in RoleSwarm for this test or just see order
        # RoleSwarm defaults to Top 5. Since we have 3, all should be selected but SORTED.
        
        print("\n[Test] Execution Order (Broadcast)")
        # We mock orchestrator.broadcast to inspect the 'agents' list passed to it
        original_broadcast = swarm.orchestrator.broadcast
        swarm.orchestrator.broadcast = AsyncMock(return_value={"Agent_A": "Res A", "Agent_B": "Res B", "Agent_C": "Res C"})
        
        await swarm._run_async({"user_request": "Test Task"})
        
        # Check arguments passed to broadcast
        call_args = swarm.orchestrator.broadcast.call_args
        selected_agents = call_args[0][0] # First arg is agents list
        
        print(f"Selected Agents Order: {[ag.name for ag in selected_agents]}")
        
        if selected_agents[0].name == "Agent_A" and selected_agents[-1].name == "Agent_C":
            print("✅ Selection sorted by weight desc.")
        else:
            print("❌ Selection order incorrect.")
            
        # 5. Verify Metrics Update (Orchestrator Level)
        # Reset orchestrated to use real logic (but mocked run_agent)
        swarm.orchestrator.broadcast = original_broadcast
        swarm.orchestrator.run_agent = AsyncMock(return_value="Success")
        
        print("\n[Test] Metrics Update")
        # Agent C fails (Simulate by mocking run_agent side effect? 
        # Actually broadcast catches exceptions. Let's make Agent C raise exception)
        
        async def mock_run_agent(agent, task, context):
            if agent.name == "Agent_C":
                raise Exception("Simulated Crash")
            return "Success"
            
        swarm.orchestrator.run_agent = mock_run_agent
        
        await swarm._run_async({"user_request": "Test Task 2"})
        
        # Check Repo again
        w_a = repo.get_agent_weight("Agent_A")
        w_c = repo.get_agent_weight("Agent_C")
        
        print(f"Agent_A New Weight: {w_a} (Expected > 1.5)")
        print(f"Agent_C New Weight: {w_c} (Expected < 0.5)")
        
        if w_a > 1.5 and w_c < 0.5:
            print("✅ Reward/Penalty applied successfully.")
        else:
            print("❌ Weights did not change as expected.")

if __name__ == "__main__":
    asyncio.run(verify_adaptive_swarm())
