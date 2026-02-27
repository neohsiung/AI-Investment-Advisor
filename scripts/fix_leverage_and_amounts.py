import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from src.data.database import get_db_engine
from src.services.etoro_service import EtoroService
from src.utils.logger import setup_logger
from dotenv import load_dotenv

logger = setup_logger("FixLeverageFromLive")

def run():
    load_dotenv()
    os.environ['DB_HOST'] = 'localhost'
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'

    engine = get_db_engine()
    etoro = EtoroService(user_id=user_id)
    
    positions = etoro.get_positions()
    leverage_map = {}
    for p in positions:
        leverage_map[p.symbol] = p.leverage
        
    logger.info(f"Live Leverages map: {leverage_map}")
    
    with engine.begin() as conn:
        fixed_count = 0
        for ticker, lev in leverage_map.items():
            if lev > 1.0:
                logger.info(f"Fixing {ticker} to leverage {lev}")
                update_query = text("""
                    UPDATE transactions
                    SET leverage = :lev,
                        amount = (price * quantity) / :lev
                    WHERE ticker = :ticker AND action IN ('BUY', 'SELL')
                """)
                res = conn.execute(update_query, {"lev": lev, "ticker": ticker})
                fixed_count += res.rowcount
                logger.info(f"  Updated {res.rowcount} rows for {ticker}")
                
        logger.info(f"Total rows fixed: {fixed_count}")
        
        # Now recalculate cash drift correctly
        delete_sync_query = text("""
            DELETE FROM transactions
            WHERE ticker = 'CASH' AND source_file = 'ETORO_SYNC'
        """)
        res_del = conn.execute(delete_sync_query)
        logger.info(f"Deleted {res_del.rowcount} ETORO_SYNC CASH adjustments to trigger a fresh resync.")

if __name__ == "__main__":
    run()
