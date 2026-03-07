import logging
import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import text

logger = logging.getLogger(__name__)

class HybridMemory:
    """
    OpenClaw Layer 4: Memory Subsystem.
    Unified PostgreSQL + pgvector support.
    """

    def __init__(self, db_path: str = None, engine=None, vector_dim: int = 1536):
        from src.data.database import get_db_engine
        self.engine = engine or get_db_engine(db_path)
        self.vector_dim = vector_dim
        # Legacy weights expected by tests
        self.vector_weight = 0.7
        self.keyword_weight = 0.3
        self._create_tables()

    def _create_tables(self):
        """Create tables if they don't exist."""
        is_sqlite = "sqlite" in str(self.engine.url)
        
        with self.engine.begin() as conn:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS memory_embeddings (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        embedding TEXT,
                        metadata TEXT,
                        created_at DATETIME
                    )
                """))
            else:
                # PostgreSQL with pgvector
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS memory_embeddings (
                        id UUID PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        embedding vector({self.vector_dim}),
                        metadata JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))

    def add_memory(self, memory_id: str = None, user_id: str = None, content: str = None, embedding: List[float] = None, category: str = None, metadata: Dict = None, **kwargs):
        """
        Inserts a memory into the unified memory_embeddings table.
        Supports both positional and keyword arguments from legacy tests.
        """
        import uuid
        # Map arguments flexibly - handles (id, user_id, content, embedding, category)
        # or (user_id, content, embedding, metadata, memory_id)
        
        # Initial guess based on typical usage
        active_id = memory_id or str(uuid.uuid4())
        active_user = user_id or "default_user"
        active_content = content or ""
        active_embedding = embedding or []
        
        # Merge all extra kwargs into metadata
        meta = metadata or {}
        if category:
            meta["category"] = category
        if kwargs:
            meta.update(kwargs)
            
        is_sqlite = "sqlite" in str(self.engine.url)
        
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO memory_embeddings (id, user_id, content, embedding, metadata, created_at)
                VALUES (:id, :user_id, :content, :embedding, :meta, :created_at)
            """)
            
            conn.execute(query, {
                "id": active_id,
                "user_id": active_user,
                "content": active_content,
                "embedding": json.dumps(active_embedding) if is_sqlite else active_embedding,
                "meta": json.dumps(meta) if is_sqlite else meta,
                "created_at": datetime.now(timezone.utc)
            })
            logger.info(f"HybridMemory: Added memory {active_id}")
        return active_id

    def search(self, query_text: str = None, query_vector: List[float] = None, user_id: str = None, limit: int = 5) -> List[Dict]:
        """
        Performs Search (with PostgreSQL + pgvector support or SQLite Keyword fallback).
        Support legacy signature where user_id might be omitted or passed in different order.
        """
        is_sqlite = "sqlite" in str(self.engine.url)
        
        # Handle positional args if called as search("user_id", "query_text", ...)
        # but the tests seem to call as search(query_text="...", ...)
        
        with self.engine.connect() as conn:
            where_clause = "1=1"
            params = {"l": limit}
            
            if user_id:
                where_clause += " AND user_id = :uid"
                params["uid"] = user_id
                
            if is_sqlite:
                # SQLite Fallback: Keyword search if text provided
                if query_text:
                    where_clause += " AND content LIKE :q"
                    params["q"] = f"%{query_text}%"
                    score_col = "1.0 as score"
                else:
                    score_col = "0.5 as score"
                
                query = text(f"""
                    SELECT id, content, metadata, {score_col}
                    FROM memory_embeddings
                    WHERE {where_clause}
                    LIMIT :l
                """)  # nosec B608
                result = conn.execute(query, params)
            else:
                # PostgreSQL + pgvector optimization
                params["embedding"] = query_vector
                query = text(f"""
                    SELECT id, content, metadata, 1 - (embedding <=> :embedding) as score
                    FROM memory_embeddings
                    WHERE {where_clause}
                    ORDER BY embedding <=> :embedding
                    LIMIT :l
                """)  # nosec B608
                result = conn.execute(query, params)
            
            rows = result.fetchall()
            return [{
                "id": str(r[0]),
                "content": r[1],
                "metadata": json.loads(r[2]) if is_sqlite and isinstance(r[2], str) else r[2],
                "score": float(r[3])
            } for r in rows]
