from src.data.database import get_db_engine
from sqlalchemy import text

def add_col():
    engine = get_db_engine()
    with engine.begin() as conn:
        print("Checking/Adding leverage column...")
        conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS leverage FLOAT DEFAULT 1.0"))
        print("✓ leverage column ensured.")

if __name__ == "__main__":
    add_col()
