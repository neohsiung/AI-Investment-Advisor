import os
import sys
import pandas as pd
from sqlalchemy import text
from src.data.database import get_db_engine
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.repositories.snapshot_repository import AlchemySnapshotRepository
from src.services.analytics_service import LeverageCalculator

def audit_user(user_email):
    print(f"Starting audit for {user_email}...")
    try:
        # Override for local audit
        os.environ['DB_HOST'] = 'localhost'
        os.environ['DB_USER'] = 'postgres'
        os.environ['DB_PASS'] = 'postgres'
        os.environ['DB_NAME'] = 'portfolio'
        
        engine = get_db_engine()
        print(f"Got DB Engine for {os.getenv('DB_HOST')}...")
        
        with engine.connect() as conn:
            # List all users first to debug
            users = conn.execute(text("SELECT email, id FROM users")).fetchall()
            print("\n--- Registered Users ---")
            for u in users:
                print(f"- {u[0]} ({u[1]})")

            # Resolve UUID
            res = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_email}).fetchone()
            if not res:
                print(f"\n[ERROR] User {user_email} not found.")
                # Try case insensitive
                res = conn.execute(text("SELECT id FROM users WHERE LOWER(email) = LOWER(:email)"), {"email": user_email}).fetchone()
                if res:
                    print(f"[INFO] Found user via case-insensitive search: {res[0]}")
                    uid = res[0]
                else:
                    return
            else:
                uid = res[0]
            
            print(f"\n>>> Auditing User UUID: {uid}")

            # 1. Transactions Summary
            print("\n--- Transactions Summary ---")
            trans_repo = AlchemyTransactionRepository(engine=engine)
            all_trans = trans_repo.get_all_by_user(uid)
            print(f"Total Transactions: {len(all_trans)}")
            
            # Breakdown by action
            df_trans = pd.DataFrame([dict(r._mapping) for r in all_trans])
            if not df_trans.empty:
                print("Quantity-based Summary:")
                print(df_trans.groupby(['action'])['quantity'].sum())
                print("\nAmount-based Summary:")
                print(df_trans.groupby(['action'])['amount'].sum())
                
                print("\n--- All Transaction Sources ---")
                print(df_trans.groupby(['source_file', 'action']).size())
                
                # Check for extreme entries
                print("\nExtreme Entries (Price > 1M or Quantity > 1M):")
                print(df_trans[(df_trans['price'] > 1000000) | (df_trans['quantity'] > 1000000)])
            
            # 2. Invested Capital vs NLV
            print("\n--- ROI Logic Audit ---")
            net_invested = trans_repo.calculate_net_invested_capital(uid)
            cash_balance = trans_repo.get_cash_balance(uid)
            
            active_tickers = trans_repo.get_active_tickers(uid)
            print(f"Active Tickers: {active_tickers}")
            
            calc = LeverageCalculator(repository=trans_repo)
            # Use very minimal prices for audit if we don't want to call external APIs
            mock_prices = {t: 1.0 for t in active_tickers} 
            metrics = calc.calculate_metrics(mock_prices, uid)
            
            print(f"Net Invested Capital: ${net_invested:,.2f} (Deposits - Withdrawals)")
            print(f"Cash Balance (Calculated): ${cash_balance:,.2f}")
            print(f"NLV (with mock $1.0 prices): ${metrics['nlv']:,.2f}")
            
            if net_invested != 0:
                profit = metrics['nlv'] - net_invested
                roi = (profit / net_invested) * 100
                print(f"Calculated ROI (mock): {roi:.2f}%")
            
            # 3. Snapshots history
            print("\n--- Snapshots ---")
            snap_repo = AlchemySnapshotRepository(engine=engine)
            history = snap_repo.get_history_by_user(uid)
            print(f"Total Snapshots: {len(history)}")
            if not history.empty:
                print(history.sort_values('date').tail(10)[['date', 'total_nlv', 'invested_capital', 'pnl']])
            else:
                print("No snapshots found.")

    except Exception as e:
        print(f"Error during audit: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    email = "supermfb@gmail.com"
    if len(sys.argv) > 1:
        email = sys.argv[1]
    audit_user(email)
