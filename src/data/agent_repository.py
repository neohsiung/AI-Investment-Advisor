import logging
import time
from typing import Dict, List, Optional
from sqlalchemy import text
from datetime import datetime
from src.data.database import get_db_engine

logger = logging.getLogger(__name__)

class AgentRepository:
    """
    Manages Agent Performance Metrics for Adaptive Swarm.
    Persists weights, success rates, and latency.
    """

    def __init__(self):
        self.engine = get_db_engine()
        self._init_table()

    def _init_table(self):
        """Ensure agent_performance table exists."""
        query = """
        CREATE TABLE IF NOT EXISTS agent_performance (
            agent_name TEXT PRIMARY KEY,
            tier TEXT,
            weight REAL DEFAULT 1.0,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            total_latency REAL DEFAULT 0.0,
            avg_latency REAL DEFAULT 0.0,
            last_updated TIMESTAMP
        );
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to init agent_performance table: {e}")

    def get_agent_weight(self, agent_name: str, default: float = 1.0) -> float:
        """Get current weight for an agent."""
        query = "SELECT weight FROM agent_performance WHERE agent_name = :name"
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {"name": agent_name}).scalar()
                return result if result is not None else default
        except Exception as e:
            logger.error(f"Failed to get weight for {agent_name}: {e}")
            return default

    def update_performance(self, agent_name: str, tier: str, success: bool, latency: float = 0.0, weight_delta: float = 0.0):
        """
        Update agent metrics.
        weight_delta: Change in weight (e.g., +0.1 for success, -0.2 for failure).
        """
        now = datetime.now().isoformat()
        
        # Upsert Logic
        # SQLite doesn't strictly support "ON CONFLICT DO UPDATE" in older versions, 
        # but modern ones do. Assuming standard SQL logic or using INSERT OR REPLACE.
        # Let's use a robust transaction approach.
        
        select_sql = "SELECT * FROM agent_performance WHERE agent_name = :name"
        insert_sql = """
            INSERT INTO agent_performance (agent_name, tier, weight, success_count, failure_count, total_latency, avg_latency, last_updated)
            VALUES (:name, :tier, :weight, :s_count, :f_count, :latency, :latency, :updated)
        """
        update_sql = """
            UPDATE agent_performance SET
                weight = weight + :w_delta,
                success_count = success_count + :s_inc,
                failure_count = failure_count + :f_inc,
                total_latency = total_latency + :lat,
                avg_latency = (total_latency + :lat) / (success_count + failure_count + 1),
                last_updated = :updated
            WHERE agent_name = :name
        """
        
        try:
            with self.engine.connect() as conn:
                existing = conn.execute(text(select_sql), {"name": agent_name}).fetchone()
                
                if not existing:
                    # Insert new
                    s_count = 1 if success else 0
                    f_count = 1 if not success else 0
                    conn.execute(text(insert_sql), {
                        "name": agent_name,
                        "tier": tier,
                        "weight": 1.0 + weight_delta,
                        "s_count": s_count,
                        "f_count": f_count,
                        "latency": latency,
                        "updated": now
                    })
                else:
                    # Update existing
                    s_inc = 1 if success else 0
                    f_inc = 1 if not success else 0
                    conn.execute(text(update_sql), {
                        "name": agent_name,
                        "w_delta": weight_delta,
                        "s_inc": s_inc,
                        "f_inc": f_inc,
                        "lat": latency,
                        "updated": now
                    })
                conn.commit()
                # logger.info(f"Updated performance for {agent_name}")
        except Exception as e:
            logger.error(f"Failed to update performance for {agent_name}: {e}")

    def get_top_agents(self, tier: str, limit: int = 5) -> List[Dict]:
        """Get high-performing agents for a specific tier."""
        query = """
            SELECT agent_name, weight, avg_latency 
            FROM agent_performance 
            WHERE tier = :tier 
            ORDER BY weight DESC, avg_latency ASC 
            LIMIT :limit
        """
        agents = []
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text(query), {"tier": tier, "limit": limit})
                for row in rows:
                    agents.append({
                        "name": row[0],
                        "weight": row[1],
                        "avg_latency": row[2]
                    })
        except Exception as e:
            logger.error(f"Failed to get top agents: {e}")
        return agents
