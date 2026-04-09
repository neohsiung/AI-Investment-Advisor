import sys
import argparse
import logging
import os
import json

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.data.database import get_db_engine
from sqlalchemy import text
import pandas as pd
from src.utils.logger import setup_logger

logger = setup_logger("get_historical_report_cli")

def main():
    parser = argparse.ArgumentParser(description="Fetch historical investment report.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    parser.add_argument("--report_type", default="WeeklyWorkflow", help="Type of report (WeeklyWorkflow/DailyWorkflow)")
    parser.add_argument("--weeks_ago", type=int, default=1, help="Number of weeks ago")
    
    args = parser.parse_args()
    
    try:
        offset = max(0, args.weeks_ago - 1)
        engine = get_db_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT created_at, content 
                FROM reports 
                WHERE user_id = :uid AND report_type = :rtype
                ORDER BY created_at DESC 
                LIMIT 1 OFFSET :offset
            """)
            df = pd.read_sql(query, conn, params={"uid": args.user_id, "rtype": args.report_type, "offset": offset})
            
            if df.empty:
                print(f"No historical ({args.report_type}) report found from {args.weeks_ago} weeks ago.")
                return
                
            record = df.iloc[0]
            date_str = str(record['created_at'])
            content = str(record['content'])
            print(f"Report Date: {date_str}\n\nContent:\n{content}")
    except Exception as e:
        logger.error(f"CLI get_historical_report failed: {e}")
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
