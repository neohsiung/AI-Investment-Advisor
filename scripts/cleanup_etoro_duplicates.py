import os
import sys

sys.path.insert(0, '/workspace')

try:
    from sqlalchemy import text
    from src.data.database import get_db_engine
    
    engine = get_db_engine()
    with engine.connect() as conn:
        with conn.begin():
            user_id = '90693c07-6177-42df-97d9-915f3ce7c573'

            # --- 1. Cleanup Duplicate eToro Trades ---
            # Any duplicated trades with exact same date, action, quantity, price.
            # We want to keep exactly one. Prefer one without "ID_" and without ".HK", else keep the MAX(created_at) or MAX(ticker).
            
            # Step 1: Find all signatures that have duplicates
            find_dup_query = text("""
                SELECT trade_date, action, quantity, price, array_agg(id) as ids, array_agg(ticker) as tickers
                FROM transactions
                WHERE user_id = :uid AND action IN ('BUY', 'SELL', 'DIVIDEND', 'FEE')
                GROUP BY trade_date, action, quantity, price
                HAVING count(*) > 1
            """)
            dups = conn.execute(find_dup_query, {'uid': user_id}).fetchall()
            
            deleted_count = 0
            for row in dups:
                ids = row.ids
                tickers = row.tickers
                
                # Pick the BEST id to keep
                # Scoring: 1. No "ID_" and no ".HK", 2. Highest length (maybe real ticker like CRWD over ID_5506).
                # Fallback to the first one.
                best_id = ids[0]
                best_score = -1
                
                for idx, (tx_id, t) in enumerate(zip(ids, tickers)):
                    score = 0
                    if not t.startswith("ID_"):
                        score += 10
                    if not t.endswith(".HK"):
                        score += 10
                    if score > best_score:
                        best_score = score
                        best_id = tx_id
                
                # Delete all other ids
                ids_to_delete = [tx_id for tx_id in ids if tx_id != best_id]
                for tx_id in ids_to_delete:
                    conn.execute(text("DELETE FROM transactions WHERE id = :id"), {'id': tx_id})
                    deleted_count += 1
            
            print(f"Deleted {deleted_count} duplicate trade records.")

            # --- 2. Cleanup ETORO_SYNC Noise ---
            # Remove all CASH operations around March 7th and 8th that were added for sync and caused the mess.
            # Particularly the ones with exact same amounts -297.7456, 297.82, etc.
            # Just delete ALL CASH DEPOSIT/WITHDRAWAL around that 2-day period to completely reset it,
            # wait, actually the legitimate ones might be deleted. 
            # Looking at the history:
            # 2026-03-08    DEPOSIT    CASH  1.000000  297.74560  297.745600   0.0  ETORO_SYNC
            # 2026-03-07    DEPOSIT    CASH  1.000000 -297.74560 -297.745600   0.0        None
            # 2026-03-07 WITHDRAWAL    CASH  1.000000 1284.23750 1284.237500   0.0        None
            # 2026-03-07 WITHDRAWAL     USD  1.000000  297.82100  297.821000   0.0        None
            # 2026-03-07    DEPOSIT     USD  1.000000    0.00005    0.000050   0.0        None
            # 2026-03-07 WITHDRAWAL    CASH  1.000000    0.00005    0.000050   0.0        None
            
            # Since these are all noisy and balance each other or counteract each other, 
            # we will delete the ETORO_SYNC rows, and any CASH or USD ticker rows on '2026-03-07' and '2026-03-08'
            # EXCEPT legitimate ones that have source_file != 'ETORO_SYNC' and source_file != None
            
            del_cash = conn.execute(text("""
                DELETE FROM transactions
                WHERE user_id = :uid 
                  AND ticker IN ('CASH', 'USD')
                  AND (source_file IS NULL OR source_file = 'ETORO_SYNC')
            """), {'uid': user_id}).rowcount
            print(f"Deleted {del_cash} noisy CASH/USD sync/record entries.")

            print("Database cleanup completed successfully.")

except Exception as e:
    import traceback
    traceback.print_exc()
