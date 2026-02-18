import os
from sqlalchemy import create_engine, text

def check_db():
    db_url = os.getenv("DB_URL", "postgresql://postgres:postgres@localhost:5432/portfolio")
    engine = create_engine(db_url)
    
    tables = ["users", "user_identities", "reports", "settings", "transactions", "daily_snapshots", "daily_reports", "weekly_reports"]
    
    print("--- Tables in Database ---")
    with engine.connect() as conn:
        res = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        for row in res:
            print(f"Table: {row[0]}")
            
    for table in tables:
        print(f"\n--- Schema for table: {table} ---")
        try:
            with engine.connect() as conn:
                res = conn.execute(text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}'"))
                cols = res.fetchall()
                if not cols:
                    print(f"  Table {table} does not exist or has no columns.")
                for row in cols:
                    print(f"  Column: {row[0]}, Type: {row[1]}")
        except Exception as e:
            print(f"  Error reading schema for {table}: {e}")

    print("\n--- User Identities ---")
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT * FROM user_identities LIMIT 5")).fetchall()
            for row in res:
                print(row)
    except Exception as e:
        print(f"  Error: {e}")

    print("\n--- Users (First 5) ---")
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT id, email, name FROM users LIMIT 5")).fetchall()
            for row in res:
                print(row)
    except Exception as e:
        print(f"  Error: {e}")

    print("\n--- Current ID and Email check ---")
    check_queries = [
        ("reports", "SELECT DISTINCT user_id FROM reports"),
        ("transactions", "SELECT DISTINCT user_id FROM transactions"),
        ("settings", "SELECT DISTINCT user_id FROM settings"),
        ("daily_snapshots", "SELECT DISTINCT user_id FROM daily_snapshots")
    ]
    for label, q in check_queries:
        print(f"Checking {label}...")
        try:
            with engine.connect() as conn:
                res = conn.execute(text(q)).fetchall()
                print(f"  Unique user_ids in {label}: {res}")
        except Exception as e:
            print(f"  Error checking {label}: {str(e).splitlines()[0]}")

if __name__ == "__main__":
    check_db()
