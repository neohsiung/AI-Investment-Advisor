from src.data.database import get_db_engine
from sqlalchemy import text
import json

def check_denied_logs():
    engine = get_db_engine()
    with engine.connect() as conn:
        # Check event_logs
        print("--- Event Logs (Errors) ---")
        sql = text("SELECT title, content, created_at FROM event_logs WHERE content LIKE '%smart%' OR content LIKE '%Consensus failed%' ORDER BY created_at DESC LIMIT 5")
        result = conn.execute(sql).fetchall()
        for row in result:
            print(f"Time: {row[2]} | Title: {row[0]}")
            print(f"Content: {row[1]}")
            print("-" * 20)

        # Check llm_usage_logs (even if failed, check if tier was 'smart')
        print("\n--- LLM Usage Logs (Recent Smart Tier) ---")
        sql = text("SELECT agent_name, model, tier, created_at FROM llm_usage_logs WHERE tier = 'smart' ORDER BY created_at DESC LIMIT 5")
        result = conn.execute(sql).fetchall()
        for row in result:
            print(f"Time: {row[3]} | Agent: {row[0]} | Model: {row[1]} | Tier: {row[2]}")
            print("-" * 20)

if __name__ == "__main__":
    try:
        check_denied_logs()
    except Exception as e:
        print(f"Error checking logs: {e}")
