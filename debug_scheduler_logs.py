
import sys
import os
sys.path.append(os.getcwd())

from src.data.database import get_db_connection
from sqlalchemy import text
import pandas as pd

def inspect_logs():
    conn = get_db_connection()
    try:
        query = text("SELECT timestamp, job_name, status, message FROM scheduler_logs ORDER BY timestamp DESC LIMIT 20")
        result = conn.execute(query).fetchall()
        
        print(f"{'Timestamp':<25} | {'Job Name':<20} | {'Status':<10} | {'Message'}")
        print("-" * 100)
        for row in result:
            timestamp, job_name, status, message = row
            print(f"{timestamp:<25} | {job_name:<20} | {status:<10} | {message}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_logs()
