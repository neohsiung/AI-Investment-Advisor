from src.data.database import get_db_connection
from sqlalchemy import text
from datetime import datetime

def seed_transactions(user_id):
    try:
        with get_db_connection() as conn:
            # Check if user has transactions
            query = text("SELECT COUNT(*) FROM transactions WHERE user_id = :uid")
            count = conn.execute(query, {"uid": user_id}).scalar()
            
            if count == 0:
                print(f"Seeding transactions for {user_id}...")
                conn.execute(text("""
                    INSERT INTO transactions (id, user_id, ticker, type, quantity, price, timestamp, fee)
                    VALUES 
                    (:id1, :uid, 'AAPL', 'BUY', 10, 150.0, :ts, 0.0),
                    (:id2, :uid, 'TSLA', 'BUY', 5, 200.0, :ts, 0.0)
                """), {
                    "id1": "seed-t1",
                    "id2": "seed-t2",
                    "uid": user_id,
                    "ts": datetime.now()
                })
                conn.commit()
                print("Transactions seeded.")
            else:
                print(f"User {user_id} already has {count} transactions.")
                
    except Exception as e:
        print(f"Error seeding: {e}")

if __name__ == "__main__":
    user_uuid = "90693c07-6177-42df-97d9-915f3ce7c573"
    seed_transactions(user_uuid)
