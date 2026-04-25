import asyncio
import time
from src.agents.swarm.role_swarm import RoleSwarm
from src.agents.base_agent import BaseAgent

class DummyAgent(BaseAgent):
    def __init__(self, name, delay=1.0, result_text=""):
        # BaseAgent requires prompt_path, we'll provide a dummy
        import os
        dummy_path = "dummy_prompt.txt"
        if not os.path.exists(dummy_path):
            with open(dummy_path, "w") as f: f.write("dummy")
            
        super().__init__(name=name, user_id="test_user", prompt_path=dummy_path, use_cache=False)
        self.delay = delay
        self.result_text = result_text

    async def run(self, context):
        # We simulate blocking or async logic. Since BaseAgent is sync, it runs in thread executor
        await asyncio.sleep(self.delay)
        return self.result_text

import pytest

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_swarm_concurrency():
    swarm = RoleSwarm(name="TestSwarm", user_id="test_user")
    
    # 1. Register Fast Tier (Takes 1 second)
    fast_agent = DummyAgent("FastRisk", delay=1.0, result_text="⚠️ SYSTEM PAUSE: Market Crash Detected!")
    swarm.register_agent("col_fast", fast_agent)
    
    # 2. Register Smart Tier (Takes 3 seconds)
    smart_agent = DummyAgent("SmartFund", delay=3.0, result_text="Company A looks solid but market is volatile.")
    swarm.register_agent("col_smart", smart_agent)
    
    # 3. Register Advanced Tier (Takes 5 seconds)
    adv_agent = DummyAgent("AdvQuant", delay=5.0, result_text="Deep quantitative analysis confirms long signal.")
    swarm.register_agent("col_adv", adv_agent)
    
    print("Testing Preemption Logic...")
    start_time = time.time()
    
    # This should return in ~1 second due to Fast Tier returning SYSTEM PAUSE
    result = await swarm.run({"user_request": "Analyze market"})
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\nExecution Duration: {duration:.2f} seconds")
    print("Result Summary:")
    print(result)
    
    assert duration < 2.0, "Execution took too long! Preemption failed or parallelization failed."
    assert "EMERGENCY STOP TRIGGERED BY FAST TIER" in result
    print("✅ Preemption Test Passed!\n")
    
    # --- Test 2: Full Concurrency ---
    print("Testing Full Parallel Concurrency (Expected ~5s)...")
    swarm2 = RoleSwarm("TestSwarm2", user_id="test_user")
    swarm2.register_agent("col_fast", DummyAgent("Fast1", delay=1.0, result_text="All clear."))
    swarm2.register_agent("col_smart", DummyAgent("Smart1", delay=3.0, result_text="Looks good."))
    swarm2.register_agent("col_adv", DummyAgent("Adv1", delay=5.0, result_text="Buy Signal."))
    
    start_time2 = time.time()
    res2 = await swarm2.run({"user_request": "Analyze market"})
    end_time2 = time.time()
    dur2 = end_time2 - start_time2
    
    print(f"\nExecution Duration: {dur2:.2f} seconds")
    print(res2)
    
    # Total time should be roughly max(1, 3, 5) = 5 seconds, not 1+3+5=9 seconds
    assert dur2 < 6.0, "Execution was not parallel (took too long)!"
    assert dur2 > 4.5, "Execution was weirdly fast?"
    print("✅ Full Parallel Test Passed!")

if __name__ == "__main__":
    test_swarm_concurrency()
