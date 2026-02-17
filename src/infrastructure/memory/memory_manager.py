import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import text

logger = logging.getLogger(__name__)

class HybridMemory:
    """
    OpenClaw Layer 4: Memory Subsystem.
    Unified PostgreSQL + pgvector support with SQLite fallback.
    """

    def __init__(self, db_path: str = None, engine=None, vector_dim: int = 1536):
        from src.data.database import get_db_engine
        self.engine = engine or get_db_engine(db_path)
        self.vector_dim = vector_dim
        self.is_sqlite = 'sqlite' in str(self.engine.url)

    def add_memory(self, user_id: str, content: str, embedding: List[float], metadata: Dict = None, memory_id: str = None):
        """
        Inserts a memory into the unified memory_embeddings table.
        """
        import uuid
        mem_id = memory_id or str(uuid.uuid4())
        
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO memory_embeddings (id, user_id, content, embedding, metadata, created_at)
                VALUES (:id, :user_id, :content, :embedding, :meta, :created_at)
            """)
            
            conn.execute(query, {
                "id": mem_id,
                "user_id": user_id,
                "content": content,
                "embedding": str(embedding) if self.is_sqlite else embedding,
                "meta": json.dumps(metadata or {}) if self.is_sqlite else (metadata or {}),
                "created_at": datetime.now(timezone.utc)
            })
            logger.info(f"HybridMemory: Added memory {mem_id}")
        return mem_id

    def search(self, user_id: str, query_text: str, query_vector: List[float], limit: int = 5) -> List[Dict]:
        """
        Performs Semantic Search (with pgvector support).
        Keyword search (LIKE) fallback for SQLite.
        """
        with self.engine.connect() as conn:
            if self.is_sqlite:
                # Simple keyword match for SQLite
                query = text("""
                    SELECT id, content, metadata 
                    FROM memory_embeddings 
                    WHERE user_id = :uid AND content LIKE :q 
                    LIMIT :l
                """)
                result = conn.execute(query, {"uid": user_id, "q": f"%{query_text}%", "l": limit})
                rows = result.fetchall()
                return [{
                    "id": r[0],
                    "content": r[1],
                    "metadata": json.loads(r[2]) if isinstance(r[2], str) else r[2],
                    "score": 0.5
                } for r in rows]
            else:
                # PostgreSQL + pgvector
                query = text("""
                    SELECT id, content, metadata, 1 - (embedding <=> :embedding) as score
                    FROM memory_embeddings
                    WHERE user_id = :uid
                    ORDER BY embedding <=> :embedding
                    LIMIT :l
                """)
                result = conn.execute(query, {"uid": user_id, "embedding": query_vector, "l": limit})
                rows = result.fetchall()
                return [{
                    "id": str(r[0]),
                    "content": r[1],
                    "metadata": r[2],
                    "score": float(r[3])
                } for r in rows]
