import os
from sqlalchemy import create_engine, text

def main():
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "advisor_prod")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "postgres")
    
    url = f"postgresql://{db_user}:{db_pass}@{db_host}/{db_name}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        print("\n--- Settings Preview ---")
        try:
            res = conn.execute(text("SELECT key, value FROM settings LIMIT 10"))
            for row in res:
                print(f"Key: {row[0]}, Value: {row[1]!r}")
        except Exception as e:
            print(f"Error querying settings: {e}")

if __name__ == "__main__":
    main()
