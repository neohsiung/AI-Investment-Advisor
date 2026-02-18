import os
import sys
from sqlalchemy import text
from src.data.database import get_db_engine

def fix_deposit(user_email, correct_investment):
    os.environ['DB_HOST'] = 'localhost'
    engine = get_db_engine()
    with engine.begin() as conn:
        # Resolve UUID
        res = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_email}).fetchone()
        if not res:
            print(f"User {user_email} not found.")
            return
        uid = res[0]
        
        print(f"Fixing deposit for {user_email} ({uid})")
        
        # Update DEPOSIT record where ticker is USD or source is etoro sync
        # Based on audit, we have a DEPOSIT of 5878.514 for USD
        conn.execute(text("""
            UPDATE transactions 
            SET amount = :val, quantity = :val 
            WHERE user_id = :uid AND action = 'DEPOSIT' AND ticker = 'USD'
        """), {"uid": uid, "val": correct_investment})
        
        print(f"✓ Updated DEPOSIT to ${correct_investment:,.2f}")

if __name__ == "__main__":
    fix_deposit("supermfb@gmail.com", 674.45)
