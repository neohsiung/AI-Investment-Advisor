import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.conversation_agent import ConversationAgent
from src.utils.logger import setup_logger

logger = setup_logger("VerifyPhase2")

async def verify_swarm():
    user_id = "test_user_swarm"
    agent = ConversationAgent(user_id=user_id, channel_id="test_channel", channel_type="terminal")
    
    print("\n=== Scenario 1: Fast Path (Skill Router) ===")
    res1 = await agent.respond("NVDA 的價格是多少？")
    print(f"Response 1: {res1}")
    
    print("\n=== Scenario 2: Team Mode (Decomposer + Swarm) ===")
    complex_msg = "分析一下 NVDA 的動能和基本面，並讓 CIO 給我一個最終的投資建議。"
    res2 = await agent.respond(complex_msg)
    print(f"Response 2: {res2}")

if __name__ == "__main__":
    asyncio.run(verify_swarm())
