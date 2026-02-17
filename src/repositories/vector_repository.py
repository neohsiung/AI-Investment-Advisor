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
    def add_council_minute(self, session_id: str, topic: str, participants: List[str], consensus: str, transcript: str, embedding: List[float]) -> str:
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

class VectorRepositoryImpl(BaseRepository, IVectorRepository):
    """
    Repository for handling Vector Database operations (PGVector/SQLite-Vec).
    處理向量資料庫呈現 (PGVector/SQLite-Vec) 的儲存庫。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

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
            query = text("""
                INSERT INTO memory_embeddings (id, user_id, timestamp, category, content, embedding, metadata)
                VALUES (:id, :uid, :ts, :cat, :cont, :emb, :meta)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "uid": user_id,
                "ts": datetime.utcnow().isoformat(),
                "cat": category,
                "cont": content,
                "emb": self._ensure_string_embedding(embedding),
                "meta": json.dumps(metadata)
            })
            return new_id

    def search_memory(self, user_id: str, embedding: List[float], top_k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Searches similar memories using vector similarity.
        使用向量相似度搜尋相似記憶。
        """
        if self.is_sqlite:
            logger.warning("VectorRepo: SQLite detected, vector search skipped.")
            return []

        with self.engine.connect() as conn:
            # PGVector Cosine Similarity: 1 - (a <=> b)
            query = text("""
                SELECT id, content, category, metadata, 1 - (embedding <=> :emb) as similarity
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
                    "category": row.category,
                    "metadata": json.loads(row.metadata) if row.metadata else {},
                    "similarity": row.similarity
                })
            return results

    def add_council_minute(self, session_id: str, topic: str, participants: List[str], consensus: str, transcript: str, embedding: List[float]) -> str:
        """
        Logs a Council Session with vector embedding.
        記錄帶有向量嵌入的議會會議記錄。
        """
        new_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO council_minutes (id, session_id, timestamp, topic, participants, consensus_decision, full_transcript, embedding)
                VALUES (:id, :sid, :ts, :topic, :parts, :decision, :transcript, :emb)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "sid": session_id,
                "ts": datetime.utcnow().isoformat(),
                "topic": topic,
                "parts": json.dumps(participants),
                "decision": consensus,
                "transcript": transcript,
                "emb": self._ensure_string_embedding(embedding)
            })
            return new_id

    def search_similar_minutes_by_embedding(self, embedding: List[float], limit: int = 1, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on embedding similarity.
        根據嵌入相似度檢索過去的議會記錄。
        """
        if self.is_sqlite:
            return []

        with self.engine.connect() as conn:
            query = text("""
                SELECT id, topic, consensus_decision, full_transcript, 1 - (embedding <=> :emb) as similarity
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
                "topic": row.topic,
                "consensus": row.consensus_decision,
                "transcript": row.full_transcript,
                "similarity": row.similarity
            } for row in rows]

# Legacy alias
# @deprecated: Use VectorRepositoryImpl
SqliteVectorRepository = VectorRepositoryImpl
VectorRepository = VectorRepositoryImpl
