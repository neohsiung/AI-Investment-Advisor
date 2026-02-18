from src.data.database import get_db_connection
from sqlalchemy import text

def find_user():
    try:
        with get_db_connection() as conn:
            query = text("SELECT id, email FROM users")
            res = conn.execute(query).fetchall()
            print("Users in database:")
            for r in res:
                print(f" - ID: {r[0]}, Email: {r[1]}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_user()
