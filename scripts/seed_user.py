
import os
import sys
import uuid
import uuid  # duplicate import, cleaning up
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from src.data.database import get_db_connection
from sqlalchemy import text

def seed_user():
    user_id = "supermfb@gmail.com"
    email = "supermfb@gmail.com"
    
    conn = get_db_connection()
    try:
        # 1. Check if user exists
        res = conn.execute(text("SELECT id FROM users WHERE id = :uid"), {"uid": user_id}).fetchone()
        if not res:
            print(f"Creating user {user_id}...")
            conn.execute(text(
                "INSERT INTO users (id, email, name, created_at) VALUES (:uid, :email, :name, :created)"
            ), {"uid": user_id, "email": email, "name": "Super User", "created": datetime.now().isoformat()})
        else:
            print(f"User {user_id} already exists.")
            
        # 2. Check for transactions (active position)
        res_trans = conn.execute(text("SELECT id FROM transactions WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        if not res_trans:
            print("Seeding sample transaction (AAPL)...")
            tid = str(uuid.uuid4())
            conn.execute(text(
                """INSERT INTO transactions 
                (id, user_id, ticker, trade_date, action, quantity, price, amount, currency) 
                VALUES (:id, :uid, 'AAPL', :date, 'BUY', 10, 150.0, 1500.0, 'USD')"""
            ), {"id": tid, "uid": user_id, "date": "2023-10-01", "uid": user_id})
            
            # Also seed NVDA for variety
            tid2 = str(uuid.uuid4())
            conn.execute(text(
                """INSERT INTO transactions 
                (id, user_id, ticker, trade_date, action, quantity, price, amount, currency) 
                VALUES (:id, :uid, 'NVDA', :date, 'BUY', 5, 400.0, 2000.0, 'USD')"""
            ), {"id": tid2, "uid": user_id, "date": "2023-10-05"})
            
        conn.commit()
        print("Seeding complete.")
        
    except Exception as e:
        print(f"Seeding failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_user()
