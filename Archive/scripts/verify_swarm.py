import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.agents.swarm.fundamental_swarm import FundamentalSwarm
from src.agents.base_agent import BaseAgent

# Setup logging
logging.basicConfig(level=logging.INFO)

# Mock BaseAgent.run_tool_loop to avoid API calls and loop logic
def mock_run_tool_loop(self, context, **kwargs):
    ticker = context.get('ticker', 'UNKNOWN')
    if isinstance(context, dict):
         user_req = context.get("user_request", "")
         if "analyze" in user_req.lower():
             return f"Mock Analysis for {ticker}: Falsified Bullish Signal based on request '{user_req}'."
    return f"Mock Output for {ticker}"

BaseAgent.run_tool_loop = mock_run_tool_loop

async def test_swarm():
    print("Initializing Swarm...")
    swarm = FundamentalSwarm(user_id="test_user")
    
    # Mock context
    context = {
        "tickers": ["AAPL", "GOOG", "TSLA"],
        "market_data": {
            "AAPL": {"financials": {"revenue": 100}, "news": [{"title": "AAPL Up"}]},
            "GOOG": {"financials": {"revenue": 200}, "news": [{"title": "GOOG Down"}]},
            "TSLA": {"financials": {"revenue": 300}, "news": [{"title": "TSLA Flat"}]}
        }
    }
    
    print("\nRunning Swarm Async...")
    try:
        result = await swarm._run_async(context)
        print("\n--- Final Aggregated Result ---")
        print(result)
        print("-------------------------------")
    except Exception as e:
        print(f"Swarm Execution Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_swarm())
