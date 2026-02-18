#!/usr/bin/env python3
"""
Test eToro Trading History API
測試 eToro 交易歷史 API
"""
import os
import sys
import logging
from datetime import datetime, timedelta

# Ensure PostgreSQL connection
os.environ['DB_TYPE'] = 'postgres'
os.environ['DB_HOST'] = 'localhost'

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.etoro_service import EtoroService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Test eToro trading history endpoint"""
    
    # User ID from database
    user_id = "90693c07-6177-42df-97d9-915f3ce7c573"
    
    logger.info("=" * 80)
    logger.info("eToro Trading History API Test")
    logger.info("=" * 80)
    
    # Initialize service with user_id to load credentials from database
    etoro = EtoroService(user_id=user_id, mode="real")
    
    # Verify credentials loaded
    if not etoro.api_key or not etoro.user_key:
        logger.error("Failed to load eToro API credentials from database!")
        logger.error(f"API Key present: {bool(etoro.api_key)}")
        logger.error(f"User Key present: {bool(etoro.user_key)}")
        return
    
    logger.info(f"✓ Credentials loaded successfully")
    logger.info(f"✓ Base URL: {etoro.base_url}")
    
    logger.info(f"\n{'='*80}")
    logger.info("Testing Trading History Endpoint")
    logger.info(f"{'='*80}")
    
    # Test different date ranges
    test_cases = [
        ("Last 7 days", 7),
        ("Last 30 days", 30),
        ("Last 90 days", 90),
        ("No date filter", None)
    ]
    
    for test_name, days in test_cases:
        logger.info(f"\n--- {test_name} ---")
        try:
            if days:
                history = etoro.get_history(days=days)
            else:
                # Test without date parameters
                import requests
                endpoint = "/api/v1/trading/info/trade/history"
                url = f"{etoro.base_url}{endpoint}"
                headers = etoro._get_headers()
                
                logger.info(f"URL: {url}")
                logger.info(f"Headers: {headers}")
                
                response = requests.get(url, headers=headers, timeout=15)
                logger.info(f"Status: {response.status_code}")
                logger.info(f"Response: {response.text[:500]}")
                
                if response.status_code == 200:
                    data = response.json()
                    history = data.get('trades', data.get('history', data if isinstance(data, list) else []))
                else:
                    history = []
            
            logger.info(f"Retrieved {len(history)} trades")
            
            if history:
                logger.info(f"\nFirst trade sample:")
                logger.info(f"{history[0]}")
                
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
    
    logger.info(f"\n{'='*80}")
    logger.info("Test Complete")
    logger.info(f"{'='*80}")

if __name__ == "__main__":
    main()
