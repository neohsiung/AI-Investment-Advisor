from src.utils.logger import setup_logger
logger = setup_logger("AgentRepository")

import time
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from sqlalchemy import text
from datetime import datetime
from src.data.database import BaseRepository, get_db_engine

class IAgentRepository(ABC):
    """
    Interface for Agent Repository.
    代理人儲存庫介機。
    """
    @abstractmethod
    def get_agent_weight(self, agent_name: str, default: float = 1.0) -> float:
        """Get current weight for an agent."""
        pass

    @abstractmethod
    def update_performance(self, agent_name: str, tier: str, success: bool, latency: float = 0.0, weight_delta: float = 0.0) -> None:
        """Update agent metrics."""
        pass

    @abstractmethod
    def get_top_agents(self, tier: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get high-performing agents for a specific tier."""
        pass

class AlchemyAgentRepository(BaseRepository, IAgentRepository):
    """
    Implementation of IAgentRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IAgentRepository。
    """

    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))
        self._init_table()

    def _init_table(self) -> None:
        """
        Ensure agent_performance table exists.
        確保代理人績效表存在。
        """
        query = text("""
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
        """)
        try:
            with self.engine.begin() as conn:
                conn.execute(query)
        except Exception as e:
            logger.error(f"Failed to init agent_performance table: {e}")

    def get_agent_weight(self, agent_name: str, default: float = 1.0) -> float:
        """
        Get current weight for an agent.
        獲取代理人權重。
        """
        query = text("SELECT weight FROM agent_performance WHERE agent_name = :name")
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, {"name": agent_name}).scalar()
                return float(result) if result is not None else default
        except Exception as e:
            logger.error(f"Failed to get weight for {agent_name}: {e}")
            return default

    def update_performance(self, agent_name: str, tier: str, success: bool, latency: float = 0.0, weight_delta: float = 0.0) -> None:
        """
        Update agent metrics.
        更新代理人績效。
        """
        now = datetime.now().isoformat()
        
        upsert_sql = text("""
            INSERT INTO agent_performance (agent_name, tier, weight, success_count, failure_count, total_latency, avg_latency, last_updated)
            VALUES (:name, :tier, :weight, :s_count, :f_count, :latency, :latency, :updated)
            ON CONFLICT(agent_name) DO UPDATE SET
                weight = agent_performance.weight + :w_delta,
                success_count = agent_performance.success_count + :s_inc,
                failure_count = agent_performance.failure_count + :f_inc,
                total_latency = agent_performance.total_latency + :lat,
                avg_latency = (agent_performance.total_latency + :lat) / (agent_performance.success_count + agent_performance.failure_count + 1),
                last_updated = :updated
        """)
        
        try:
            with self.engine.begin() as conn:
                s_inc = 1 if success else 0
                f_inc = 1 if not success else 0
                conn.execute(upsert_sql, {
                    "name": agent_name,
                    "tier": tier,
                    "weight": 1.0 + weight_delta,
                    "s_count": s_inc,
                    "f_count": f_inc,
                    "latency": latency,
                    "updated": now,
                    "w_delta": weight_delta,
                    "s_inc": s_inc,
                    "f_inc": f_inc,
                    "lat": latency
                })
        except Exception as e:
            logger.error(f"Failed to update performance for {agent_name}: {e}")

    def get_top_agents(self, tier: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get high-performing agents for a specific tier.
        獲取高績效代理人。
        """
        query = text("""
            SELECT agent_name, weight, avg_latency 
            FROM agent_performance 
            WHERE tier = :tier 
            ORDER BY weight DESC, avg_latency ASC 
            LIMIT :limit
        """)
        agents = []
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query, {"tier": tier, "limit": limit})
                for row in results:
                    agents.append({
                        "name": row.agent_name,
                        "weight": float(row.weight),
                        "avg_latency": float(row.avg_latency)
                    })
        except Exception as e:
            logger.error(f"Failed to get top agents: {e}")
        return agents

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyAgentRepository
