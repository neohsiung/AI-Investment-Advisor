import logging
import uuid
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

logger = logging.getLogger(__name__)

class IVectorRepository(ABC):
    """
    Interface for Vector Repository.
    向量儲存庫介面。
    """
    @abstractmethod
    def add_memory(self, user_id: str, category: str, content: str, embedding: List[float], metadata: Dict = {}) -> str:
        """
        Inserts a new memory item with vector embedding.
        新增帶有向量嵌入的記憶項目。
        """
        pass

    @abstractmethod
    def search_memory(self, user_id: str, embedding: List[float], top_k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Searches similar memories using vector similarity.
        使用向量相似度搜尋相似記憶。
        """
        pass

    @abstractmethod
    def add_council_minute(self, user_id: str, session_id: str, topic: str, participants: List[str], consensus: str, transcript: str, embedding: List[float]) -> str:
        """
        Logs a Council Session with vector embedding.
        記錄帶有向量嵌入的議會會議記錄。
        """
        pass

    @abstractmethod
    def search_similar_minutes_by_embedding(self, embedding: List[float], limit: int = 1, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on embedding similarity.
        根據嵌入相似度檢索過去的議會記錄。
        """
        pass

class AlchemyVectorRepository(BaseRepository, IVectorRepository):
    """
    Repository for handling Vector Database operations (PGVector strictly).
    處理向量資料庫呈現 (PGVector 專用) 的儲存庫。
    """
    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        engine = engine or get_db_engine(db_path)
        BaseRepository.__init__(self, engine)

    def _ensure_string_embedding(self, embedding: List[float]) -> str:
        """
        Converts list to string format '[x,y,z]' for SQL insertion.
        將列表轉換為字串格式以供 SQL 插入。
        """
        return str(embedding)

    def add_memory(self, user_id: str, category: str, content: str, embedding: List[float], metadata: Dict = {}) -> str:
        """
        Inserts a new memory item with vector embedding.
        新增帶有向量嵌入的記憶項目。
        """
        new_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            # v4.2.1: Aligned with database.py (created_at instead of timestamp)
            query = text("""
                INSERT INTO memory_embeddings (id, user_id, content, embedding, metadata, created_at)
                VALUES (:id, :uid, :cont, :emb, :meta, :ts)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "uid": user_id,
                "cont": content,
                "emb": self._ensure_string_embedding(embedding),
                "meta": json.dumps(metadata),
                "ts": datetime.utcnow()
            })
            return new_id

    def search_memory(self, user_id: str, embedding: List[float], top_k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Searches similar memories using vector similarity (PostgreSQL pgvector).
        """
        # v4.2.1: Skip vector search on SQLite (tests)
        if self.engine.dialect.name == "sqlite":
            logger.warning("Vector search skipped on SQLite.")
            return []

        with self.engine.connect() as conn:
            # PGVector Cosine Similarity: 1 - (a <=> b)
            query = text("""
                SELECT id, content, metadata, 1 - (embedding <=> :emb) as similarity
                FROM memory_embeddings
                WHERE user_id = :uid
                AND 1 - (embedding <=> :emb) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)

            rows = conn.execute(query, {
                "uid": user_id,
                "emb": self._ensure_string_embedding(embedding),
                "threshold": threshold,
                "limit": top_k
            }).fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row.id,
                    "content": row.content,
                    "metadata": json.loads(row.metadata) if row.metadata else {},
                    "similarity": row.similarity
                })
            return results

    def add_council_minute(self, user_id: str, session_id: str, topic: str, participants: List[str], consensus: str, transcript: str, embedding: List[float]) -> str:
        """
        Logs a Council Session with vector embedding.
        """
        new_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            # v4.2.1: Aligned with database.py schema (including user_id)
            query = text("""
                INSERT INTO council_minutes (id, user_id, session_id, decision, embedding, created_at)
                VALUES (:id, :uid, :sid, :decision, :emb, :ts)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "uid": user_id,
                "sid": session_id,
                "decision": consensus,
                "emb": self._ensure_string_embedding(embedding),
                "ts": datetime.utcnow()
            })
            return new_id

    def search_similar_minutes_by_embedding(self, embedding: List[float], limit: int = 1, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on embedding similarity (PostgreSQL pgvector).
        """
        if self.engine.dialect.name == "sqlite":
            return []

        with self.engine.connect() as conn:
            query = text("""
                SELECT id, decision as consensus, 1 - (embedding <=> :emb) as similarity
                FROM council_minutes
                WHERE 1 - (embedding <=> :emb) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            
            rows = conn.execute(query, {
                "emb": self._ensure_string_embedding(embedding),
                "threshold": threshold,
                "limit": limit
            }).fetchall()
            
            return [{
                "id": row.id,
                "consensus": row.consensus,
                "similarity": row.similarity
            } for row in rows]
