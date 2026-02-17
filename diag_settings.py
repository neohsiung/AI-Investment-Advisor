from src.data.database import get_db_connection
from sqlalchemy import text
import os

def check_settings():
    try:
        with get_db_connection() as conn:
            query = text("SELECT key, value FROM settings WHERE key LIKE 'channel_%';")
            rows = conn.execute(query).fetchall()
            print("--- Channel Settings ---")
            for row in rows:
                print(f"{row[0]}: {row[1]}")
            
            # Also check user mapping to see if user is linked
            query = text("SELECT user_id, channel, channel_user_id FROM user_channels;")
            rows = conn.execute(query).fetchall()
            print("\n--- User Channels ---")
            for row in rows:
                print(f"User: {row[0]} | Channel: {row[1]} | ID: {row[2]}")
                
    except Exception as e:
        print(f"Error checking settings: {e}")

if __name__ == "__main__":
    check_settings()
