
from src.data.database import get_db_connection
from sqlalchemy import text
import sys

def reconcile_db():
    user_id = "ac1b9257-eb9e-4531-8ee4-33fb2633cd38" # From .env
    print(f"Reconciling database for user {user_id}...")
    
    conn = get_db_connection()
    with conn.begin():
        # 1. Zero out phantom positions (AAPL, MSFT)
        # We add a transaction that offsets the current quantity to 0
        for ticker in ['AAPL', 'MSFT']:
            print(f"Zeroing out {ticker}...")
            # Get current quantity
            res = conn.execute(text(
                "SELECT SUM(CASE WHEN action = 'buy' THEN quantity ELSE -quantity END) "
                "FROM transactions WHERE user_id = :uid AND ticker = :ticker"
            ), {'uid': user_id, 'ticker': ticker}).fetchone()
            
            qty = res[0] or 0.0
            if qty != 0:
                print(f"Current {ticker} quantity: {qty}. Adding adjustment transaction...")
                conn.execute(text(
                    "INSERT INTO transactions (id, user_id, ticker, action, quantity, price, fees, date) "
                    "VALUES (gen_random_uuid(), :uid, :ticker, :action, :qty, 0, 0, NOW())"
                ), {
                    'uid': user_id, 
                    'ticker': ticker, 
                    'action': 'sell' if qty > 0 else 'buy', 
                    'qty': abs(qty)
                })
        
        # 2. Ensure COST is present or corrected
        # Actually, let's just trigger a full sync after this.
        print("Phantom positions zeroed out.")

if __name__ == "__main__":
    reconcile_db()
