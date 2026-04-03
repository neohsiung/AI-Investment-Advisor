import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta

from src.data.database import BaseRepository, get_db_engine
from sqlalchemy import text

logger = logging.getLogger("CognitiveMemoryManager")

class CognitiveMemoryManager:
    """
    Rule #8: Cognitive Memory Tiering.
    認知記憶管理器：實作三階層記憶架構。
    
    Tiers:
    1. Short (Fast): Redis / In-memory (Ticks/Events)
    2. Medium (Structured): PostgreSQL (Insights/Convictions)
    3. Long (Cold): File-based / Compressed (Archives)
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.engine = get_db_engine()
        self.long_term_path = Path("data/memory/long_term") / str(user_id or "default")
        self.long_term_path.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────
    # Medium-Term Storage (SQL)
    # ──────────────────────────────────────────

    def store_insight(self, agent_name: str, memory_type: str, content: Dict[str, Any], importance: float = 0.5, source_id: str = None):
        """
        Stores a distilled insight into the medium-term memory (PostgreSQL).
        將提煉出的見解儲存至中階記憶體 (SQL)。
        """
        sql = """
        INSERT INTO cognitive_memories (user_id, agent_name, memory_type, content, importance, source_id)
        VALUES (:user_id, :agent_name, :memory_type, :content, :importance, :source_id)
        """
        try:
            with self.engine.begin() as conn:
                conn.execute(text(sql), {
                    "user_id": self.user_id,
                    "agent_name": agent_name,
                    "memory_type": memory_type,
                    "content": json.dumps(content),
                    "importance": importance,
                    "source_id": source_id
                })
            logger.info(f"Stored {memory_type} memory for agent {agent_name} (User: {self.user_id})")
        except Exception as e:
            logger.error(f"Failed to store cognitive memory: {e}")

    def get_recent_memories(self, limit: int = 10, memory_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves recent distilled memories.
        讀取近期提煉出的記憶。
        """
        sql = """
        SELECT agent_name, memory_type, content, importance, created_at 
        FROM cognitive_memories 
        WHERE user_id = :user_id
        """
        params = {"user_id": self.user_id, "limit": limit}
        if memory_type:
            sql += " AND memory_type = :memory_type"
            params["memory_type"] = memory_type
        
        sql += " ORDER BY created_at DESC LIMIT :limit"
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params).fetchall()
                return [
                    {
                        "agent_name": row[0],
                        "memory_type": row[1],
                        "content": json.loads(row[2]) if isinstance(row[2], str) else row[2],
                        "importance": float(row[3]),
                        "created_at": row[4].isoformat() if hasattr(row[4], 'isoformat') else str(row[4])
                    }
                    for row in result
                ]
        except Exception as e:
            logger.error(f"Failed to retrieve cognitive memories: {e}")
            return []

    # ──────────────────────────────────────────
    # Long-Term Storage (Files)
    # ──────────────────────────────────────────

    def archive_to_long_term(self, month: str = None):
        """
        Archives old medium-term memories to long-term storage (JSON files).
        將舊的中階記憶歸檔至長階儲存 (JSON 檔案)。
        """
        if not month:
            # Default to last month
            last_month = datetime.now() - timedelta(days=30)
            month = last_month.strftime("%Y-%m")
        
        # Implement background compression/archiving logic here
        pass

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Semantic search across tiers (Future optimization).
        跨層級語義搜索（未來優化）。
        """
        # For now, just return SQL matches
        return self.get_recent_memories(limit=5)
