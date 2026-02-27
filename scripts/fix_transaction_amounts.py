import os
import sys

# Ensure src module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from src.data.database import get_db_engine
from src.utils.logger import setup_logger

logger = setup_logger("FixTransactionAmounts")

def run_migration():
    os.environ['DB_HOST'] = 'localhost'
    engine = get_db_engine()
    
    with engine.begin() as conn:
        # First, query how many rows need fixing
        # A row needs fixing if: action IN ('BUY', 'SELL') AND leverage > 1.0 AND ABS(amount - (price * quantity)) < 0.01 
        # (Meaning amount is currently price * quantity)
        
        # Actually it's probably safer to just blindly update ALL BUY/SELL rows to (price * quantity) / leverage
        # Since it should mathematically be correct for all of them.
        
        check_query = text("""
            SELECT COUNT(*) FROM transactions
            WHERE action IN ('BUY', 'SELL')
        """)
        
        total_rows = conn.execute(check_query).scalar()
        logger.info(f"Checking {total_rows} BUY/SELL transactions for incorrect amounts...")
        
        # We also need to see if any have leverage > 1 and amount == price * quantity
        check_bad_query = text("""
            SELECT COUNT(*) FROM transactions
            WHERE action IN ('BUY', 'SELL') 
            AND leverage > 1.0
            AND ABS(amount - (price * quantity)) < 0.1
        """)
        bad_rows = conn.execute(check_bad_query).scalar()
        logger.info(f"Found {bad_rows} leveraged transactions with purely nominal amounts (need fixing).")
        
        update_query = text("""
            UPDATE transactions
            SET amount = (price * quantity) / leverage
            WHERE action IN ('BUY', 'SELL')
            AND leverage IS NOT NULL
            AND leverage > 0
        """)
        
        res = conn.execute(update_query)
        logger.info(f"Successfully updated 'amount' for {res.rowcount} BUY/SELL transactions.")
        
        # Now, delete all CASH transactions sourced from ETORO_SYNC so that
        # the system will recalculate the accurate cash drift on next sync.
        delete_sync_query = text("""
            DELETE FROM transactions
            WHERE ticker = 'CASH' AND source_file = 'ETORO_SYNC'
        """)
        res_del = conn.execute(delete_sync_query)
        logger.info(f"Deleted {res_del.rowcount} ETORO_SYNC CASH adjustments. They will be recreated accurately.")

if __name__ == "__main__":
    run_migration()
