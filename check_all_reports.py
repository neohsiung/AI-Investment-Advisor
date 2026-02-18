from src.data.database import get_db_connection
from sqlalchemy import text

def check_all_reports():
    try:
        with get_db_connection() as conn:
            query = text("SELECT DISTINCT report_type FROM reports")
            types = [r[0] for r in conn.execute(query).fetchall()]
            print(f"Report types in database: {types}")
            
            query_all = text("SELECT report_type, title, created_at FROM reports ORDER BY created_at DESC LIMIT 20")
            res = conn.execute(query_all).fetchall()
            print("\nAll recent reports:")
            for r in res:
                print(f" - Type: {r[0]}, Title: {r[1]}, Created At: {r[2]}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_all_reports()
