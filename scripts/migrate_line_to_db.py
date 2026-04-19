
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def migrate():
    load_dotenv()
    
    # 1. Get credentials from .env
    env_secret = os.getenv("LINE_CHANNEL_SECRET")
    env_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    
    if not env_secret and not env_token:
        print("No LINE credentials found in .env. Skipping migration.")
        return

    # 2. Database connection
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Fallback to standard dev DB
        db_url = f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'portfolio')}"
    
    engine = create_engine(db_url)
    user_id = "90693c07-6177-42df-97d9-915f3ce7c573" # supermfb@gmail.com
    
    with engine.connect() as conn:
        # 3. Check and migrate Secret
        res = conn.execute(text("SELECT value FROM settings WHERE user_id = :uid AND key = 'channel_line_secret'"), {"uid": user_id}).fetchone()
        if res:
            print(f"Setting 'channel_line_secret' already exists in DB: {res[0][:4]}... (Prioritizing DB)")
        elif env_secret:
            conn.execute(text("INSERT INTO settings (user_id, key, value) VALUES (:uid, 'channel_line_secret', :val)"), {"uid": user_id, "val": env_secret})
            print("Successfully migrated 'channel_line_secret' to DB.")
        
        # 4. Check and migrate Token
        res = conn.execute(text("SELECT value FROM settings WHERE user_id = :uid AND key = 'channel_line_access_token'"), {"uid": user_id}).fetchone()
        if res:
            print(f"Setting 'channel_line_access_token' already exists in DB: {res[0][:4]}... (Prioritizing DB)")
        elif env_token:
            conn.execute(text("INSERT INTO settings (user_id, key, value) VALUES (:uid, 'channel_line_access_token', :val)"), {"uid": user_id, "val": env_token})
            print("Successfully migrated 'channel_line_access_token' to DB.")
            
        conn.commit()
    
    print("\nMigration Complete.")
    print("WARNING: Please manually remove LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN from your .env file now.")

if __name__ == "__main__":
    migrate()
