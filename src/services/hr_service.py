from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import text
from src.data.database import get_db_connection
from src.utils.time_utils import get_current_time

class HRService:
    def __init__(self, db_path="data/cache.db"):
        self.db_path = db_path

    def check_agent_health(self):
        """
        Check the health status of all agents based on their last activity in cache.
        Returns a DataFrame with columns: [Agent, Last Active, Status, Days Inactive]
        """
        conn = get_db_connection(self.db_path)
        try:
            query = text("""
                SELECT agent_name, MAX(timestamp) as last_active 
                FROM response_cache 
                GROUP BY agent_name
            """)
            df = pd.read_sql(query, conn)
            
            if df.empty:
                return pd.DataFrame(columns=["Agent", "Last Active", "Status", "Days Inactive"])

            # Process data
            now = get_current_time()
            if now.tzinfo is None:
                now = now.replace(tzinfo=None) # Ensure naive if DB is naive
            
            results = []
            
            # Known Agents List (to detect those never active)
            known_agents = ["Momentum", "Fundamental", "Macro", "CIO", "Dispatcher", "System Engineer", "Sentiment"]
            
            # Map existing data
            agent_status_map = {}
            
            for _, row in df.iterrows():
                agent_name = row['agent_name']
                last_active_str = row['last_active']
                
                try:
                    # Handle ISO format
                    last_active = pd.to_datetime(last_active_str)
                    if last_active.tzinfo is not None and now.tzinfo is None:
                         last_active = last_active.tz_localize(None)
                    elif last_active.tzinfo is None and now.tzinfo is not None:
                         last_active = last_active.tz_localize(now.tzinfo)
                         
                except Exception:
                    last_active = now # Fallback
                
                diff = now - last_active
                days_inactive = diff.days
                
                status = "✅ Active"
                if days_inactive > 7:
                    status = "🧟 Zombie"
                elif days_inactive > 3:
                     status = "⚠️ Idle"

                agent_status_map[agent_name] = {
                    "Last Active": last_active.strftime("%Y-%m-%d %H:%M"),
                    "Status": status,
                    "Days Inactive": days_inactive
                }

            # Merge with known agents
            final_data = []
            for agent in known_agents:
                if agent in agent_status_map:
                    row_data = agent_status_map[agent]
                    final_data.append({
                        "Agent": agent,
                        **row_data
                    })
                else:
                    final_data.append({
                        "Agent": agent,
                        "Last Active": "N/A",
                        "Status": "👻 Missing",
                        "Days Inactive": -1
                    })
                    
            # Add any extra agents found in DB
            for agent in agent_status_map:
                if agent not in known_agents:
                    row_data = agent_status_map[agent]
                    final_data.append({
                        "Agent": agent,
                        **row_data
                    })

            return pd.DataFrame(final_data)
            
        finally:
            conn.close()
