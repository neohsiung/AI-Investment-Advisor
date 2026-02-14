
import sys
import os
import logging
import json

# Add project root to path
sys.path.append(os.getcwd())

from src.services.etoro_service import EtoroService

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')
logger = logging.getLogger("EtoroVerify")

def main():
    logger.info("🚀 Starting eToro Fix Verification...")
    
    etoro = EtoroService()
    
    # 1. Verify Ticker Resolution (via get_positions auto-fetch)
    logger.info("1. Verifying Position Tickers...")
    try:
        positions = etoro.get_positions()
        if positions:
            logger.info(f"Found {len(positions)} positions.")
            for p in positions[:5]:
                logger.info(f" - Symbol: {p.symbol} (ID Resolved?), Qty: {p.quantity}, MV: {p.market_value}")
                if p.symbol.isdigit():
                    logger.error(f"❌ Ticker {p.symbol} is still numeric!")
                else:
                    logger.info("✅ Ticker looks valid.")
        else:
            logger.warning("No positions found.")
    except Exception as e:
        logger.error(f"get_positions failed: {e}")

    # 2. Verify Account Balance (Equity/Cash calc)
    logger.info("2. Verifying Account Balance...")
    try:
        account = etoro.get_account()
        if account:
            logger.info(f"Account ID: {account.account_id}")
            logger.info(f"Total Equity: ${account.total_equity:,.2f}")
            logger.info(f"Available Cash: ${account.available_cash:,.2f}")
            
            # Validation rule from user feedback
            # NAV ~ 1182.15, Cash ~ 317.91
            if 1100 <= account.total_equity <= 1300:
                logger.info("✅ Equity is within expected range (~1182).")
            else:
                logger.warning(f"⚠️ Equity {account.total_equity} seems off (Expected ~1182).")
                
            if 300 <= account.available_cash <= 350:
                 logger.info("✅ Cash is within expected range (~317).")
            else:
                 logger.warning(f"⚠️ Cash {account.available_cash} seems off (Expected ~317).")
        else:
            logger.error("❌ get_account returned None.")
    except Exception as e:
        logger.error(f"get_account failed: {e}")

if __name__ == "__main__":
    main()
