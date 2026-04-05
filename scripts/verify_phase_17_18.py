import asyncio
import json
import logging
import sys
import os
import uuid
from datetime import datetime

# Ensure the project root is in sys.path
sys.path.append(os.getcwd())

from src.agents.sensory_agent import SensoryAgent
from src.agents.base_agent import BaseAgent
from src.data.database import get_db_engine
from src.data.models import User, UserCustomPrompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Verify_17_18")

async def test_sensory_agent():
    logger.info("--- 📡 Testing Task 17.2: Sensory Agent ---")
    agent = SensoryAgent()
    
    # 1. Test Alert Needed
    ctx = {
        "ticker": "TSLA",
        "price_info": "Current: $250 (+15% Gapped Up)",
        "recent_news": "Tesla announces record delivery and new factory in Mars."
    }
    
    logger.info("  Scanning for alerts (Price Gap Up)...")
    res_str = await agent.run(ctx)
    res = json.loads(res_str)
    
    if res.get("alert_needed"):
        logger.info(f"  ✅ Alert Triggered: {res.get('reason')} (Urgency: {res.get('urgency')})")
    else:
        logger.error("  ❌ Alert should have been triggered for 15% gap.")

async def test_dynamic_prompt_injection():
    logger.info("\n--- 🧠 Testing Task 18.3: Dynamic Prompt Injection ---")
    
    user_id = str(uuid.uuid4())
    agent_name = "TestDynamicAgent"
    
    # 1. Create a dummy agent
    class TestAgent(BaseAgent):
        def __init__(self, **kwargs):
            super().__init__(name=agent_name, prompt_path="prompts/cio_agent.txt", **kwargs)

    # Pre-check: Should load from file
    agent_initial = TestAgent(user_id=user_id)
    # logger.info(f"  Initial Prompt Source: {agent_initial.system_prompt[:50]}...")

    # 2. Add custom prompt to DB
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=get_db_engine())
    session = Session()
    
    custom = UserCustomPrompt(
        user_id=user_id,
        agent_name=agent_name,
        custom_prompt="YOU ARE A HYPER-OPTIMIZED CUSTOM PROMPT OVERRIDE."
    )
    session.add(custom)
    session.commit()
    
    # 3. Reload Agent
    agent_dynamic = TestAgent(user_id=user_id)
    
    if agent_dynamic.system_prompt == "YOU ARE A HYPER-OPTIMIZED CUSTOM PROMPT OVERRIDE.":
        logger.info("  ✅ Dynamic Prompt successfully injected from Database.")
    else:
        logger.error(f"  ❌ Dynamic Prompt failed. Found: {agent_dynamic.system_prompt[:50]}")
    
    session.delete(custom)
    session.commit()
    session.close()

async def main():
    # We skip full DB integration tests if networking is restricted, 
    # but we test the logic.
    try:
        await test_sensory_agent()
        await test_dynamic_prompt_injection()
    except Exception as e:
        logger.error(f"Verification failed: {e}")
    
    logger.info("\n✨ Phase 17 & 18 Verification Completed.")

if __name__ == "__main__":
    asyncio.run(main())
