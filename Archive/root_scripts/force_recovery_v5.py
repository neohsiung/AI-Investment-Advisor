import os
import uuid
import json
from sqlalchemy import create_engine, text

def force_recovery():
    db_url = os.getenv("DB_URL", "postgresql://postgres:postgres@localhost:5432/portfolio")
    engine = create_engine(db_url)
    target_email = "supermfb@gmail.com"
    
    print(f"--- Force Recovery for {target_email} ---")
    
    with engine.begin() as conn:
        # Disable all constraints/triggers for this session
        conn.execute(text("SET session_replication_role = 'replica';"))
        
        # 1. Ensure schema is harmonized (again, just in case)
        print("  Checking schema...")
        tables_cols = {
            "users": ["preferences", "metadata"],
            "reports": ["user_id", "title", "created_at"],
            "daily_snapshots": ["user_id", "total_tnv", "leverage_ratio"],
            "settings": ["user_id", "updated_at"]
        }
        for table, cols in tables_cols.items():
            res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")).fetchall()
            existing = [r[0] for r in res]
            for c in cols:
                if c not in existing:
                    print(f"    Adding {c} to {table}")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {c} TEXT")) # Simplified def for speed
        
        # 2. Identify current ID for the email
        user = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": target_email}).fetchone()
        if not user:
            print(f"  User {target_email} not found in database. Exiting.")
            return
            
        old_id = user[0]
        if "@" not in old_id:
            print(f"  User {target_email} already has a non-email ID: {old_id}")
            new_id = old_id
        else:
            new_id = str(uuid.uuid4())
            print(f"  Updating ID for {target_email}: {old_id} -> {new_id}")
            conn.execute(text("UPDATE users SET id = :new_id WHERE id = :old_id"), {"new_id": new_id, "old_id": old_id})
        
        # 3. Update ALL tables
        # Use a broad list of tables
        all_tables = [
            "transactions", "daily_snapshots", "cash_flows", "settings", 
            "user_identities", "reports", "council_minutes", "event_logs", 
            "daily_reports", "weekly_reports", "channel_verifications", "prompt_history"
        ]
        
        for table in all_tables:
            try:
                # Check if table and user_id column exist
                check = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' AND column_name = 'user_id'")).fetchone()
                if check:
                    res = conn.execute(text(f"UPDATE {table} SET user_id = :new_id WHERE user_id = :old_id"), {"new_id": new_id, "old_id": old_id})
                    print(f"    Updated {table} ({res.rowcount} rows)")
            except Exception as e:
                print(f"    Failed to update {table}: {str(e).splitlines()[0]}")

        # 4. Ensure Identity Resolution is correct
        conn.execute(text("DELETE FROM user_identities WHERE user_id = :new_id AND provider = 'email'"), {"new_id": new_id})
        conn.execute(text("""
            INSERT INTO user_identities (id, user_id, provider, identifier, is_primary)
            VALUES (:id, :uid, 'email', :email, 1)
        """), {"id": str(uuid.uuid4()), "uid": new_id, "email": target_email})
        print("    Updated user_identities.")

        # Re-enable constraints
        conn.execute(text("SET session_replication_role = 'origin';"))

    print("\nForce recovery complete.")

if __name__ == "__main__":
    force_recovery()
