import os
import logging
import asyncio
from dotenv import load_dotenv
from src.services.etoro_service import EtoroService

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    logger.info(f"Starting eToro sync for user: {user_id}")
    
    # Check if keys are loaded
    api_key = os.getenv("ETORO_API_KEY")
    user_key = os.getenv("ETORO_USER_KEY")
    
    if not api_key:
        logger.error("ETORO_API_KEY not found in environment!")
        return

    logger.info(f"Using API Key (prefix): {api_key[:5]}...")
    
    # Initialize service
    etoro = EtoroService()
    logger.info(f"Using Base URL: {etoro.base_url}")
    
    # Run sync_history
    results = etoro.sync_history(user_id=user_id)
    
    logger.info(f"Sync complete. Added: {results['added']}, Skipped: {results['skipped']}")

if __name__ == "__main__":
    asyncio.run(main())
