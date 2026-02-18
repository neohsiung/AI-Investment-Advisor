import os
import uuid
import sqlite3
import json
from sqlalchemy import create_engine, text

def run_recovery():
    db_url = os.getenv("DB_URL", "postgresql://postgres:postgres@localhost:5432/portfolio")
    engine = create_engine(db_url)
    sqlite_path = "data/portfolio.db"
    
    print("--- Step 1: Massive Schema Harmonization ---")
    harmonize_tasks = [
        ("users", [
            ("preferences", "JSONB DEFAULT '{}'"),
            ("metadata", "JSONB DEFAULT '{}'"),
            ("id", "TEXT")
        ]),
        ("reports", [
            ("user_id", "TEXT"),
            ("title", "TEXT"),
            ("created_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP"),
            ("published_at", "TIMESTAMPTZ"),
            ("id", "TEXT")
        ]),
        ("transactions", [
            ("user_id", "TEXT")
        ]),
        ("daily_snapshots", [
            ("user_id", "TEXT"),
            ("total_tnv", "NUMERIC DEFAULT 0"),
            ("leverage_ratio", "NUMERIC DEFAULT 0")
        ]),
        ("settings", [
            ("user_id", "TEXT"),
            ("updated_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP")
        ])
    ]
    
    for table, cols in harmonize_tasks:
        print(f"  Harmonizing table: {table}")
        for col_name, col_def in cols:
            try:
                with engine.begin() as conn:
                    # Check if column exists
                    res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' AND column_name = '{col_name}'"))
                    if not res.fetchone():
                        print(f"    Adding column: {col_name} to {table}")
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
            except Exception as e:
                print(f"    Error add column {col_name} to {table}: {str(e).splitlines()[0]}")

    print("\n--- Step 2: Unifying User Identities ---")
    users = []
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT id, email FROM users")).fetchall()
            users = [(r[0], r[1]) for r in res]
    except Exception as e:
        print(f"  Error reading users: {e}")
        
    id_map = {}
    for uid, email in users:
        if "@" in uid:
            new_uuid = str(uuid.uuid4())
            print(f"  Migrating {email}...")
            try:
                with engine.begin() as conn:
                    # Fetch data
                    user_data = conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": uid}).fetchone()
                    user_dict = dict(user_data._mapping)
                    user_dict['id'] = new_uuid
                    
                    # Fix JSON
                    for k in ['preferences', 'metadata']:
                        if k in user_dict and isinstance(user_dict[k], (dict, list)):
                            user_dict[k] = json.dumps(user_dict[k])
                    
                    # Insert new
                    keys = user_dict.keys()
                    query = text(f"INSERT INTO users ({', '.join(keys)}) VALUES ({', '.join([':'+k for k in keys])}) ON CONFLICT (email) DO NOTHING")
                    conn.execute(query, user_dict)
                    id_map[uid] = new_uuid
            except Exception as e:
                print(f"    Failed to create new record for {email}: {e}")
        else:
            id_map[uid] = uid

    print("\n--- Step 3: Cascading Updates ---")
    tables = ["transactions", "daily_snapshots", "cash_flows", "settings", "user_identities", "reports", "council_minutes", "event_logs", "daily_reports", "weekly_reports"]
    for old_id, new_id in id_map.items():
        if old_id == new_id: continue
        
        for table in tables:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"UPDATE {table} SET user_id = :new_id WHERE user_id = :old_id"), {"new_id": new_id, "old_id": old_id})
                    print(f"    Updated {table} for {old_id}")
            except Exception as e:
                pass
        
        # Link identity
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO user_identities (id, user_id, provider, identifier, is_primary)
                    VALUES (:id, :uid, 'email', :email, 1)
                    ON CONFLICT (provider, identifier) DO UPDATE SET user_id = :uid
                """), {"id": str(uuid.uuid4()), "uid": new_id, "email": old_id})
        except Exception as e:
            print(f"    Failed to link identity for {old_id}: {e}")

        # Cleanup
        try:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM users WHERE id = :old_id"), {"old_id": old_id})
                print(f"    Deleted legacy user {old_id}")
        except Exception as e:
             print(f"    Legacy user {old_id} still has references, keeping for now.")

    print("\n--- Step 4: Data Restoration ---")
    if os.path.exists(sqlite_path):
        sl_conn = sqlite3.connect(sqlite_path)
        sl_cursor = sl_conn.cursor()
        try:
            sl_cursor.execute("SELECT * FROM transactions")
            sl_txs = sl_cursor.fetchall()
            col_names = [description[0] for description in sl_cursor.description]
            
            if sl_txs:
                print(f"  Restoring {len(sl_txs)} transactions...")
                with engine.begin() as conn:
                    pg_cols = [r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'transactions'"))]
                    for tx in sl_txs:
                        tx_dict = dict(zip(col_names, tx))
                        tx_dict = {k: v for k, v in tx_dict.items() if k in pg_cols}
                        old_uid = tx_dict.get('user_id')
                        new_uid = id_map.get(old_uid, old_uid)
                        tx_dict['user_id'] = new_uid
                        
                        keys = tx_dict.keys()
                        query = text(f"INSERT INTO transactions ({', '.join(keys)}) VALUES ({', '.join([':'+k for k in keys])}) ON CONFLICT DO NOTHING")
                        conn.execute(query, tx_dict)
                print("  Done.")
        except Exception as e:
            print(f"  Error: {e}")
        finally:
            sl_conn.close()

    print("\nRecovery finished.")

if __name__ == "__main__":
    run_recovery()
