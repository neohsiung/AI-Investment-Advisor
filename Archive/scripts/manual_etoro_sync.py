import sys
import os
import logging
import time
from datetime import datetime
from sqlalchemy import text

# Add project root to path
sys.path.append(os.getcwd())

from src.services.etoro_service import EtoroService
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.infrastructure.risk_manager import RiskManager
from src.data.database import get_db_connection
from src.services.user_focus_service import UserFocusService
from dotenv import load_dotenv

# Load env
load_dotenv()

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')
logger = logging.getLogger("EtoroSync")

def verify_watchlists(etoro_service):
    logger.info("📋 Verifying Watchlists & User Focus...")
    
    # 1. Fetch Watchlists (Populates ID Cache in Service)
    start_time = time.time()
    watchlists = etoro_service.get_watchlists()
    duration = time.time() - start_time
    
    # Parse count
    count = 0
    if isinstance(watchlists, dict) and 'Watchlists' in watchlists:
        count = len(watchlists['Watchlists'])
    elif isinstance(watchlists, list):
        count = len(watchlists)
        
    logger.info(f"Found {count} watchlists in {duration:.2f}s.")
    
    # 2. Extract User Focus
    focus_service = UserFocusService(etoro_service=etoro_service)
    focus = focus_service.get_user_focus()
    logger.info(f"🔍 User Focus Extracted: {focus}")

def main():
    user_id = "supermfb@gmail.com"
    # Fetch keys from Settings Repository
    from src.repositories.settings_repository import SqliteSettingsRepository
    repo = SqliteSettingsRepository()
    api_key = repo.get(user_id, "etoro_api_key")
    user_key = repo.get(user_id, "etoro_user_key")
    mode = repo.get(user_id, "etoro_mode") or "real"

    # Fallback to Env Vars if not in DB
    if not api_key:
        api_key = os.getenv("ETORO_API_KEY")
        user_key = os.getenv("ETORO_USER_KEY")
        logger.info("⚠️ Keys not found in DB, using Environment Variables.")

    if not api_key:
        logger.error(f"❌ ETORO_API_KEY not found in Settings or Env for user {user_id}.")
        return

    logger.info("🚀 Starting eToro Data Overwrite/Sync...")
    
    # Mode from Repo or default to 'real' if key present?
    # If using env var, assume real unless ETORO_MODE set
    if not mode:
        mode = os.getenv("ETORO_MODE", "real")
        
    etoro = EtoroService(mode=mode, api_key=api_key, user_key=user_key)
    
    logger.info(f"Connected to eToro as: {etoro.base_url}")
    
    # 0. Initialize Metadata (Watchlists)
    # Important: Fetching watchlists populates the ID->Ticker map for positions
    verify_watchlists(etoro)

    # 1. Sync Positions (Snapshot)
    logger.info("📥 Fetching current positions from eToro...")
    positions = etoro.get_positions()
    logger.info(f"Found {len(positions)} open positions.")
    for p in positions:
        logger.info(f" - {p.symbol}: {p.quantity} @ ${p.open_price} (Val: ${p.market_value})")

    # 2. Sync History (Overwrite Mode)
    logger.info("🔄 Syncing Transaction History (Overwrite Mode)...")
    logger.info(f"⚠️  Clearing existing transactions for user: {user_id}")
    
    # Clear DB Logic
    failed_clear = False
    try:
        with get_db_connection() as conn:
             conn.execute(text("DELETE FROM transactions WHERE user_id = :uid"), {"uid": user_id})
             conn.execute(text("DELETE FROM cash_flows WHERE user_id = :uid"), {"uid": user_id})
             conn.commit()
        logger.info("✅ Data cleared.")
    except Exception as e:
        logger.error(f"Failed to clear data: {e}")
        failed_clear = True

    if failed_clear:
        logger.error("Aborting sync due to DB error.")
        return

    # Sync History
    result = etoro.sync_history(user_id)
    added = result.get('added', 0)
    skipped = result.get('skipped', 0)
    logger.info(f"History Sync Result: Added {added}, Skipped {skipped}")

    # Fallback: Seed from Positions if History is empty
    if added == 0 and len(positions) > 0:
        logger.warning(f"⚠️ History sync returned 0 but {len(positions)} positions exist.")
        logger.info("🌱 Seeding database with synthetic 'BUY' transactions from current positions...")
        
        repo = SqliteTransactionRepository()
        seed_count = 0
        
        for pos in positions:
             try:
                 # Check if already exists (basic check, though we just cleared)
                 # Actually we just cleared, so just add.
                 # Use open_date from position
                 date_str = pos.open_date.strftime('%Y-%m-%d')
                 
                 repo.add(
                     user_id=user_id,
                     ticker=pos.symbol,
                     date=date_str,
                     action="BUY",
                     quantity=pos.quantity,
                     price=pos.open_price,
                     fees=0.0
                 )
                 seed_count += 1
             except Exception as e:
                 logger.error(f"Failed to seed {pos.symbol}: {e}")
                 
        logger.info(f"✅ Seeding Complete: Added {seed_count} transactions.")
        
        # 3. Insert Initial Deposit (For correct ROI calculation)
        # Net Invested = Cash + Cost of Positions
        account = etoro.get_account()
        if account:
            cash = account.available_cash
            # Sum of 'market_value' in our domain object comes from 'unitsBaseValueDollars' (Cost)
            cost_of_positions = sum(p.market_value for p in positions)
            total_initial_equity = cash + cost_of_positions
            
            logger.info(f"💰 Inserting Initial Deposit: ${total_initial_equity:.2f} (Cash ${cash:.2f} + Cost ${cost_of_positions:.2f})")
            
            try:
                # Insert into cash_flows table directly
                with get_db_connection() as conn:
                    import uuid
                    cf_id = str(uuid.uuid4())
                    
                    conn.execute(text("""
                        INSERT INTO cash_flows (id, user_id, date, amount, type, description)
                        VALUES (:id, :uid, :date, :amount, 'DEPOSIT', 'Initial Deposit from Etoro Sync')
                    """), {
                        "id": cf_id,
                        "uid": user_id,
                        "date": datetime.now().strftime('%Y-%m-%d'),
                        "amount": total_initial_equity
                    })
                    conn.commit()
                    logger.info(f"✅ Initial Deposit Added to cash_flows: ${total_initial_equity:.2f}")
            except Exception as e:
                logger.error(f"Failed to add deposit: {e}")

    logger.info("🎉 eToro Integration Validation Complete.")

if __name__ == "__main__":
    main()
