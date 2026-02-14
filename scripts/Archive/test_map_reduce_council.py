import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.services.council_service import CouncilService
from src.utils.logger import setup_logger

logging.basicConfig(level=logging.INFO)
logger = setup_logger("MapReduceTest")

async def main():
    logger.info("Starting Map-Reduce Council Test...")
    
    # Mock Data
    portfolio = [
        {"symbol": "AAPL", "quantity": 10},
        {"symbol": "NVDA", "quantity": 5},
        {"symbol": "TSLA", "quantity": 20},
        {"symbol": "MSFT", "quantity": 15},
        {"symbol": "GOOGL", "quantity": 8},
        {"symbol": "AMZN", "quantity": 12}, # Add 6th to test batching > 5
        {"symbol": "META", "quantity": 7}
    ]
    
    context_data = {
        "portfolio": portfolio,
        "market_data": {"vix": 15.0}, # Low volatility
        "user_id": "test_user"
    }
    
    service = CouncilService()
    
    # Run Map-Reduce
    try:
        topic = "Weekly Portfolio Review"
        result = await service.start_session(topic, context_data, scope="portfolio")
        
        logger.info(f"Session ID: {result.get('session_id')}")
        logger.info(f"Type: {result.get('type')}")
        
        transcript = result.get('transcript', '')
        logger.info(f"Transcript Length: {len(transcript)} chars")
        print("\n--- Aggregated Transcript (Snippet) ---")
        print(transcript[:500] + "...")
        
        consensus = result.get('consensus', '')
        print("\n--- CIO Consensus (Snippet) ---")
        print(consensus[:500] + "...")
        
        if "AAPL" in transcript and "META" in transcript:
            logger.info("SUCCESS: Automated Map-Reduce covered all tickers.")
        else:
            logger.error("FAILURE: Some tickers missing from transcript.")
            
    except Exception as e:
        logger.error(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
