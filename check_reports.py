from src.data.database import get_db_connection
from sqlalchemy import text

def check_recent_reports():
    try:
        with get_db_connection() as conn:
            query = text("SELECT report_type, title, created_at FROM reports ORDER BY created_at DESC LIMIT 5")
            res = conn.execute(query).fetchall()
            print("Recent reports in database:")
            for r in res:
                print(f" - Type: {r[0]}, Title: {r[1]}, Created At: {r[2]}")
                
            # Also check event_logs for any notification related logs
            query_logs = text("SELECT source, level, title, timestamp FROM event_logs WHERE source = 'Notification' OR title LIKE '%Email%' ORDER BY timestamp DESC LIMIT 5")
            res_logs = conn.execute(query_logs).fetchall()
            print("\nRecent notification-related logs:")
            for l in res_logs:
                 print(f" - Source: {l[0]}, Level: {l[1]}, Title: {l[2]}, Time: {l[3]}")
                 
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_recent_reports()
