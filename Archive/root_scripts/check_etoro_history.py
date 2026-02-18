#!/usr/bin/env python3
"""
檢查 eToro 完整歷史記錄
Check eToro complete history
"""

import os
import logging
import json
from dotenv import load_dotenv
from src.services.etoro_service import EtoroService

# Load environment variables
load_dotenv()

# Override DB_HOST for local development
if os.getenv('DB_TYPE') == 'postgres' and os.getenv('DB_HOST') == 'postgres':
    os.environ['DB_HOST'] = 'localhost'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    
    logger.info("=" * 80)
    logger.info("eToro 完整歷史記錄檢查")
    logger.info("=" * 80)
    
    # Initialize eToro service
    etoro = EtoroService(user_id=user_id)
    
    # Get history (all records from 2024)
    logger.info("\n獲取完整交易歷史（從 2024-01-01）...")
    history = etoro.get_history(days=779)  # From 2024-01-01
    
    logger.info(f"\n總記錄數: {len(history)}")
    
    if history:
        # Show first record structure
        logger.info("\n第一筆記錄的完整結構:")
        logger.info(json.dumps(history[0], indent=2, default=str))
        
        # Analyze record types
        logger.info("\n所有記錄的欄位分析:")
        all_keys = set()
        for record in history:
            all_keys.update(record.keys())
        logger.info(f"所有欄位: {sorted(all_keys)}")
        
        # Show sample records
        logger.info("\n前 10 筆記錄摘要:")
        for i, record in enumerate(history[:10]):
            logger.info(f"\n記錄 {i+1}:")
            for key, value in record.items():
                logger.info(f"  {key}: {value}")
    else:
        logger.warning("沒有獲取到任何歷史記錄")
    
    logger.info("\n" + "=" * 80)

if __name__ == "__main__":
    main()
